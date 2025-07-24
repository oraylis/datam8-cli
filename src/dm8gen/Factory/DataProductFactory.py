import json
from ..Generated.DataProducts import Model as DataProducts
from ..Helper.Helper import Helper
import logging

logger = logging.getLogger(__name__)


class DataproductFactory:
    """Factory class for Data Products."""

    json: json = None
    data_product_object: object = None
    errors: list = []
    log_level: logging.log = None

    def __init__(self, path: str, log_level: logging.log = logging.INFO) -> None:
        """Initialize the DataproductFactory.

        Args:
            path (str): The path to the file.
            log_level (logging.log, optional): The logging level. Defaults to logging.INFO.
        """
        try:
            self.logger: logging.Logger = Helper.start_logger(
                self.__class__.__name__, log_level=log_level
            )
            self.json = Helper.read_json(path)
            self.data_product_object = self.__get_object()

        except Exception as e:
            self.__error_handler(str(e))

    def __error_handler(self, msg: str):
        """Handle errors.

        Args:
            msg (str): The error message.
        """
        self.errors.append(f"Error DataproductFactory: {msg}")
        self.logger.error(msg)

    def __get_object(self) -> object:
        """Get the data product object.

        Returns:
            object: The data product object.
        """
        __object = DataProducts.model_validate_json(json.dumps(self.json))
        return __object

    def get_data_product(self, data_product_name) -> DataProducts:
        """Get the data product.

        Args:
            data_product_name: The name of the data product.

        Returns:
            DataProduct: The data product.
        """
        try:
            __data_product_item = None
            __data_product_item = [
                i for i in self.data_product_object.dataProducts if i.name == data_product_name
            ][0]

            if __data_product_item is None:
                self.__error_handler(f"Found no item for product: {data_product_name}")

            return __data_product_item

        except Exception as e:
            self.__error_handler(str(e))
