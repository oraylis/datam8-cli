import json
from ..Generated.AttributeTypes import Model as AttributeTypes
from ..Helper.Helper import Helper
import logging

logger = logging.getLogger(__name__)


class AttributeTypesFactory:
    json: json = None
    attribute_types_object: object = None
    errors: list = []
    log_level: logging.log = None

    def __init__(self, path: str, log_level: logging.log = logging.INFO) -> None:
        try:
            self.logger = Helper.start_logger(
                self.__class__.__name__, log_level=log_level
            )
            self.json = Helper.read_json(path)
            self.attribute_types_object = self.__get_object()

        except Exception as e:
            self.__error_handler(str(e))

    def __error_handler(self, msg: str):
        self.errors.append(f"Error DataSourceFactory: {msg}")
        self.logger.error(msg)

    def __get_object(self) -> object:

        __object = AttributeTypes.model_validate_json(json.dumps(self.json))

        return __object

    def get_attribute(self, attribute_name) -> AttributeTypes:

        try:
            __attribute_item = None
            __attribute_item = [
                i for i in self.attribute_types_object.attributeTypes if i.name == attribute_name
            ][0]

            if __attribute_item is None:
                self.__error_handler(
                    f"Found no Source item for source name: {attribute_name}"
                )

            return __attribute_item

        except Exception as e:
            self.__error_handler(str(e))
