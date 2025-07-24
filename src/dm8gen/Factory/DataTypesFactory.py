import sys
import json

from ..Generated.DataTypes import Model as DataTypes
from ..Helper.Helper import Helper
import logging

logger = logging.getLogger(__name__)


class DataTypesFactory:
    """Factory class for Data Types."""

    json: json = None
    data_types_object: object = None
    errors: list = []
    log_level: logging.log = None

    def __init__(self, path: str, log_level: logging.log = logging.INFO) -> None:
        """Initialize the DataTypesFactory.

        Args:
            path (str): The path to the file.
            log_level (logging.log, optional): The logging level. Defaults to logging.INFO.
        """
        try:
            self.logger: logging.Logger = Helper.start_logger(
                self.__class__.__name__, log_level=log_level
            )
            self.json = Helper.read_json(path)
            self.data_types_object = self.__get_object()

        except Exception as e:
            self.__error_handler(str(e))

    def __error_handler(self, msg: str):
        """Handle errors.

        Args:
            msg (str): The error message.
        """
        self.errors.append(f"Error DataTypeFactory: {msg}")
        self.logger.error(msg)
        sys.exit()

    def __get_object(self) -> object:
        """Get the data types object.

        Returns:
            object: The data types object.
        """
        __object = DataTypes.model_validate_json(json.dumps(self.json))
        return __object

    def get_data_type(self, datatype_name: str) -> DataTypes:
        """Get the data type.

        Args:
            datatype_name (str): The name of the data type.

        Returns:
            DataType: The data type.
        """
        try:
            __data_type_item = None
            __ls_mapping = [
                i
                for i in self.data_types_object.dataTypes
                if getattr(i, "name") == datatype_name
            ]

            if len(__ls_mapping) == 0:
                self.__error_handler(
                    f"Found no datatype for property_key: name with value: {datatype_name}"
                )
            elif len(__ls_mapping) > 1:
                self.__error_handler(
                    f"Found multiple datatypes for property_key: name with value: {datatype_name}"
                )

            __data_type_item = __ls_mapping[0]

            return __data_type_item

        except Exception as e:
            self.__error_handler(str(e))

    def get_data_type_list(
        self, property_key: str, property_value: str
    ) -> list[DataTypes]:
        """Get a list of data types.

        Args:
            property_key (str): The property key.
            property_value (str): The property value.

        Returns:
            list[DataType]: A list of data types.
        """
        try:
            __ls_mapping: list[DataTypes] = None
            __ls_mapping = [
                i
                for i in self.data_types_object.dataTypes
                if getattr(i, property_key) == property_value
            ]

            return __ls_mapping

        except Exception as e:
            self.__error_handler(str(e))
