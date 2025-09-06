class ModelParseException(Exception):
    def __init__(
        self,
        msg="Error(s) occured during model files parsing.",
        inner_exceptions: list[Exception] = [],
    ):
        Exception.__init__(self, msg)

        self.inner_exceptions = inner_exceptions
        self.message = msg
