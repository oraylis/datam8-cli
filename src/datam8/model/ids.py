"""Model entity IDs shared by loading, creation and updates."""

from datam8.errors import Datam8ValidationError

MAX_MODEL_ENTITY_ID = (1 << 53) - 1


def validate_model_entity_id(value: object, *, locator: str) -> None:
    if type(value) is not int or not 1 <= value <= MAX_MODEL_ENTITY_ID:
        raise Datam8ValidationError(
            message=(
                f"Invalid model entity ID {value!r} at {locator}; "
                f"expected an integer in 1..{MAX_MODEL_ENTITY_ID}"
            ),
            details={"id": value, "locator": locator},
        )
