import json
from ..Generated.DataSourceTypes import Model as DataSourceTypes
from ..Helper.Helper import Helper
import logging

logger = logging.getLogger(__name__)


class DataSourceTypesFactory:
    """Factory class for Data Source Types."""

    json: json = None
    data_source_types_object: object = None
    errors: list = []
    log_level: logging.log = None

    def __init__(self, path: str, log_level: logging.log = logging.INFO) -> None:
        """Initialize the DataSourceTypesFactory.

        Args:
            path (str): The path to the file.
            log_level (logging.log, optional): The logging level. Defaults to logging.INFO.
        """
        try:
            self.logger: logging.Logger = Helper.start_logger(
                self.__class__.__name__, log_level=log_level
            )
            self.json = Helper.read_json(path)
            self.data_source_types_object = self.__get_object()

        except Exception as e:
            self.__error_handler(str(e))

    def __error_handler(self, msg: str):
        """Handle errors.

        Args:
            msg (str): The error message.
        """
        self.errors.append(f"Error DataSourceTypesFactory: {msg}")
        self.logger.error(msg)

    def __get_object(self) -> object:
        """Get the data source types object.

        Returns:
            object: The data source types object.
        """
        __object = DataSourceTypes.model_validate_json(json.dumps(self.json))
        return __object

    def get_datasource_type(self, type_name: str) -> DataSourceTypes:
        """Get the data source type by name.

        Args:
            type_name (str): The name of the data source type.

        Returns:
            DataSourceTypes: The data source type.
        """
        try:
            __type_item = None
            __type_item = [
                i for i in self.data_source_types_object.dataSourceTypes if i.name == type_name
            ][0]

            if __type_item is None:
                self.__error_handler(
                    f"Found no data source type for name: {type_name}"
                )

            return __type_item

        except Exception as e:
            self.__error_handler(str(e))

    def get_datasource_type_list(self) -> list[DataSourceTypes]:
        """Get a list of all data source types.

        Returns:
            list[DataSourceTypes]: A list of data source types.
        """
        try:
            return self.data_source_types_object.dataSourceTypes
        except Exception as e:
            self.__error_handler(str(e))

    def get_default_type_mapping(self, type_name: str, source_type: str) -> str:
        """Get the default type mapping for a source type.

        Args:
            type_name (str): The name of the data source type.
            source_type (str): The source data type to map.

        Returns:
            str: The target data type, or None if no mapping found.
        """
        try:
            datasource_type = self.get_datasource_type(type_name)
            
            if datasource_type and datasource_type.dataTypeMapping:
                for mapping in datasource_type.dataTypeMapping:
                    if mapping.sourceType == source_type:
                        return mapping.targetType
            
            self.logger.debug(f"No type mapping found for {source_type} in {type_name}")
            return None

        except Exception as e:
            self.__error_handler(str(e))
            return None

    def get_connection_properties(self, type_name: str) -> list:
        """Get the connection properties for a data source type.

        Args:
            type_name (str): The name of the data source type.

        Returns:
            list: List of connection properties, or empty list if none found.
        """
        try:
            datasource_type = self.get_datasource_type(type_name)
            
            if datasource_type and datasource_type.connectionProperties:
                return datasource_type.connectionProperties
            
            return []

        except Exception as e:
            self.__error_handler(str(e))
            return []

    def validate_connection_config(self, type_name: str, config: dict) -> bool:
        """Validate a connection configuration against the data source type requirements.

        Args:
            type_name (str): The name of the data source type.
            config (dict): The connection configuration to validate.

        Returns:
            bool: True if configuration is valid, False otherwise.
        """
        try:
            connection_properties = self.get_connection_properties(type_name)
            
            # Check required properties
            for prop in connection_properties:
                if prop.required and prop.name not in config:
                    self.logger.error(f"Required connection property '{prop.name}' missing for {type_name}")
                    return False
            
            return True

        except Exception as e:
            self.__error_handler(str(e))
            return False

    def get_required_properties(self, type_name: str) -> list[str]:
        """Get list of required property names for a data source type.

        Args:
            type_name (str): The name of the data source type.

        Returns:
            list[str]: List of required property names.
        """
        try:
            connection_properties = self.get_connection_properties(type_name)
            return [prop.name for prop in connection_properties if prop.required]
        except Exception as e:
            self.__error_handler(str(e))
            return []

    def get_optional_properties(self, type_name: str) -> list[str]:
        """Get list of optional property names for a data source type.

        Args:
            type_name (str): The name of the data source type.

        Returns:
            list[str]: List of optional property names.
        """
        try:
            connection_properties = self.get_connection_properties(type_name)
            return [prop.name for prop in connection_properties if not prop.required]
        except Exception as e:
            self.__error_handler(str(e))
            return []