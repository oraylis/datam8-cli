"""Central allocation and validation of model and folder entity IDs."""

import secrets
from threading import Lock

from datam8.errors import Datam8ValidationError

MAX_ENTITY_ID = (1 << 53) - 1
_lock = Lock()


def generate_entity_id(used_ids: set[int]) -> int:
    with _lock:
        while True:
            entity_id = secrets.randbelow(MAX_ENTITY_ID) + 1
            if entity_id not in used_ids:
                used_ids.add(entity_id)
                return entity_id


def validate_entity_id(value: object, *, locator: str) -> None:
    if type(value) is not int or not 1 <= value <= MAX_ENTITY_ID:
        raise Datam8ValidationError(
            message=f"Invalid entity ID {value!r} at {locator}; expected an integer in 1..{MAX_ENTITY_ID}",
            details={"id": repr(value), "locator": locator},
        )
