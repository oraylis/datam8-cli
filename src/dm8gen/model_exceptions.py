class EntityNotFoundError(Exception):
    def __init__(
        self,
        entity: str,
        msg: str = "Entity was not found in model: {}",
        inner_exceptions: list[Exception] | None = None,
    ):
        Exception.__init__(self, msg.format(entity))

        self.inner_exceptions = inner_exceptions
        self.message = msg.format(entity)


class InvalidLocatorError(Exception):
    def __init__(self, locator: str):
        super().__init__(f"Not a valid locator: {locator}")


class PropertiesNotResolvedError(Exception):
    def __init__(self, locator):
        super().__init__(
            f"Tried to access properties of unresolved entity '{locator}' yet"
        )
