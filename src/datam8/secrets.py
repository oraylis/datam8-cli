# DataM8
# Copyright (C) 2024-2025 ORAYLIS GmbH
#
# This file is part of DataM8.
#
# DataM8 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# DataM8 is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

import os
from contextlib import suppress
from pathlib import PurePosixPath
from threading import Lock

import keyring

from datam8 import config, logging, utils

logger = logging.getLogger(__name__)


class SecretResolver:
    __instance: "SecretResolver | None" = None
    __lock = Lock()

    def __new__(cls) -> "SecretResolver":
        if cls.__instance is None:
            with cls.__lock:
                if cls.__instance is None:
                    cls.__instance = super().__new__(cls)

        return cls.__instance

    @classmethod
    def reset_singleton(cls) -> None:
        with cls.__lock:
            cls.__instance = None

    def __init__(self) -> None:
        self.__service_name = f"datam8:{config.get_name()}"
        self.__username = os.getlogin()
        self.lock = Lock()

    #
    # private methods with thread safety
    #

    def __set_password(self, service: str, value: str, /) -> None:
        logger.debug("Setting '%s'", service)
        keyring.set_password(service, self.__username, value)

    def __get_password(self, service: str, /) -> str | None:
        logger.debug("Getting '%s'", service)
        return keyring.get_password(service, self.__username)

    def __unset_password(self, service: str, /) -> None:
        logger.debug("Unsetting '%s'", service)
        keyring.delete_password(service, self.__username)

    def __register_secret(self, path: PurePosixPath, /) -> None:
        service_name = self.__create_service_name()
        secrets = self.__get_password(service_name)

        logger.debug(f"Before register: {secrets}")

        if secrets is None or secrets == "":
            secrets = path.as_posix()
        else:
            secrets = f"{secrets},{path.as_posix()}"

        self.__set_password(service_name, secrets)
        logger.debug(f"After register: {secrets}")

    def __unregister_secret(self, path: PurePosixPath, /) -> None:
        service_name = self.__create_service_name()
        current_secrets = self.__get_password(service_name)
        current_secrets = [] if current_secrets is None else current_secrets.split(",")
        posix_path = path.as_posix()

        logger.debug(f"Before unregister: {current_secrets}")

        if posix_path not in current_secrets:
            logger.warning("Trying to unregister non existing secret")
            return

        path_index = current_secrets.index(posix_path)
        current_secrets.pop(path_index)

        logger.debug(f"After unregister: {current_secrets}")

        self.__set_password(service_name, ",".join(current_secrets))

    def __create_service_name(self, path: PurePosixPath | None = None, /) -> str:
        if path is None:
            return f"{self.__service_name}"
        return f"{self.__service_name}/{path.as_posix()}"

    #
    # public methods - enforcing thread safety
    #

    def set_secret(self, path: PurePosixPath, value: str, /, *, force: bool = False) -> None:
        "Set a new secret or overwrite an existing one"
        service_name = self.__create_service_name(path)

        with self.lock:
            existing_secret = self.get_secret(path)

            if existing_secret is not None and not force:
                raise utils.create_error(f"Trying to set secret but it already exists: {path}")

            self.__set_password(service_name, value)
            self.__register_secret(path)

    def unset_secret(self, path: PurePosixPath, /) -> None:
        "Remove a secret from the keyring backend"
        service_name = self.__create_service_name(path)

        with self.lock:
            existing_secret = self.get_secret(path)
            self.__unregister_secret(path)

            if existing_secret is None:
                raise utils.create_error(f"Trying to unset non existing secret: {path}")

            self.__unset_password(service_name)

    def list_secrets(self) -> list[PurePosixPath]:
        "Returns a list of available secrets"
        service_name = self.__create_service_name()

        with self.lock:
            secrets = self.__get_password(service_name)

        if secrets is None or len(secrets) == 0:
            return []

        secret_list = secrets.split(",")

        logger.debug("Secret registry: '%s' [%s]", secrets, len(secret_list))

        return [PurePosixPath(p) for p in secret_list]

    def get_secret(self, path: PurePosixPath, /) -> str | None:
        service_name = self.__create_service_name(path)
        secret = keyring.get_password(service_name, self.__username)
        return secret

    def clean(self) -> None:
        secrets = self.list_secrets()
        with suppress(Exception), self.lock:
            for s in secrets:
                self.__unset_password(self.__create_service_name(s))
            self.__unset_password(self.__create_service_name())
