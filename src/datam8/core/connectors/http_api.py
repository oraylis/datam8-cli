from __future__ import annotations

import base64
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from datam8.core.errors import (
    Datam8ExternalSystemError,
    Datam8PermissionError,
    Datam8ValidationError,
)

if TYPE_CHECKING:
    pass  # pragma: no cover


DEFAULT_REQUEST_TIMEOUT_MS = 30_000
TOKEN_EXPIRY_SKEW_MS = 60_000
SAMPLE_ROW_LIMIT = 75


def _get_by_path(obj: Any, path: str | None) -> Any:
    if not path:
        return obj
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


@dataclass
class _OAuthTokenCache:
    access_token: str
    expires_at_ms: int


class HttpApiRestConnector:
    def __init__(
        self,
        config: dict[str, Any],
        runtime_secrets: dict[str, str],
        *,
        http_client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._config = config or {}
        self._secrets = runtime_secrets or {}
        self._token_cache: _OAuthTokenCache | None = None
        self._http_client_factory = http_client_factory

    def request_json_array(self, *, source_location: str) -> list[Any]:
        httpx = _import_httpx()
        url = self._build_url(source_location)
        headers: dict[str, str] = {
            "content-type": "application/json",
            "accept": "application/json",
        }
        self._apply_auth(headers)

        timeout_ms = int(self._config.get("requestTimeoutMs") or DEFAULT_REQUEST_TIMEOUT_MS)
        try:
            with self._client(timeout_ms=timeout_ms, httpx=httpx) as client:
                resp = client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException:
            raise Datam8ExternalSystemError(
                code="http_timeout",
                message=f"Request timeout after {timeout_ms} ms for {url}",
                details={"url": url, "timeoutMs": timeout_ms},
            )
        except httpx.HTTPStatusError as e:
            text = (e.response.text or "").strip()
            msg = f"HTTP API request failed ({e.response.status_code} {e.response.reason_phrase})"
            if text:
                msg = f"{msg}: {text}"
            raise Datam8ExternalSystemError(code="http_error", message=msg, details={"url": url, "status": e.response.status_code})
        except Exception as e:
            raise Datam8ExternalSystemError(code="http_error", message="HTTP API request failed.", details={"url": url, "error": str(e)})

        has_path = bool(self._config.get("responseArrayPath"))
        response_path = str(self._config.get("responseArrayPath") or "") or None
        extracted = _get_by_path(data, response_path) if has_path else data

        if has_path and extracted is None:
            raise Datam8ValidationError(
                message=f"Expected JSON array or object at path '{response_path}', got undefined",
                details={"path": response_path},
            )

        if isinstance(extracted, list):
            return extracted
        if isinstance(extracted, dict):
            return [extracted]
        type_label = "null" if extracted is None else type(extracted).__name__
        label = response_path or "root"
        raise Datam8ValidationError(
            message=f"Expected JSON array or object at path '{label}', got {type_label}",
            details={"path": label},
        )

    def get_virtual_table_metadata(self, *, source_location: str) -> dict[str, Any]:
        rows = self.request_json_array(source_location=source_location)

        path_part = source_location.split("?")[0]
        segments = [s for s in path_part.split("/") if s.strip()]
        table_name = segments[-1] if segments else "http_api_source"

        sample_rows = rows[:SAMPLE_ROW_LIMIT]
        key_map: dict[str, set[str]] = {}

        for row in sample_rows:
            if not isinstance(row, dict):
                continue
            for k, v in row.items():
                if k not in key_map:
                    key_map[k] = set()
                if v is None:
                    continue
                if isinstance(v, bool):
                    key_map[k].add("boolean")
                elif isinstance(v, (int, float)) and not isinstance(v, bool):
                    key_map[k].add("number")
                else:
                    key_map[k].add("string")

        all_keys = sorted(key_map.keys())
        columns: list[dict[str, Any]] = []
        for idx, key in enumerate(all_keys):
            types = key_map.get(key) or set()
            inferred = "string"
            if len(types) == 1:
                if "number" in types:
                    inferred = "double"
                elif "boolean" in types:
                    inferred = "boolean"

            columns.append(
                {
                    "name": key,
                    "ordinal": idx + 1,
                    "dataType": inferred,
                    "maxLength": None,
                    "numericPrecision": None,
                    "numericScale": None,
                    "isNullable": True,
                    "isPrimaryKey": key.lower() == "id",
                }
            )

        return {
            "schema": "api",
            "name": table_name,
            "type": "BASE TABLE",
            "columns": columns,
        }

    def _build_url(self, source_location: str) -> str:
        src = (source_location or "").strip()
        if src.lower().startswith(("http://", "https://")):
            return src
        base = str(self._config.get("baseUrl") or "")
        if not base.strip():
            raise Datam8ValidationError(message="Missing baseUrl.", details=None)
        base = base.rstrip("/") + "/"
        loc = src.lstrip("/")
        return base + loc

    def _require_secret(self, key: str) -> str:
        v = (self._secrets.get(key) or "").strip()
        if not v:
            raise Datam8PermissionError(code="auth", message=f"Missing required secret '{key}'.", details=None)
        return v

    def _apply_auth(self, headers: dict[str, str]) -> None:
        auth = self._config.get("auth") if isinstance(self._config.get("auth"), dict) else {}
        kind = auth.get("kind") if isinstance(auth.get("kind"), str) else "none"

        if kind == "none":
            return
        if kind == "api-key-header":
            header_name = auth.get("headerName") if isinstance(auth.get("headerName"), str) else ""
            if not header_name.strip():
                raise Datam8ValidationError(message="auth.headerName is required for api-key-header.", details=None)
            headers[header_name] = self._require_secret("apiKey")
            return
        if kind == "basic":
            username = auth.get("username") if isinstance(auth.get("username"), str) else ""
            if not username.strip():
                raise Datam8ValidationError(message="auth.username is required for basic auth.", details=None)
            password = self._require_secret("password")
            creds = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
            headers["authorization"] = f"Basic {creds}"
            return
        if kind == "bearer-static":
            headers["authorization"] = f"Bearer {self._require_secret('token')}"
            return
        if kind == "oauth2-client-credentials":
            headers["authorization"] = f"Bearer {self._get_oauth_token()}"
            return

        raise Datam8ValidationError(message="Unsupported auth.kind.", details={"kind": kind})

    def _get_oauth_token(self) -> str:
        httpx = _import_httpx()
        now_ms = int(time.time() * 1000)
        if self._token_cache and now_ms < (self._token_cache.expires_at_ms - TOKEN_EXPIRY_SKEW_MS):
            return self._token_cache.access_token

        auth = self._config.get("auth") if isinstance(self._config.get("auth"), dict) else {}
        token_url = auth.get("tokenUrl") if isinstance(auth.get("tokenUrl"), str) else ""
        client_id = auth.get("clientId") if isinstance(auth.get("clientId"), str) else ""
        scope = auth.get("scope") if isinstance(auth.get("scope"), str) else None
        if not token_url.strip() or not client_id.strip():
            raise Datam8ValidationError(message="auth.tokenUrl and auth.clientId are required for oauth2.", details=None)

        client_secret = self._require_secret("clientSecret")
        timeout_ms = int(
            self._config.get("tokenRequestTimeoutMs")
            or self._config.get("requestTimeoutMs")
            or DEFAULT_REQUEST_TIMEOUT_MS
        )

        data = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
        if scope and scope.strip():
            data["scope"] = scope.strip()

        try:
            with self._client(timeout_ms=timeout_ms, httpx=httpx) as client:
                resp = client.post(token_url, data=data, headers={"content-type": "application/x-www-form-urlencoded"})
                resp.raise_for_status()
                token_data = resp.json()
        except httpx.TimeoutException:
            raise Datam8ExternalSystemError(
                code="oauth_timeout",
                message=f"Request timeout after {timeout_ms} ms for {token_url}",
                details={"url": token_url, "timeoutMs": timeout_ms},
            )
        except httpx.HTTPStatusError as e:
            text = (e.response.text or "").strip()
            msg = f"Failed to obtain access token ({e.response.status_code} {e.response.reason_phrase})"
            if text:
                msg = f"{msg}: {text}"
            raise Datam8ExternalSystemError(code="oauth_error", message=msg, details={"url": token_url, "status": e.response.status_code})
        except Exception as e:
            raise Datam8ExternalSystemError(code="oauth_error", message="Failed to obtain access token.", details={"url": token_url, "error": str(e)})

        access_token = token_data.get("access_token") if isinstance(token_data, dict) else None
        if not isinstance(access_token, str) or not access_token.strip():
            raise Datam8ExternalSystemError(code="oauth_error", message="No access_token in OAuth2 response.", details={"url": token_url})

        raw_expires = token_data.get("expires_in") if isinstance(token_data, dict) else None
        expires_in_s: int | None = None
        if isinstance(raw_expires, (int, float)) and raw_expires > 0:
            expires_in_s = int(raw_expires)
        elif isinstance(raw_expires, str) and raw_expires.strip().isdigit():
            expires_in_s = int(raw_expires.strip())

        expires_at_ms = now_ms + (expires_in_s * 1000 if expires_in_s else 3_600_000)
        self._token_cache = _OAuthTokenCache(access_token=access_token, expires_at_ms=expires_at_ms)
        return access_token

    def _client(self, *, timeout_ms: int, httpx: Any) -> Any:
        if self._http_client_factory:
            return self._http_client_factory()
        return httpx.Client(timeout=timeout_ms / 1000.0, follow_redirects=True)


def _import_httpx():
    try:
        import httpx  # type: ignore

        return httpx
    except ModuleNotFoundError as e:
        raise Datam8ExternalSystemError(
            code="missing_dependency",
            message="HTTP API connector requires optional dependency 'httpx'.",
            details={"package": "httpx"},
            hint="Install missing Python dependencies for the connector and restart the backend.",
        ) from e


def create_http_api_connector(config: dict[str, Any], runtime_secrets: dict[str, str]) -> HttpApiRestConnector:
    auth = config.get("auth") if isinstance(config.get("auth"), dict) else {}
    if "kind" not in auth:
        config = dict(config)
        config["auth"] = {**auth, "kind": "none"}
    return HttpApiRestConnector(config, runtime_secrets)
