import json
from ..Generated.Zones import Model as Zones
from ..Helper.Helper import Helper
import logging

logger = logging.getLogger(__name__)


class ZonesFactory:
    """Factory class for Zones."""

    json: json = None
    zones_object: object = None
    errors: list = []
    log_level: logging.log = None

    def __init__(self, path: str, log_level: logging.log = logging.INFO) -> None:
        """Initialize the ZonesFactory.

        Args:
            path (str): The path to the file.
            log_level (logging.log, optional): The logging level. Defaults to logging.INFO.
        """
        try:
            self.logger: logging.Logger = Helper.start_logger(
                self.__class__.__name__, log_level=log_level
            )
            self.json = Helper.read_json(path)
            self.zones_object = self.__get_object()

        except Exception as e:
            self.__error_handler(str(e))

    def __error_handler(self, msg: str):
        """Handle errors.

        Args:
            msg (str): The error message.
        """
        self.errors.append(f"Error ZonesFactory: {msg}")
        self.logger.error(msg)

    def __get_object(self) -> object:
        """Get the zones object.

        Returns:
            object: The zones object.
        """
        __object = Zones.model_validate_json(json.dumps(self.json))
        return __object

    def get_zone(self, zone_name: str) -> Zones:
        """Get the zone by logical name.

        Args:
            zone_name (str): The logical name of the zone (e.g., 'Raw', 'Core', 'Curated').

        Returns:
            Zones: The zone definition.
        """
        try:
            __zone_item = None
            __zone_item = [
                i for i in self.zones_object.zones if i.name == zone_name
            ][0]

            if __zone_item is None:
                self.__error_handler(
                    f"Found no zone for name: {zone_name}"
                )

            return __zone_item

        except Exception as e:
            self.__error_handler(str(e))

    def get_zone_list(self) -> list[Zones]:
        """Get a list of all zones.

        Returns:
            list[Zones]: A list of zones.
        """
        try:
            return self.zones_object.zones
        except Exception as e:
            self.__error_handler(str(e))

    def get_target_name(self, logical_name: str) -> str:
        """Get the target name for a logical zone name.

        Args:
            logical_name (str): The logical zone name (e.g., 'Raw', 'Core').

        Returns:
            str: The target name (e.g., 'Bronze', 'Silver'), or None if not found.
        """
        try:
            zone = self.get_zone(logical_name)
            
            if zone:
                return zone.targeName
            
            return None

        except Exception as e:
            self.__error_handler(str(e))
            return None

    def get_folder_structure(self, zone_name: str) -> str:
        """Get the local folder name for a zone.

        Args:
            zone_name (str): The logical zone name.

        Returns:
            str: The local folder name (e.g., '010-Raw'), or None if not found.
        """
        try:
            zone = self.get_zone(zone_name)
            
            if zone:
                return zone.localFolderName
            
            return None

        except Exception as e:
            self.__error_handler(str(e))
            return None

    def get_display_name(self, zone_name: str) -> str:
        """Get the display name for a zone.

        Args:
            zone_name (str): The logical zone name.

        Returns:
            str: The display name, or None if not found.
        """
        try:
            zone = self.get_zone(zone_name)
            
            if zone:
                return zone.displayName
            
            return None

        except Exception as e:
            self.__error_handler(str(e))
            return None

    def get_zone_by_target(self, target_name: str) -> Zones:
        """Get zone by target name (reverse lookup).

        Args:
            target_name (str): The target name (e.g., 'Bronze', 'Silver').

        Returns:
            Zones: The zone definition, or None if not found.
        """
        try:
            __zone_item = None
            __zone_item = [
                i for i in self.zones_object.zones if i.targeName == target_name
            ][0]

            if __zone_item is None:
                self.__error_handler(
                    f"Found no zone for target name: {target_name}"
                )

            return __zone_item

        except Exception as e:
            self.__error_handler(str(e))
            return None

    def get_zone_by_folder(self, folder_name: str) -> Zones:
        """Get zone by local folder name.

        Args:
            folder_name (str): The local folder name (e.g., '010-Raw').

        Returns:
            Zones: The zone definition, or None if not found.
        """
        try:
            __zone_item = None
            __zone_item = [
                i for i in self.zones_object.zones if i.localFolderName == folder_name
            ][0]

            if __zone_item is None:
                self.__error_handler(
                    f"Found no zone for folder name: {folder_name}"
                )

            return __zone_item

        except Exception as e:
            self.__error_handler(str(e))
            return None

    def get_zone_names(self) -> list[str]:
        """Get list of all logical zone names.

        Returns:
            list[str]: List of logical zone names.
        """
        try:
            return [zone.name for zone in self.zones_object.zones]
        except Exception as e:
            self.__error_handler(str(e))
            return []

    def get_target_names(self) -> list[str]:
        """Get list of all target names.

        Returns:
            list[str]: List of target names.
        """
        try:
            return [zone.targeName for zone in self.zones_object.zones]
        except Exception as e:
            self.__error_handler(str(e))
            return []