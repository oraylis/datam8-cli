import json
from ..Generated.DataSources import Model as DataSources
from ..Helper.Helper import Helper
import logging

logger = logging.getLogger(__name__)


class DataSourceFactory:
    """Factory class for Data Sources."""

    CACHE_MAPPING: dict = {}

    json: json = None
    source_object: object = None
    errors: list = []
    log_level: logging.log = None

    def __init__(
        self, path: str, log_level: logging.log = logging.INFO
    ) -> None:
        """Initialize the DataSourceFactory.

        Args:
            path (str): The path to the file.
            log_level (logging.log, optional): The logging level. Defaults to logging.INFO.
        """
        try:
            self.logger: logging.Logger = Helper.start_logger(
                self.__class__.__name__, log_level=log_level
            )
            self.json = Helper.read_json(path)
            self.source_object = self.__get_object()

        except Exception as e:
            self.__error_handler(e)

    def __error_handler(self, msg: str):
        """Handle errors.

        Args:
            msg (str): The error message.
        """
        self.errors.append(f"Error DataSourceFactory: {msg}")
        self.logger.error(msg)

    def __get_object(self) -> object:
        """Get the data source object.

        Returns:
            object: The data source object.
        """
        __object = DataSources.model_validate_json(json.dumps(self.json))
        return __object

    def get_datasource(self, source_name) -> DataSources:
        """Get the data source.

        Args:
            source_name: The name of the data source.

        Returns:
            DataSource: The data source.
        """
        try:
            __source_item = None
            __source_item = [
                i for i in self.source_object.dataSources if i.name == source_name
            ][0]

            if __source_item is None:
                self.__error_handler(
                    f"Found no Source item for source name: {source_name}"
                )

            return __source_item

        except Exception as e:
            self.__error_handler(e)

    def get_datasource_list(self) -> list[DataSources]:
        """Get a list of all data sources.

        Returns:
            list[DataSource]: A list of data sources.
        """
        try:
            return self.source_object.dataSources
        except Exception as e:
            self.__error_handler(e)

    def get_datasource_target_type(self, source_name: str, source_type) -> str:
        """Get the target type of the data source.

        Args:
            source_name (str): The name of the data source.
            source_type: The source type.

        Returns:
            str: The target type of the data source.
        """
        cache_key = "%s:%s" % (source_name, source_type)
        if cache_key in DataSourceFactory.CACHE_MAPPING:
            self.logger.debug("Cached mapping return for %s" % cache_key)
            return DataSourceFactory.CACHE_MAPPING[cache_key]

        try:
            __source_item = self.get_datasource(source_name=source_name)
            __ls_target_type = [
                i.targetType
                for i in __source_item.dataTypeMapping
                if i.sourceType == source_type
            ]
            if len(__ls_target_type) == 1:
                __target_type = __ls_target_type[0]
                self.logger.debug(
                    f"Mapping Datasource {source_name} from sourceType: {source_type} to targetType: {__target_type}"
                )
            else:
                __target_type = ""
                self.__error_handler(
                    f"Invalid Mapping Datasource {source_name} from sourceType: {source_type} to targetType: {__ls_target_type}"
                )

            DataSourceFactory.CACHE_MAPPING[cache_key] = __target_type
            return __target_type

        except Exception as e:
            self.__error_handler(e)
