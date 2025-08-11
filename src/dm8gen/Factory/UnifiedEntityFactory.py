import json
from ..Generated.ModelDataEntity import Model as UnifiedEntity
from ..Helper.Helper import Helper
import logging

logger = logging.getLogger(__name__)


class UnifiedEntityFactory:
    """Factory class for Unified V2 Entities using ModelDataEntity schema."""

    file_path: str = None
    model_json: json = None
    model_object: UnifiedEntity = None
    model_type: str = None
    entity_layer: str = None
    data_product: str = None
    data_module: str = None
    errors: list = []
    log_level: logging.log = None

    def __init__(self, path: str, log_level: logging.log = logging.INFO) -> None:
        """Initialize the UnifiedEntityFactory.

        Args:
            path (str): The path to the entity file.
            log_level (logging.log, optional): The logging level. Defaults to logging.INFO.
        """
        try:
            self.logger: logging.Logger = Helper.start_logger(
                self.__class__.__name__, log_level=log_level
            )
            self.file_path = path
            self.model_json = Helper.read_json(self.file_path)
            self.model_object = UnifiedEntity.model_validate_json(json.dumps(self.model_json))
            self.model_type = self.model_object.type.value
            
            # Extract layer, data product, and data module from file path
            self._extract_path_metadata()
            
            self.logger.debug(f"Initialized UnifiedEntityFactory for {self.entity_name} at {self.file_path}")
            
        except Exception as e:
            self.__error_handler(str(e))

    def _extract_path_metadata(self):
        """Extract layer, data product, and data module from the file path."""
        try:
            # Normalize path separators
            normalized_path = self.file_path.replace('\\', '/')
            
            # Extract components from path like: .../Model/{Layer}/{DataProduct}/{DataModule}/{Entity}.json
            path_parts = normalized_path.split('/')
            
            # Find the Model directory index
            model_index = -1
            for i, part in enumerate(path_parts):
                if part == 'Model':
                    model_index = i
                    break
            
            if model_index >= 0 and len(path_parts) > model_index + 3:
                self.entity_layer = path_parts[model_index + 1]  # e.g., Core, Staging, Curated
                self.data_product = path_parts[model_index + 2]   # e.g., Sales
                self.data_module = path_parts[model_index + 3]    # e.g., Customer
            else:
                self.logger.warning(f"Could not extract path metadata from {self.file_path}")
                self.entity_layer = "Unknown"
                self.data_product = "Unknown"
                self.data_module = "Unknown"
                
        except Exception as e:
            self.logger.error(f"Error extracting path metadata: {e}")
            self.entity_layer = "Unknown"
            self.data_product = "Unknown"  
            self.data_module = "Unknown"

    @property
    def entity_name(self) -> str:
        """Get the entity name.

        Returns:
            str: The entity name.
        """
        return self.model_object.entity.name

    @property
    def locator(self) -> str:
        """Get the locator.

        Returns:
            str: The locator in format /{Layer}/{DataProduct}/{DataModule}/{EntityName}.
        """
        locator = Helper.get_locator(
            entity_type=self.entity_layer.lower(),
            data_product=self.data_product,
            data_module=self.data_module,
            entity_name=self.entity_name,
        )
        return locator

    @property
    def entity(self):
        """Get the entity definition.

        Returns:
            DataEntity: The entity definition.
        """
        return self.model_object.entity

    @property
    def functions(self):
        """Get the entity functions configuration.

        Returns:
            EntityFunctions: The entity functions configuration.
        """
        return self.model_object.functions

    @property
    def attributes(self):
        """Get the entity attributes.

        Returns:
            List[Attribute]: The entity attributes sorted by ordinal number.
        """
        if self.entity.attribute:
            # Sort by ordinalNumber if available, otherwise maintain original order
            return sorted(self.entity.attribute, 
                         key=lambda x: x.ordinalNumber if x.ordinalNumber is not None else 999999)
        return []

    @property
    def business_key_attributes(self):
        """Get attributes that are business keys.

        Returns:
            List[Attribute]: Attributes with type 'BK'.
        """
        return [attr for attr in self.attributes if attr.type and attr.type.value == 'BK']

    @property
    def surrogate_key_attributes(self):
        """Get attributes that are surrogate keys.

        Returns:
            List[Attribute]: Attributes with type 'SK'.
        """
        return [attr for attr in self.attributes if attr.type and attr.type.value == 'SK']

    @property
    def scd2_attributes(self):
        """Get attributes that are SCD2 tracked.

        Returns:
            List[Attribute]: Attributes with type 'SCD2'.
        """
        return [attr for attr in self.attributes if attr.type and attr.type.value == 'SCD2']

    @property
    def sources(self):
        """Get the source configurations.

        Returns:
            List[Union[SystemSource, ModelSource]]: The source configurations.
        """
        if self.functions and self.functions.sources:
            return self.functions.sources
        return []

    @property
    def model_sources(self):
        """Get model-type sources.

        Returns:
            List[ModelSource]: Sources of type 'model'.
        """
        return [source for source in self.sources 
                if hasattr(source, 'type') and source.type.value == 'model']

    @property
    def system_sources(self):
        """Get system-type sources.

        Returns:
            List[SystemSource]: Sources of type 'source'.
        """
        return [source for source in self.sources 
                if hasattr(source, 'type') and source.type.value == 'source']

    def as_raw_entity(self):
        """Convert this staging entity to a raw entity representation.
        
        For v2 schemas, raw entities are derived from staging entities' source configurations.
        
        Returns:
            dict: Raw entity representation
        """
        if not self.system_sources:
            return None
            
        # Take the first system source as the primary raw source
        primary_source = self.system_sources[0]
        
        raw_entity = {
            "name": self.entity_name,
            "displayName": self.entity.displayName,
            "description": self.entity.description or "",
            "dataSource": primary_source.source.dataSource,
            "sourceLocation": primary_source.source.sourceLocation,
            "attributes": []
        }
        
        # Convert attributes to raw format
        for attr in self.attributes:
            raw_attr = {
                "name": attr.name,
                "type": attr.targetDataType.type,
                "charLength": attr.targetDataType.charLen,
                "precision": attr.targetDataType.precision,
                "scale": attr.targetDataType.scale,
                "nullable": attr.targetDataType.nullable,
                "tags": attr.tags or []
            }
            raw_entity["attributes"].append(raw_attr)
            
        return raw_entity

    def as_stage_entity(self):
        """Convert this entity to a stage entity representation.
        
        Returns:
            dict: Stage entity representation (this is the primary representation)
        """
        stage_entity = {
            "name": self.entity_name,
            "displayName": self.entity.displayName,
            "description": self.entity.description or "",
            "attributes": [],
            "sources": self.sources,
            "functions": self.functions
        }
        
        # Convert attributes to stage format
        for attr in self.attributes:
            stage_attr = {
                "name": attr.name,
                "displayName": attr.displayName,
                "attributeType": attr.attributeType,
                "targetDataType": attr.targetDataType.to_dict(),
                "ordinalNumber": attr.ordinalNumber,
                "charLength": attr.charLength,
                "precision": attr.precision,
                "scale": attr.scale,
                "nullable": attr.nullable,
                "type": attr.type.value if attr.type else "SCD1",
                "tags": attr.tags or []
            }
            # Add sourceDataType if available
            if attr.sourceDataType:
                stage_attr["sourceDataType"] = attr.sourceDataType.to_dict()
            stage_entity["attributes"].append(stage_attr)
            
        return stage_entity

    @property
    def transformations(self):
        """Get the transformation configurations.

        Returns:
            List[Union[CustomTransformation, BuiltInTransformation, FunctionTransformation]]: 
            The transformation configurations sorted by step number.
        """
        if self.functions and self.functions.transformations:
            return sorted(self.functions.transformations, key=lambda x: x.stepNo)
        return []

    @property
    def trigger_config(self):
        """Get the trigger configuration.

        Returns:
            TriggerFunction: The trigger configuration.
        """
        if self.functions:
            return self.functions.trigger
        return None

    @property
    def store_config(self):
        """Get the store configuration.

        Returns:
            StoreFunction: The store configuration.
        """
        if self.functions:
            return self.functions.store
        return None

    def has_schedule_trigger(self) -> bool:
        """Check if entity has schedule-based trigger.

        Returns:
            bool: True if trigger mode is 'schedule'.
        """
        trigger = self.trigger_config
        return trigger and trigger.mode and trigger.mode.value == 'schedule'

    def has_children_trigger(self) -> bool:
        """Check if entity has children-based trigger.

        Returns:
            bool: True if trigger mode is 'children'.
        """
        trigger = self.trigger_config
        return trigger and trigger.mode and trigger.mode.value == 'children'

    def is_merge_mode(self) -> bool:
        """Check if entity uses merge write mode.

        Returns:
            bool: True if store write_mode is 'merge'.
        """
        store = self.store_config
        return store and store.write_mode == 'merge'

    def is_overwrite_mode(self) -> bool:
        """Check if entity uses overwrite write mode.

        Returns:
            bool: True if store write_mode is 'overwrite'.
        """
        store = self.store_config
        return store and store.write_mode == 'overwrite'

    def get_merge_business_keys(self):
        """Get business keys used for merge operations.

        Returns:
            List[str]: Business key field names.
        """
        store = self.store_config
        if store and store.merge and store.merge.business_key:
            return store.merge.business_key
        return []

    def get_layout_keys(self):
        """Get layout/clustering keys.

        Returns:
            List[str]: Layout key field names.
        """
        store = self.store_config
        if store and store.layout and store.layout.keys:
            return store.layout.keys
        return []

    def get_columns_by_type(self, type_name: str) -> list[str]:
        """Get column names filtered by attribute type.
        
        Args:
            type_name (str): The attribute type to filter by (e.g., 'BK', 'SCD0', 'SCD1', 'SCD2', 'SK').
            
        Returns:
            list[str]: List of column names matching the specified type.
        """
        return [attr.name for attr in self.attributes 
                if attr.type and attr.type.value == type_name]

    def get_columns_by_tag(self, tag_name: str) -> list[str]:
        """Get column names filtered by attribute tag.
        
        Args:
            tag_name (str): The tag to filter by (e.g., 'partitions').
            
        Returns:
            list[str]: List of column names that have the specified tag.
        """
        return [attr.name for attr in self.attributes 
                if attr.tags and tag_name in attr.tags]

    def get_source_extract_config(self, source_index: int = 0):
        """Get extract configuration for a specific source.
        
        Args:
            source_index (int): Index of the source (default: 0 for first source).
            
        Returns:
            ExtractConfig or None: The extract configuration for the source.
        """
        if source_index < len(self.system_sources):
            source = self.system_sources[source_index]
            if hasattr(source, 'source') and hasattr(source.source, 'extract'):
                return source.source.extract
        return None

    def get_source_filter(self, source_index: int = 0) -> str:
        """Get SQL filter expression for a specific source.
        
        Args:
            source_index (int): Index of the source (default: 0 for first source).
            
        Returns:
            str: SQL filter expression or empty string.
        """
        if source_index < len(self.system_sources):
            source = self.system_sources[source_index]
            if hasattr(source, 'source') and hasattr(source.source, 'filter'):
                return source.source.filter or ""
        return ""

    def has_delta_extraction(self) -> bool:
        """Check if any source uses delta extraction mode.
        
        Returns:
            bool: True if any source has delta extraction configured.
        """
        for source in self.system_sources:
            if hasattr(source, 'source') and hasattr(source.source, 'extract'):
                extract_config = source.source.extract
                if extract_config and hasattr(extract_config, 'type') and extract_config.type:
                    if extract_config.type.value == 'delta':
                        return True
        return False

    def get_entity_parameters(self) -> list:
        """Get entity-level parameters.
        
        Returns:
            list: List of entity parameters.
        """
        if self.entity.parameters:
            return self.entity.parameters
        return []

    def get_attribute_parameters(self, attr_name: str) -> list:
        """Get parameters for a specific attribute.
        
        Args:
            attr_name (str): Name of the attribute.
            
        Returns:
            list: List of parameters for the attribute.
        """
        for attr in self.attributes:
            if attr.name == attr_name and attr.parameter:
                return attr.parameter
        return []

    def get_attribute_refactor_names(self, attr_name: str) -> list[str]:
        """Get refactor names for a specific attribute.
        
        Args:
            attr_name (str): Name of the attribute.
            
        Returns:
            list[str]: List of refactor names for the attribute.
        """
        for attr in self.attributes:
            if attr.name == attr_name and attr.refactorNames:
                return attr.refactorNames
        return []

    def get_attribute_unit(self, attr_name: str) -> str:
        """Get unit attribute for a specific attribute.
        
        Args:
            attr_name (str): Name of the attribute.
            
        Returns:
            str: Unit attribute or empty string.
        """
        for attr in self.attributes:
            if attr.name == attr_name and attr.unitAttribute:
                return attr.unitAttribute
        return ""

    def __error_handler(self, msg: str):
        """Handle errors.

        Args:
            msg (str): The error message.
        """
        self.errors.append(f"Error UnifiedEntityFactory with error: {msg}")
        self.logger.error(msg)