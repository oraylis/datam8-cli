"""
Wrapper around python's builtin hashlib module for direct usage within jinja2 templates.
"""

import hashlib
from enum import Enum
from uuid import UUID


class Algorithm(Enum):
    SHA256 = 0


class UnknownAlgorithmExpcetion(Exception):
    def __ini__(self, algorithm: str):
        super().__init__(f"Unkown algorithm: {algorithm}")


class Hasher:
    __algorithm: Algorithm

    @property
    def algorithm(self) -> Algorithm:
        return self.__algorithm

    def __init__(self, algorithm: str = Algorithm.SHA256.name) -> None:
        if algorithm not in Algorithm._member_names_:
            raise UnknownAlgorithmExpcetion(algorithm)

        self.__algorithm = Algorithm(algorithm)

    def hash(self, input: str) -> hashlib._Hash:
        input_encoded = input.encode()

        match self.__algorithm:
            case Algorithm.SHA256:
                hash_object = hashlib.sha256(input_encoded)

        return hash_object

    def create_uuid(self, input: str) -> UUID:
        hash = self.hash(input)

        if self.__algorithm == Algorithm.SHA256:
            uuid = UUID(hash.hexdigest()[::2])
        else:
            uuid = UUID(hash.hexdigest())

        return uuid
