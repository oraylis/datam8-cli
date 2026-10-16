"""Exclusive workspace transitions for the opt-in desktop server.

The CLI's config/factory accessors remain compatibility adapters. They may only
be changed while the HTTP gate is held, including while parsing awaits file IO.
The gate surrounds the ASGI response, not just creation of a streaming response.
"""

from __future__ import annotations

import asyncio
import importlib
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi.responses import JSONResponse

from datam8 import config, factory, generate, model, plugins
from datam8.errors import (
    Datam8Error,
    Datam8ValidationError,
    ModelParseError,
    NotSupportedModelVersionError,
)
from datam8.secrets import SecretResolver
from datam8.utils.importer import TargetModuleFinder

HEADER = b"x-datam8-workspace"


@dataclass
class WorkspaceContext:
    path: Path
    folder: Path
    model: model.Model
    plugins: plugins.PluginManager | None

    @classmethod
    def current(cls) -> WorkspaceContext:
        return cls(
            config.solution_path,
            config.solution_folder_path,
            factory.get_model(),
            factory._plugin_manager,
        )

    def activate(self) -> None:
        config.solution_path = self.path
        config.solution_folder_path = self.folder
        factory._model = self.model
        factory._plugin_manager = self.plugins


class WorkspaceManager:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self.id = str(uuid.uuid4())
        self.lock = asyncio.Lock()

    def describe(self) -> dict[str, str]:
        return {"workspaceId": self.id, "path": str(config.solution_path)}

    def require_enabled(self) -> None:
        if not self.enabled:
            raise Datam8Error(code="permission", message="Workspace switching is disabled.")

    async def open(self, path: Path) -> dict[str, str]:
        self.require_enabled()
        if not path.is_absolute() or path.suffix.lower() != ".dm8s":
            raise Datam8ValidationError(message="An absolute .dm8s file path is required.")
        path = path.resolve(strict=True)
        if path == config.solution_path.resolve():
            return self.describe()
        previous = WorkspaceContext.current()
        changed, deleted = previous.model.get_unsaved_entities()
        if changed or deleted:
            raise Datam8Error(
                code="conflict", message="Save pending changes before switching solutions."
            )

        try:
            config.set_solution(path)
            candidate_model = await factory.load_model(path)
            candidate = WorkspaceContext(
                path, path.parent, candidate_model, plugins.PluginManager(candidate_model.solution)
            )
        except (ValueError, ModelParseError, NotSupportedModelVersionError) as error:
            previous.activate()
            raise Datam8ValidationError(message=f"Cannot open solution: {error}") from error
        except BaseException:
            previous.activate()
            raise

        candidate.activate()
        self.id = str(uuid.uuid4())
        SecretResolver.reset_singleton()
        generate.payload_functions.clear()
        TargetModuleFinder._path.clear()
        # Custom plugin and target modules must not survive under a shared name.
        # Driver libraries outside the previous solution stay imported.
        for name, module in list(sys.modules.items()):
            origin = getattr(module, "__file__", None)
            # A solution can contain the development checkout/venv itself.
            # Never unload the server or its installed driver dependencies.
            infrastructure = (Path(factory.__file__).parent, Path(sys.prefix))
            if (
                isinstance(origin, str)
                and Path(origin).is_relative_to(previous.folder)
                and not name.startswith(("datam8.", "datam8_model."))
                and name not in {"datam8", "datam8_model"}
                and not any(Path(origin).is_relative_to(root) for root in infrastructure)
            ):
                sys.modules.pop(name, None)
        importlib.invalidate_caches()
        return self.describe()


class WorkspaceMiddleware:
    def __init__(self, app, manager: WorkspaceManager) -> None:
        self.app = app
        self.manager = manager

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or not self.manager.enabled or scope["path"] == "/health":
            await self.app(scope, receive, send)
            return
        async with self.manager.lock:
            path = scope["path"]
            if path != "/version" and not (path == "/workspace" and scope["method"] == "GET"):
                requested = dict(scope["headers"]).get(HEADER, b"")
                if requested != self.manager.id.encode():
                    error = Datam8Error(
                        code="conflict", message="Workspace changed; reload before retrying."
                    )
                    response = JSONResponse(
                        status_code=409, content=error.to_envelope().model_dump()
                    )
                    await response(scope, receive, send)
                    return
            await self.app(scope, receive, send)
