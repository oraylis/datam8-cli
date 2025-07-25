import os.path
import json
import re
import sys
from typing import Union
from dataclasses import dataclass
import textwrap
from .DataSourceFactory import DataSourceFactory
from .AttributeTypesFactory import AttributeTypesFactory
from .DataModuleFactory import DataModuleFactory
from .DataTypesFactory import DataTypesFactory
from .DataSourceTypesFactory import DataSourceTypesFactory
from .ZonesFactory import ZonesFactory
from .UnifiedEntityFactory import UnifiedEntityFactory
from ..Generated.Solution import Model as Solution
from ..Generated.Index import Model as Index
from ..Helper.Helper import Helper, JsonFileParseException
import logging

logger = logging.getLogger(__name__)


class Model:
    CACHE_DATA_SOURCE: dict = {}
    CACHE_ATTRIBUTE_TYPES: dict = {}
    CACHE_DATA_MODULE: dict = {}
    CACHE_DATA_TYPES: dict = {}
    CACHE_DATA_SOURCE_TYPES: dict = {}
    CACHE_ZONES: dict = {}

    path_solution: str = None
    dict_solution: str = None
    errors: list = []
    log_level: logging.log = None

    def __init__(
        self, path_solution: str, log_level: logging.log = logging.INFO
    ):
        self.log_level = log_level
        self.logger: logging.Logger = Helper.start_logger(
            self.__class__.__name__, log_level=log_level
        )
        self.path_solution = os.path.abspath(path_solution)
        self.dict_solution = os.path.dirname(self.path_solution)
        self.path_index = os.path.join(self.dict_solution, "index.json")
        
        # Validate zones configuration on initialization
        self._validate_zones_configuration()

    @property
    def solution(self) -> Solution:
        try:
            solution_object = Solution.model_validate_json(
                json.dumps(Helper.read_json(path=self.path_solution))
            )
            # self.logger.info('Successfully init Solution object')
            return solution_object
        except Exception as e:
            self.__error_handler(e)


    @property
    def path_base(self) -> str:
        try:
            base_path = self.__get_dict_path(dict_item=self.solution.basePath)
            # self.logger.info(f'Requested base path: {base_path}')
            return base_path
        except Exception as e:
            self.__error_handler(e)

    @property
    def path_raw(self) -> str:
        try:
            # Raw zone special case: path uses dynamic zone system but entities derived from staging
            model_path = self.__get_dict_path(dict_item=self.solution.modelPath)
            # Use "Raw" folder for backward compatibility - raw entities are derived from staging
            raw_path = os.path.join(model_path, "Raw")
            self.logger.debug(f"Requested raw path (entities derived from staging): {raw_path}")
            return raw_path
        except Exception as e:
            self.__error_handler(e)

    @property
    def path_stage(self) -> str:
        """Get stage path using dynamic zone system."""
        return self.get_zone_path("stage")

    @property
    def path_core(self) -> str:
        """Get core path using dynamic zone system."""
        return self.get_zone_path("core")

    @property
    def path_curated(self) -> str:
        """Get curated path using dynamic zone system."""
        return self.get_zone_path("curated")

    @property
    def path_generate(self) -> str:
        try:
            generate_path = self.__get_dict_path(
                dict_item=self.solution.generatePath
            )
            # self.logger.info(f'Requested generate path: {generate_path}')
            return generate_path
        except Exception as e:
            self.__error_handler(e)

    @property
    def path_output(self) -> str:
        try:
            output_path = self.__get_dict_path(
                dict_item=self.solution.outputPath
            )
            # self.logger.info(f'Requested output path: {output_path}')
            return output_path
        except Exception as e:
            self.__error_handler(e)

    def get_zone_path(self, zone_name: str) -> str:
        """Get the full path for a specific zone using dynamic zone system.
        
        Args:
            zone_name (str): The logical zone name from Zones.json.
            
        Returns:
            str: The full path to the zone directory.
            
        Raises:
            ValueError: If the zone is not found in Zones.json.
        """
        return self.get_zone_path_dynamic(zone_name)

    def get_zone_folder(self, zone_name: str) -> str:
        """Get the local folder name for a specific zone.
        
        Args:
            zone_name (str): The logical zone name (e.g., 'stage', 'core', 'curated').
            
        Returns:
            str: The local folder name (e.g., '010-Staging', '020-Core').
            
        Raises:
            ValueError: If the zone is not found in Zones.json.
        """
        try:
            zone_folder = self.zones.get_folder_structure(zone_name)
            if not zone_folder:
                raise ValueError(f"Zone '{zone_name}' not found in Zones.json - zone configuration is required")
            return zone_folder
        except Exception as e:
            self.__error_handler(e)
            raise

    def get_zone_target_name(self, zone_name: str) -> str:
        """Get the target platform name for a specific zone.
        
        Args:
            zone_name (str): The logical zone name (e.g., 'stage', 'core', 'curated').
            
        Returns:
            str: The target platform name (e.g., 'bronze', 'silver', 'gold').
            
        Raises:
            ValueError: If the zone is not found in Zones.json.
        """
        try:
            target_name = self.zones.get_target_name(zone_name)
            if not target_name:
                raise ValueError(f"Zone '{zone_name}' not found in Zones.json - zone configuration is required")
            return target_name
        except Exception as e:
            self.__error_handler(e)
            raise

    def get_zone_display_name(self, zone_name: str) -> str:
        """Get the display name for a specific zone.
        
        Args:
            zone_name (str): The logical zone name (e.g., 'stage', 'core', 'curated').
            
        Returns:
            str: The display name (e.g., 'Staging Data Layer', 'Core Business Layer').
            
        Raises:
            ValueError: If the zone is not found in Zones.json.
        """
        try:
            display_name = self.zones.get_display_name(zone_name)
            if not display_name:
                raise ValueError(f"Zone '{zone_name}' not found in Zones.json - zone configuration is required")
            return display_name
        except Exception as e:
            self.__error_handler(e)
            raise

    def _validate_zones_configuration(self) -> None:
        """Validate that all zones in Zones.json are properly configured.
        
        Raises:
            ValueError: If zones are missing required fields or misconfigured.
        """
        try:
            missing_zones = []
            
            # Dynamic validation - check all zones defined in Zones.json
            for zone in self.zones.get_zone_list():
                zone_name = zone.name
                try:
                    zone_target = self.zones.get_target_name(zone_name)
                    zone_display = self.zones.get_display_name(zone_name)
                    
                    if not zone_target:
                        missing_zones.append(f"{zone_name} (missing targeName)")
                    if not zone_display:
                        missing_zones.append(f"{zone_name} (missing displayName)")
                    
                    # Validate localFolderName for all zones
                    zone_folder = self.zones.get_folder_structure(zone_name)
                    if not zone_folder:
                        missing_zones.append(f"{zone_name} (missing localFolderName)")
                        
                except Exception:
                    missing_zones.append(f"{zone_name} (zone validation failed)")
            
            if missing_zones:
                raise ValueError(
                    f"Zones configuration validation failed. Missing or incomplete zones: {', '.join(missing_zones)}. "
                    "Please ensure all zones are properly defined in Zones.json"
                )
                
            self.logger.info(f"Zones configuration validation passed for {len(self.zones.get_zone_list())} zones")
            
        except Exception as e:
            self.logger.error(f"Zones validation failed: {e}")
            raise

    @property
    def zone_paths(self) -> dict[str, str]:
        """Get all configured zone paths dynamically.
        
        Returns:
            dict[str, str]: Dictionary mapping zone names to their full paths.
        """
        try:
            paths = {}
            model_path = self.__get_dict_path(dict_item=self.solution.modelPath)
            
            for zone in self.zones.get_zone_list():
                zone_name = zone.name
                
                # Special case for raw zone - uses "Raw" folder for entity discovery
                if zone_name == "raw":
                    paths[zone_name] = os.path.join(model_path, "Raw")
                else:
                    # Other zones use their localFolderName
                    if hasattr(zone, 'localFolderName') and zone.localFolderName:
                        paths[zone_name] = os.path.join(model_path, zone.localFolderName)
                    else:
                        raise ValueError(f"Zone '{zone_name}' missing localFolderName in Zones.json")
                        
            return paths
        except Exception as e:
            self.__error_handler(e)
            raise

    def get_zone_path_dynamic(self, zone_name: str) -> str:
        """Universal zone path lookup that works for any zone in Zones.json.
        
        Args:
            zone_name (str): The logical zone name from Zones.json.
            
        Returns:
            str: The full path to the zone directory.
            
        Raises:
            ValueError: If the zone is not found or misconfigured.
        """
        try:
            model_path = self.__get_dict_path(dict_item=self.solution.modelPath)
            
            # Special case for raw zone
            if zone_name == "raw":
                zone_path = os.path.join(model_path, "Raw")
                self.logger.debug(f"Requested {zone_name} zone path (special case): {zone_path}")
                return zone_path
            
            # Standard zones use localFolderName
            zone = self.zones.get_zone(zone_name)
            if not zone:
                raise ValueError(f"Zone '{zone_name}' not found in Zones.json")
                
            if not hasattr(zone, 'localFolderName') or not zone.localFolderName:
                raise ValueError(f"Zone '{zone_name}' missing localFolderName in Zones.json")
                
            zone_path = os.path.join(model_path, zone.localFolderName)
            self.logger.debug(f"Requested {zone_name} zone path: {zone_path}")
            return zone_path
            
        except Exception as e:
            self.__error_handler(e)
            raise

    @property
    def data_sources(self) -> DataSourceFactory:
        path_datasource: str = os.path.join(
            self.__get_dict_path(self.path_base), "DataSources.json"
        )

        if path_datasource in Model.CACHE_DATA_SOURCE:
            self.logger.debug(
                "Cached DataSourceFactory for %s" % path_datasource
            )
            return Model.CACHE_DATA_SOURCE[path_datasource]

        try:
            datasource_factory = DataSourceFactory(
                path=path_datasource, log_level=self.log_level
            )
            Model.CACHE_DATA_SOURCE[path_datasource] = datasource_factory
            self.logger.info(
                "Successfully init Datasource Factory from %s" % path_datasource
            )

            return datasource_factory
        except Exception as e:
            self.__error_handler(e)

    @property
    def attribute_types(self) -> AttributeTypesFactory:
        path_attribute_types: str = os.path.join(
            self.__get_dict_path(self.path_base), "AttributeTypes.json"
        )
        if path_attribute_types in Model.CACHE_ATTRIBUTE_TYPES:
            self.logger.debug(
                "Cached AttributeTypesFactory for %s" % path_attribute_types
            )
            return Model.CACHE_ATTRIBUTE_TYPES[path_attribute_types]

        try:
            attribute_types_factory = AttributeTypesFactory(
                path=path_attribute_types, log_level=self.log_level
            )
            Model.CACHE_ATTRIBUTE_TYPES[path_attribute_types] = (
                attribute_types_factory
            )
            self.logger.info(
                "Successfully init Attribute Factory from %s"
                % path_attribute_types
            )

            return attribute_types_factory
        except Exception as e:
            self.__error_handler(e)

    @property
    def data_modules(self) -> DataModuleFactory:
        path_data_modules: str = os.path.join(
            self.__get_dict_path(self.path_base), "DataModules.json"
        )
        if path_data_modules in Model.CACHE_DATA_MODULE:
            self.logger.debug(
                "Cached DataModuleFactory for %s" % path_data_modules
            )
            return Model.CACHE_DATA_MODULE[path_data_modules]

        try:
            data_modules_factory = DataModuleFactory(
                path=path_data_modules, log_level=self.log_level
            )
            Model.CACHE_DATA_MODULE[path_data_modules] = data_modules_factory
            self.logger.info(
                "Successfully init Data Module Factory from %s"
                % path_data_modules
            )

            return data_modules_factory
        except Exception as e:
            self.__error_handler(e)

    @property
    def data_types(self) -> DataTypesFactory:
        path_data_types: str = os.path.join(
            self.__get_dict_path(self.path_base), "DataTypes.json"
        )
        if path_data_types in Model.CACHE_DATA_TYPES:
            self.logger.debug(
                "Cached DataTypesFactory for %s" % path_data_types
            )
            return Model.CACHE_DATA_TYPES[path_data_types]

        try:
            data_types_factory = DataTypesFactory(
                path=path_data_types, log_level=self.log_level
            )
            Model.CACHE_DATA_TYPES[path_data_types] = data_types_factory
            self.logger.info(
                "Successfully init Data Types Factory from %s" % path_data_types
            )

            return data_types_factory
        except Exception as e:
            self.__error_handler(e)

    @property
    def data_source_types(self) -> DataSourceTypesFactory:
        path_data_source_types: str = os.path.join(
            self.__get_dict_path(self.path_base), "DataSourceTypes.json"
        )
        if path_data_source_types in Model.CACHE_DATA_SOURCE_TYPES:
            self.logger.debug(
                "Cached DataSourceTypesFactory for %s" % path_data_source_types
            )
            return Model.CACHE_DATA_SOURCE_TYPES[path_data_source_types]

        try:
            data_source_types_factory = DataSourceTypesFactory(
                path=path_data_source_types, log_level=self.log_level
            )
            Model.CACHE_DATA_SOURCE_TYPES[path_data_source_types] = data_source_types_factory
            self.logger.info(
                "Successfully init Data Source Types Factory from %s" % path_data_source_types
            )

            return data_source_types_factory
        except Exception as e:
            self.__error_handler(e)

    @property
    def zones(self) -> ZonesFactory:
        path_zones: str = os.path.join(
            self.__get_dict_path(self.path_base), "Zones.json"
        )
        if path_zones in Model.CACHE_ZONES:
            self.logger.debug(
                "Cached ZonesFactory for %s" % path_zones
            )
            return Model.CACHE_ZONES[path_zones]

        try:
            zones_factory = ZonesFactory(
                path=path_zones, log_level=self.log_level
            )
            Model.CACHE_ZONES[path_zones] = zones_factory
            self.logger.info(
                "Successfully init Zones Factory from %s" % path_zones
            )

            return zones_factory
        except Exception as e:
            self.__error_handler(e)

    def __error_handler(self, e: Exception):
        self.errors.append(e)
        self.logger.error(str(e))

    def __get_dict_path(self, dict_item) -> str:
        # ToDo: Implement relative path (e.g. ./base)
        return str(os.path.join(self.dict_solution, dict_item))

    def get_index(self) -> Index:
        idx_json: json = Helper.read_json(self.path_index)
        _idx = Index.model_validate_json(json.dumps(idx_json))
        return _idx






    def get_unified_entity(self, path: str) -> UnifiedEntityFactory:
        """Get a unified entity factory for v2 schema entities.
        
        Args:
            path (str): The path to the entity file.
            
        Returns:
            UnifiedEntityFactory: The unified entity factory instance.
        """
        try:
            return UnifiedEntityFactory(path=path, log_level=self.log_level)
        except Exception as e:
            self.__error_handler(e)

    def detect_v1_schema(self, entity_json: dict) -> bool:
        """Detect if an entity uses deprecated v1 schema format.
        
        Args:
            entity_json (dict): The entity JSON data.
            
        Returns:
            bool: True if entity uses v1 schema (now unsupported), False otherwise.
        """
        # Check for v1 schema indicators
        entity_type = entity_json.get("type", "")
        if entity_type in ["raw", "stage", "core", "curated"]:
            return True
            
        # Check for v1 structure patterns
        if "function" in entity_json and "entity" in entity_json:
            # This could be v1 if type is not "entity"
            if entity_type != "entity":
                return True
                
        return False

    def get_entity_factory(self, path: str) -> UnifiedEntityFactory:
        """Get the unified entity factory for v2 schema entities.
        
        Args:
            path (str): The path to the entity file.
            
        Returns:
            UnifiedEntityFactory: The unified entity factory.
            
        Raises:
            ValueError: If the entity uses deprecated v1 schema format.
        """
        try:
            entity_json = Helper.read_json(path)
            
            if self.detect_v1_schema(entity_json):
                entity_type = entity_json.get("type", "unknown")
                raise ValueError(
                    f"Entity at {path} uses deprecated v1 schema format (type: {entity_type}). "
                    "Please migrate to v2 schema using ModelDataEntity.json. "
                    "See documentation for migration guide."
                )
            
            return self.get_unified_entity(path)
                    
        except Exception as e:
            self.__error_handler(e)
            raise

    def get_raw_entity_list(self) -> list[UnifiedEntityFactory]:
        """Get raw layer entities (DEPRECATED - use get_entity_list_by_layer('raw') instead)."""
        import warnings
        warnings.warn(
            "get_raw_entity_list() is deprecated. Use get_entity_list_by_layer('raw') instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.get_entity_list_by_layer('raw')

    def get_stage_entity_list(self) -> list[UnifiedEntityFactory]:
        """Get stage layer entities (DEPRECATED - use get_entity_list_by_layer('stage') instead)."""
        import warnings
        warnings.warn(
            "get_stage_entity_list() is deprecated. Use get_entity_list_by_layer('stage') instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.get_entity_list_by_layer('stage')

    def get_core_entity_list(self) -> list[UnifiedEntityFactory]:
        """Get core layer entities (DEPRECATED - use get_entity_list_by_layer('core') instead)."""
        import warnings
        warnings.warn(
            "get_core_entity_list() is deprecated. Use get_entity_list_by_layer('core') instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.get_entity_list_by_layer('core')

    def get_curated_entity_list(self) -> list[UnifiedEntityFactory]:
        """Get curated layer entities (DEPRECATED - use get_entity_list_by_layer('curated') instead)."""
        import warnings
        warnings.warn(
            "get_curated_entity_list() is deprecated. Use get_entity_list_by_layer('curated') instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.get_entity_list_by_layer('curated')

    def get_entity_list_by_layer(self, layer: str) -> list[UnifiedEntityFactory]:
        """Get entities for a specific layer using unified factory.
        
        Args:
            layer (str): Layer name ("raw", "stage", "core", "curated").
            
        Returns:
            list[UnifiedEntityFactory]: List of unified entity factories for the layer.
        """
        ls_entity = []
        index = self.get_index()
        
        # Special handling for raw layer - derive from staging entities
        if layer.lower() == "raw":
            for e in index.stageIndex.entry:
                try:
                    unified_entity = self.get_unified_entity(path=e.absPath)
                    # Only add if the staging entity has system sources (indicating it should have a raw layer)
                    if unified_entity.system_sources:
                        self.logger.debug(
                            f"Added derived raw entity from staging: {e.locator} file: {e.absPath}"
                        )
                        ls_entity.append(unified_entity)
                except Exception as e_inner:
                    self.logger.warning(f"Error processing staging entity for raw derivation: {e_inner}")
        else:
            # Standard handling for other layers
            layer_index_name = f"{layer.lower()}Index"
            if hasattr(index, layer_index_name):
                layer_index = getattr(index, layer_index_name)
                for e in layer_index.entry:
                    self.logger.debug(
                        f"Added to {layer} entity list locator: {e.locator} file: {e.absPath}"
                    )
                    ls_entity.append(self.get_entity_factory(path=e.absPath))
            else:
                raise ValueError(f"Unknown layer: {layer}. Valid layers are: raw, stage, core, curated")

        return ls_entity

    def get_entity_list(
        self,
        regex: str = r"^([A-Za-z]*)\/([A-Za-z]*)\/([A-Za-z]*)\/([A-Za-z]*)",
    ) -> list[UnifiedEntityFactory]:
        ls_entity = []
        for e in self.get_locator(regex=regex):
            self.logger.debug(
                f"Added to entity list locator: {e.locator} file: {e.absPath}"
            )
            ls_entity.append(self.get_entity_factory(path=e.absPath))

        return ls_entity

    def get_unified_entity_list(self) -> list[UnifiedEntityFactory]:
        """Get all unified v2 entities across all layers.
        
        Returns:
            list[UnifiedEntityFactory]: List of unified entity factories.
        """
        ls_unified_entity = []
        index = self.get_index()
        
        # Check all layers for v2 entities
        for layer_name in ["rawIndex", "stageIndex", "coreIndex", "curatedIndex"]:
            layer_index = getattr(index, layer_name)
            for entry in layer_index.entry:
                try:
                    entity_json = Helper.read_json(entry.absPath)
                    if not self.detect_v1_schema(entity_json):
                        self.logger.debug(
                            f"Added unified entity: {entry.locator} file: {entry.absPath}"
                        )
                        ls_unified_entity.append(self.get_unified_entity(path=entry.absPath))
                except Exception as e:
                    self.logger.warning(f"Error processing entity {entry.absPath}: {e}")
                    
        return ls_unified_entity

    def get_unified_entities_by_layer(self, layer: str) -> list[UnifiedEntityFactory]:
        """Get unified v2 entities for a specific layer.
        
        Args:
            layer (str): Layer name (raw, stage, core, curated).
            
        Returns:
            list[UnifiedEntityFactory]: List of unified entity factories for the layer.
        """
        ls_unified_entity = []
        index = self.get_index()
        
        layer_index_name = f"{layer}Index"
        if hasattr(index, layer_index_name):
            layer_index = getattr(index, layer_index_name)
            for entry in layer_index.entry:
                try:
                    entity_json = Helper.read_json(entry.absPath)
                    if not self.detect_v1_schema(entity_json):
                        self.logger.debug(
                            f"Added unified {layer} entity: {entry.locator} file: {entry.absPath}"
                        )
                        ls_unified_entity.append(self.get_unified_entity(path=entry.absPath))
                except Exception as e:
                    self.logger.warning(f"Error processing {layer} entity {entry.absPath}: {e}")
                    
        return ls_unified_entity

    def __get_index_items(self) -> list[tuple[str, str]]:
        ls_index_items: list[tuple[str, str]] = [
            ("rawIndex", self.path_raw),
            ("stageIndex", self.path_stage),
            ("coreIndex", self.path_core),
            ("curatedIndex", self.path_curated),
        ]
        return ls_index_items

    def __get_index_entry(self, path: str) -> dict:
        ls_idx_entry = []
        for subdir, dirs, files in os.walk(path):
            json_files = [f for f in files if f.endswith(".json")]

            for file in json_files:
                abspath = os.path.join(subdir, file)

                try:
                    _js = Helper.read_json(abspath)
                except JsonFileParseException as e:
                    self.__error_handler(e)
                    continue

                # Check for deprecated v1 schema and provide helpful error
                if self.detect_v1_schema(_js):
                    self.logger.error(f"Found deprecated v1 schema in {abspath}. Please migrate to v2 schema format.")
                    continue
                
                # V2 schema only: extract layer from path and entity info from entity object
                unified_factory = UnifiedEntityFactory(abspath, log_level=self.log_level)
                entity_type = unified_factory.entity_layer.lower()
                data_module = unified_factory.data_module
                data_product = unified_factory.data_product
                entity_name = unified_factory.entity_name

                locator = Helper.get_locator(
                    entity_type=entity_type,
                    data_module=data_module,
                    data_product=data_product,
                    entity_name=entity_name,
                )
                entry: dict = {
                    "absPath": abspath,
                    "name": entity_name,
                    "locator": locator,
                }

                # Add references field to core and curated objects
                if entity_type in ["core", "curated"]:
                    entry["references"] = []

                ls_idx_entry.append(entry)

        __dict: dict = {"entry": ls_idx_entry}

        return __dict

    @dataclass
    class IndexTuple:
        index: Index
        locators: list[str]

    def __get_clean_index_tuple(self) -> IndexTuple:
        try:
            ls_locators = []

            # Get current Index
            __idx = self.get_index()

            # Remove invalid index items and add valid to locators list
            for item in self.__get_index_items():
                for i in getattr(__idx, f"{item[0]}").entry:
                    if not os.path.exists(i.absPath):
                        self.logger.info(
                            f"Removing deleted file from index: {os.path.basename(i.absPath)}"
                        )
                        getattr(__idx, f"{item[0]}").entry.remove(i)
                    else:
                        ls_locators.append(i.locator)

            tpl = self.IndexTuple(index=__idx, locators=ls_locators)

            return tpl

        except Exception as e:
            self.__error_handler(e)

    def __get_refresh_index(self) -> Index:
        self.logger.info("Start index refresh")

        __idx_tuple = self.__get_clean_index_tuple()
        __idx: Index = __idx_tuple.index
        __locators: list = __idx_tuple.locators

        idx_change_time = os.path.getmtime(self.path_index)
        # idx_created_time = os.path.getctime(self.path_index)  # never used

        for item in self.__get_index_items():
            self.logger.info(f"Start refreshing index for: {item[0]}")

            for subdir, dirs, files in os.walk(item[1]):
                for file in files:
                    abspath = os.path.join(subdir, file)
                    file_name = os.path.basename(abspath)
                    file_change_time = os.path.getmtime(abspath)

                    if file_change_time > idx_change_time:
                        _js = Helper.read_json(abspath)
                        
                        # Check for deprecated v1 schema and skip
                        if self.detect_v1_schema(_js):
                            self.logger.warning(f"Skipping deprecated v1 schema file: {file_name}")
                            continue
                        
                        # V2 schema only: extract layer from path and entity info from entity object
                        unified_factory = UnifiedEntityFactory(abspath, log_level=self.log_level)
                        entity_type = unified_factory.entity_layer.lower()
                        data_module = unified_factory.data_module
                        data_product = unified_factory.data_product
                        entity_name = unified_factory.entity_name
                        
                        locator = Helper.get_locator(
                            entity_type=entity_type,
                            data_module=data_module,
                            data_product=data_product,
                            entity_name=entity_name,
                        )

                        # Only add if locator not already in the list
                        if locator not in __locators:
                            entry: dict = {
                                "absPath": abspath,
                                "name": entity_name,
                                "locator": locator,
                            }
                            e = Index.model_validate_json(json.dumps(entry))
                            getattr(__idx, f"{item[0]}").entry.append(e)
                            self.logger.info(
                                f"Adding file to index: {file_name}"
                            )
                        else:
                            self.logger.info(
                                f"Changed File locator already in index: {file_name}"
                            )

        return __idx

    def __check_index_duplicates(self, idx: Index):
        ls_locators: list[str] = []
        for item in self.__get_index_items():
            for i in getattr(idx, f"{item[0]}").entry:
                if i.locator in ls_locators:
                    raise ValueError(
                        f"Error generating index due to duplicate locator: {i.locator} in file: {i.absPath}"
                    )
                else:
                    ls_locators.append(i.locator)

    def check_zone_for_entities(self, zone: str) -> bool:
        if zone == "raw":
            path_to_check = self.path_raw
        elif zone == "stage":
            path_to_check = self.path_stage
        elif zone == "core":
            path_to_check = self.path_core
        elif zone == "curated":
            path_to_check = self.path_curated
        else:
            raise ValueError("Unknown zone name: %s" % zone)

        return len(self.__get_index_entry(path_to_check)["entry"]) > 0

    def validate_index(self, full_index_scan=True):
        try:
            if full_index_scan or not os.path.exists(self.path_index):
                self.logger.info("Start full index generating")

                raw: dict = self.__get_index_entry(self.path_raw)
                stage: dict = self.__get_index_entry(self.path_stage)
                core: dict = self.__get_index_entry(self.path_core)
                curated: dict = self.__get_index_entry(self.path_curated)

                if self.errors:
                    raise Model.ModelParseException(
                        inner_exceptions=self.errors
                    )

                # Create Index
                idx_dict: dict = {
                    "type": "Index",
                    "rawIndex": raw,
                    "stageIndex": stage,
                    "coreIndex": core,
                    "curatedIndex": curated,
                }

                # Validate duplicate locators
                __idx = Index.model_validate_json(json.dumps(idx_dict))
                self.__check_index_duplicates(idx=__idx)

                # Write Index
                with open(self.path_index, "w", encoding="utf-8") as f:
                    json.dump(idx_dict, f, ensure_ascii=False, indent=4)

                self.logger.info("Index has been generated")

            else:
                idx_refreshed = self.__get_refresh_index()

                # Validate duplicate locators
                self.__check_index_duplicates(idx=idx_refreshed)

                with open(self.path_index, "w", encoding="utf-8") as f:
                    json.dump(
                        idx_refreshed.to_dict(), f, ensure_ascii=False, indent=4
                    )

                self.logger.info("Index has been refreshed")

        except Model.ModelParseException as e:
            self.logger.error(str(e))
            sys.exit(-1)

        except Exception as e:
            self.__error_handler(e)

    def get_locator(
        self,
        regex: str = r"^([A-Za-z]*)\/([A-Za-z]*)\/([A-Za-z]*)\/([A-Za-z]*)",
    ) -> list[Index]:
        if not re.search(r"^\/+.+\/.+\/.+\/.+$", re.escape(regex)):
            raise InvalidLocatorException(regex)

        ls_locators: list = []
        __idx = self.get_index()

        for item in self.__get_index_items():
            for entry in getattr(__idx, item[0]).entry:
                locator = entry.locator
                # if re.match(re.escape(regex.lower()), str(locator).lower()):
                if regex.lower() == str(locator).lower():
                    self.logger.debug(
                        f"Matching regex locator added: {locator}"
                    )
                    ls_locators.append(entry)

        if ls_locators is None or len(ls_locators) == 0:
            raise LocatorNotFoundException(regex)

        if len(ls_locators) != 1:
            raise MultipleLocatorsFoundException(
                "%s - %s" % (regex, str(ls_locators))
            )

        return ls_locators

    def lookup_entity(self, locator: str) -> UnifiedEntityFactory:
        """
        Lookup an entity object by locator

        Arguments:
            locator(str): Locator to lookup in the index, e.g. "/Raw/Sales/Customer/Customer_DE"
        """
        self.logger.debug("Start looking for locator: %s" % locator)

        if not locator.startswith("/"):
            locator = "/" + locator

        layer = locator.lower().split("/")[1]

        locator_index = self.get_locator(regex=locator)
        self.logger.debug("Locator Index: %s" % str(locator_index))

        for locator_index in self.get_locator(regex=locator):
            # Use the schema-aware factory method to get the appropriate factory
            return self.get_entity_factory(path=locator_index.absPath)

    def lookup_stage_entity(self, locator: str) -> UnifiedEntityFactory:
        """
        Lookup a Stage entity object by locator

        Parameters:
            locator: str = Stage locator to lookup in index (e.g "Stage/Sales/Customer/Customer_DE")
        """
        self.logger.debug("Start looking for locator: %s" % locator)

        if locator.lower().startswith("/stage") or locator.lower().startswith("/staging"):
            locator_index = self.get_locator(regex=locator)
            self.logger.debug("Locator Index: %s" % str(locator_index))

            for locator_index in self.get_locator(regex=locator):
                return self.get_entity_factory(path=locator_index.absPath)
        else:
            self.logger.warning(
                f"Can not return stage object as the locatore {locator} is not a stage location"
            )

    def perform_initial_checks(self, *layers) -> int:
        """Performs some simple checks to validate the model before actually
        processing templates.

        The reason to do this is that some error are hard to identify during
        template rendering, e.g. a source locator of a core entity does not
        work.

        Arguments:
            *layers: The names of layers to perform checks on, e.g. `raw`.
        """
        self.logger.debug("Start performing initial model checks")

        if "raw" in layers:
            self.__perform_raw_checks()

        if "stage" in layers:
            self.__perform_stage_checks()

        if "core" in layers:
            self.__perform_core_checks()

        if "curated" in layers:
            self.__perform_curated_checks()

        self.logger.info("Finished initial model checks")

        return 0

    def __perform_raw_checks(self) -> None:
        raw_entities: list = self.get_raw_entity_list()

        self.logger.info("Raw Entities to process: %s" % str(len(raw_entities)))

    def __perform_stage_checks(self) -> None:
        stage_entities: list = self.get_stage_entity_list()
        self.logger.info(
            "Stage Entities to process: %s" % str(len(stage_entities))
        )

    def __perform_core_checks(self) -> None:
        core_entities: list = self.get_core_entity_list()
        self.logger.info(
            "Core Entities to process: %s" % str(len(core_entities))
        )

        for entity in core_entities:
            # V2 unified entity structure only
            table = entity.entity
            sources = entity.model_sources if hasattr(entity, 'model_sources') else []
            table_name = table.name

            self.logger.debug("Core Table: %s" % table_name)

            # validate source locators
            for source in sources:
                if hasattr(source, 'dm8l'):
                    source_locator = source.dm8l
                elif hasattr(source, 'model') and hasattr(source.model, 'dm8l'):
                    source_locator = source.model.dm8l
                else:
                    continue
                    
                self.logger.debug("Source Entity Locator: %s" % source_locator)
                try:
                    stage_entity = self.lookup_entity(source_locator)
                    entity_name = stage_entity.entity_name
                    self.logger.debug("Source Entity: %s" % entity_name)
                except Exception as e:
                    self.logger.warning(f"Could not lookup source entity {source_locator}: {e}")

    def __perform_curated_checks(self) -> None:
        curated_entities: list = self.get_curated_entity_list()
        self.logger.info(
            "Curated Entities to process: %s" % str(len(curated_entities))
        )

        for entity in curated_entities:
            # V2 unified entity structure only
            table = entity.entity
            sources = entity.model_sources if hasattr(entity, 'model_sources') else []
            table_name = table.name

            self.logger.debug("Curated Table: %s" % table_name)

            # V2: iterate through model sources
            for source in sources:
                if hasattr(source, 'model') and hasattr(source.model, 'dm8l'):
                    source_locator = source.model.dm8l
                    self.logger.debug("Source Entity Locator: %s" % source_locator)
                    try:
                        core_entity = self.lookup_entity(source_locator)
                        entity_name = core_entity.entity_name
                        self.logger.debug("Source Entity: %s" % entity_name)
                    except Exception as e:
                        self.logger.warning(f"Could not lookup source entity {source_locator}: {e}")

    class ModelParseException(Exception):
        def __init__(
            self,
            msg="Error(s) occured during model files parsing.",
            inner_exceptions: list[Exception] = [],
        ):
            Exception.__init__(self, msg)

            self.inner_exceptions = inner_exceptions
            self.message = msg

        def get_errors(self):
            errors = [
                textwrap.dedent(
                    """
                    File:       %(file)s
                    --------------------------
                    Error:      %(message)s
                    Error-Type: %(type)s
                    """
                    % {
                        "file": e.file,
                        "type": type(e),
                        "message": str(e),
                    }
                )
                for e in self.inner_exceptions
            ]

            return self.message + "\n" + "\n".join(errors)


class LocatorNotFoundException(Exception):
    def __init__(self, locator):
        super().__init__("Locator was not found: %s" % locator)


class MultipleLocatorsFoundException(Exception):
    def __init__(self, locator):
        super().__init__("Multiple locators found for: %s" % locator)


class InvalidLocatorException(Exception):
    def __init__(self, locator):
        super().__init__("Not a valid locator: %s" % locator)
