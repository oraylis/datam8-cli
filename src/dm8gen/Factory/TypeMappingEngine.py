from typing import Dict, Optional, Any
import logging
from dataclasses import dataclass

from .DataSourceTypesFactory import DataSourceTypesFactory
from .DataSourceFactory import DataSourceFactory
from .DataTypesFactory import DataTypesFactory
from ..Helper.Helper import Helper

logger = logging.getLogger(__name__)


@dataclass
class DataTypeMapping:
    """Represents a complete data type mapping with source and target information."""
    
    source_type: str
    target_type: str
    nullable: bool
    char_len: Optional[int] = None
    precision: Optional[int] = None
    scale: Optional[int] = None


@dataclass
class AttributeTypeMapping:
    """Represents attribute type information for semantic mapping."""
    
    attribute_type: str
    source_data_type: DataTypeMapping
    target_data_type: DataTypeMapping


class TypeMappingEngine:
    """
    Engine for hierarchical type mapping resolution in the DataM8 reverse generator.
    
    This class implements the type mapping priority chain:
    1. DataSourceTypes.json → Base type mappings by source type
    2. DataSources.json → Override mappings for specific data source instances
    3. DataTypes.json → Final canonical type resolution using parquetType field
    """

    def __init__(self, solution_path: str, log_level: int = logging.INFO):
        """
        Initialize the type mapping engine.
        
        Args:
            solution_path (str): Path to the solution file
            log_level (int): Logging level
        """
        self.solution_path = solution_path
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(log_level)
        
        # Initialize factory instances
        try:
            from pathlib import Path
            solution_data = Helper.read_json(solution_path)
            solution_dir = Path(solution_path).parent
            base_path = solution_data.get('basePath', '')
            
            self.data_source_types_factory = DataSourceTypesFactory(
                str(solution_dir / base_path / "DataSourceTypes.json"), log_level
            )
            self.data_sources_factory = DataSourceFactory(
                str(solution_dir / base_path / "DataSources.json"), log_level
            )
            self.data_types_factory = DataTypesFactory(
                str(solution_dir / base_path / "DataTypes.json"), log_level
            )
            
        except Exception as e:
            self.logger.error(f"Failed to initialize TypeMappingEngine: {e}")
            raise
        

    def resolve_type_mapping(self, source_data_source_name: str, source_type: str, 
                           nullable: bool = True, char_len: Optional[int] = None,
                           precision: Optional[int] = None, scale: Optional[int] = None) -> DataTypeMapping:
        """
        Resolve type mapping using the hierarchical chain.
        
        Args:
            source_data_source_name (str): Name of the data source
            source_type (str): Source data type
            nullable (bool): Whether the field is nullable
            char_len (Optional[int]): Character length for string types
            precision (Optional[int]): Numeric precision
            scale (Optional[int]): Numeric scale
            
        Returns:
            DataTypeMapping: Complete type mapping information
            
        Raises:
            ValueError: If type mapping cannot be resolved
        """
        try:
            # Step 1: Get base mapping from DataSourceTypes
            data_source = self.data_sources_factory.get_datasource(source_data_source_name)
            if not data_source:
                raise ValueError(f"Data source '{source_data_source_name}' not found")
            
            # Step 2: Try data source specific mapping first
            target_type = self.data_sources_factory.get_datasource_target_type(
                source_data_source_name, source_type
            )
            
            if not target_type:
                # Step 3: Fall back to data source type mapping
                target_type = self._get_datasource_type_mapping(data_source.type, source_type)
            
            if not target_type:
                raise ValueError(f"No type mapping found for source type '{source_type}' in data source '{source_data_source_name}'")
            
            # Step 4: Resolve canonical type using DataTypes.json
            canonical_type = self._resolve_canonical_type(target_type)
            
            return DataTypeMapping(
                source_type=source_type,
                target_type=canonical_type,
                nullable=nullable,
                char_len=char_len,
                precision=precision,
                scale=scale
            )
            
        except Exception as e:
            self.logger.error(f"Failed to resolve type mapping for '{source_type}': {e}")
            raise
    
    
    def create_attribute_mapping(self, column_name: str, source_data_source_name: str,
                               source_type: str, nullable: bool = True,
                               char_len: Optional[int] = None, precision: Optional[int] = None,
                               scale: Optional[int] = None, is_primary_key: bool = False,
                               is_foreign_key: bool = False, is_unique: bool = False) -> AttributeTypeMapping:
        """
        Create complete attribute mapping with type resolution.
        
        Args:
            column_name (str): Name of the column
            source_data_source_name (str): Name of the data source
            source_type (str): Source data type
            nullable (bool): Whether the field is nullable
            char_len (Optional[int]): Character length for string types
            precision (Optional[int]): Numeric precision
            scale (Optional[int]): Numeric scale
            is_primary_key (bool): Whether column is a primary key
            is_foreign_key (bool): Whether column is a foreign key
            is_unique (bool): Whether column has unique constraint
            
        Returns:
            AttributeTypeMapping: Complete attribute mapping
        """
        # Resolve data type mapping
        data_type_mapping = self.resolve_type_mapping(
            source_data_source_name, source_type, nullable, char_len, precision, scale
        )
        
        # Create target type mapping (usually same as source for staging, but can be different)
        target_type_mapping = DataTypeMapping(
            source_type=data_type_mapping.target_type,
            target_type=data_type_mapping.target_type,
            nullable=nullable,
            char_len=char_len,
            precision=precision,
            scale=scale
        )
        
        # No automatic attribute type detection - keep it optional
        attribute_type = None  # User can manually set attributeType if needed
        
        return AttributeTypeMapping(
            attribute_type=attribute_type,
            source_data_type=data_type_mapping,
            target_data_type=target_type_mapping
        )
    
    def _get_datasource_type_mapping(self, source_type_name: str, source_data_type: str) -> Optional[str]:
        """
        Get type mapping from DataSourceTypes.json.
        
        Args:
            source_type_name (str): Name of the data source type (e.g., 'SqlDataSource')
            source_data_type (str): Source data type to map
            
        Returns:
            Optional[str]: Target type or None if not found
        """
        try:
            data_source_type = self.data_source_types_factory.get_datasourcetype(source_type_name)
            if not data_source_type or not data_source_type.dataTypeMapping:
                return None
            
            for mapping in data_source_type.dataTypeMapping:
                if mapping.sourceType == source_data_type:
                    return mapping.targetType
            
            return None
        except Exception as e:
            self.logger.debug(f"Error getting data source type mapping: {e}")
            return None
    
    def _resolve_canonical_type(self, target_type: str) -> str:
        """
        Resolve canonical type using DataTypes.json parquetType field.
        
        Args:
            target_type (str): Target type from previous mapping steps
            
        Returns:
            str: Canonical type name
        """
        try:
            data_type = self.data_types_factory.get_datatype(target_type)
            if data_type and data_type.parquetType:
                return data_type.name  # Return the canonical name, not parquetType
            
            # If not found, return the input type as fallback
            return target_type
        except Exception as e:
            self.logger.debug(f"Error resolving canonical type for '{target_type}': {e}")
            return target_type
    
    
    
    
    def get_data_source_info(self, data_source_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific data source.
        
        Args:
            data_source_name (str): Name of the data source
            
        Returns:
            Optional[Dict[str, Any]]: Data source information or None if not found
        """
        try:
            data_source = self.data_sources_factory.get_datasource(data_source_name)
            if not data_source:
                return None
            
            return {
                'name': data_source.name,
                'displayName': data_source.displayName,
                'type': data_source.type,
                'connectionString': data_source.connectionString,
                'extendedProperties': data_source.ExtendedProperties
            }
        except Exception as e:
            self.logger.error(f"Error getting data source info for '{data_source_name}': {e}")
            return None