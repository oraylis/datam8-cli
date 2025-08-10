from typing import Dict, List, Optional, Any, Tuple
import json
import os
from pathlib import Path
import logging
from datetime import datetime

from .TypeMappingEngine import TypeMappingEngine, AttributeTypeMapping
from .SourceDiscovery import get_connector, ConnectionInfo
from .DataSourceFactory import DataSourceFactory
from ..Helper.Helper import Helper

logger = logging.getLogger(__name__)


class ReverseGenerator:
    """
    Main class for reverse generating DataM8 staging entities from data sources.
    
    This class orchestrates the entire reverse generation process:
    1. Connect to data sources and extract metadata
    2. Map data types using hierarchical resolution
    3. Generate staging entity JSON files
    4. Apply user preferences and interactive prompts
    """

    def __init__(self, solution_path: str, log_level: int = logging.INFO):
        """
        Initialize the reverse generator.
        
        Args:
            solution_path (str): Path to the solution file
            log_level (int): Logging level
        """
        self.solution_path = solution_path
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(log_level)
        
        # Initialize components
        try:
            self.solution_data = Helper.read_json(solution_path)
            self.model_path = self.solution_data.get('modelPath', 'Model')
            self.base_path = self.solution_data.get('basePath', '')
            
            # Initialize type mapping engine
            self.type_mapping_engine = TypeMappingEngine(solution_path, log_level)
            
            # Initialize data source factory
            from pathlib import Path
            solution_dir = Path(solution_path).parent
            data_sources_path = solution_dir / self.base_path / "DataSources.json"
            self.data_source_factory = DataSourceFactory(
                str(data_sources_path), log_level
            )
            
        except Exception as e:
            self.logger.error(f"Failed to initialize ReverseGenerator: {e}")
            raise

    def generate_staging_entities(self, data_source_name: str, data_product: str,
                                 data_module: str, tables: List[str],
                                 entity_names: Optional[List[str]] = None,
                                 interactive: bool = False) -> List[str]:
        """
        Generate staging entities for the specified tables.
        
        Args:
            data_source_name (str): Name of the data source
            data_product (str): Data product for output path
            data_module (str): Data module for output path
            tables (List[str]): List of table names to process
            entity_names (Optional[List[str]]): Corresponding entity names (optional)
            interactive (bool): Enable interactive mode with user prompts
            
        Returns:
            List[str]: List of generated entity file paths
        """
        self.logger.info(f"Starting reverse generation for {len(tables)} tables from '{data_source_name}'")
        
        try:
            # Step 0: Validate connection to data source
            self.logger.info(f"Validating data source connection...")
            is_valid, error_msg = self._validate_data_source_connection(data_source_name)
            if not is_valid:
                raise ValueError(f"Data source validation failed: {error_msg}")
            
            # Validate table existence if not in interactive mode
            if not interactive:
                self.logger.info(f"Validating table existence...")
                tables_valid, table_errors = self._validate_table_existence(data_source_name, tables)
                if not tables_valid:
                    error_messages = [f"{table}: {error}" for table, error in table_errors.items() if error]
                    raise ValueError(f"Table validation failed:\n" + "\n".join(error_messages))
            # Step 1: Get data source information and create connector
            data_source_info = self.type_mapping_engine.get_data_source_info(data_source_name)
            if not data_source_info:
                raise ValueError(f"Data source '{data_source_name}' not found")
            
            connection_info = ConnectionInfo(
                data_source_name=data_source_info['name'],
                data_source_type=data_source_info['type'],
                connection_string=data_source_info['connectionString'],
                extended_properties=data_source_info.get('extendedProperties', {})
            )
            
            connector = get_connector(connection_info, self.logger.level)
            if not connector:
                raise ValueError(f"No connector available for data source type '{data_source_info['type']}'")
            
            # Step 2: Test connection
            if not connector.test_connection():
                raise RuntimeError(f"Failed to connect to data source '{data_source_name}'")
            
            # Step 3: Process each table
            generated_files = []
            
            with connector:
                for i, table_name in enumerate(tables):
                    try:
                        # Determine entity name
                        if entity_names and i < len(entity_names):
                            entity_name = entity_names[i]
                        else:
                            # Auto-generate entity name or prompt user
                            entity_name = self._determine_entity_name(
                                table_name, interactive
                            )
                        
                        # Generate entity
                        file_path = self._generate_single_entity(
                            connector=connector,
                            table_name=table_name,
                            entity_name=entity_name,
                            data_source_name=data_source_name,
                            data_product=data_product,
                            data_module=data_module,
                            interactive=interactive
                        )
                        
                        if file_path:
                            generated_files.append(file_path)
                            self.logger.info(f"Generated entity '{entity_name}' -> {file_path}")
                        
                    except Exception as e:
                        self.logger.error(f"Failed to generate entity for table '{table_name}': {e}")
                        if not interactive:
                            raise  # In non-interactive mode, fail fast
                        else:
                            # In interactive mode, continue with other tables
                            continue
            
            self.logger.info(f"Successfully generated {len(generated_files)} staging entities")
            return generated_files
            
        except Exception as e:
            self.logger.error(f"Reverse generation failed: {e}")
            raise

    def _generate_single_entity(self, connector, table_name: str, entity_name: str,
                               data_source_name: str, data_product: str, data_module: str,
                               interactive: bool = False) -> Optional[str]:
        """
        Generate a single staging entity from table metadata.
        
        Args:
            connector: Source connector instance
            table_name (str): Name of the source table
            entity_name (str): Name for the generated entity
            data_source_name (str): Data source name
            data_product (str): Data product name
            data_module (str): Data module name
            interactive (bool): Enable interactive confirmations
            
        Returns:
            Optional[str]: Path to generated file or None if failed
        """
        try:
            # Step 1: Extract table metadata
            self.logger.info(f"Extracting metadata for table '{table_name}'")
            table_metadata = connector.get_table_metadata(table_name)
            
            if not table_metadata.columns:
                self.logger.warning(f"No columns found for table '{table_name}'")
                return None
            
            # Step 2: Map attributes with type resolution
            attributes = []
            for column in table_metadata.columns:
                try:
                    # Create attribute mapping
                    attr_mapping = self.type_mapping_engine.create_attribute_mapping(
                        column_name=column.name,
                        source_data_source_name=data_source_name,
                        source_type=column.data_type,
                        nullable=column.is_nullable,
                        char_len=column.character_maximum_length,
                        precision=column.numeric_precision,
                        scale=column.numeric_scale,
                        is_primary_key=column.is_primary_key,
                        is_foreign_key=column.is_foreign_key,
                        is_unique=column.is_unique
                    )
                    
                    # Interactive confirmation for attribute type
                    if interactive:
                        confirmed_attr_type = self._confirm_attribute_type(
                            column.name, attr_mapping.attribute_type
                        )
                        attr_mapping.attribute_type = confirmed_attr_type
                    
                    # Build attribute definition
                    attribute = self._build_attribute_definition(
                        column, attr_mapping
                    )
                    
                    attributes.append(attribute)
                    
                except Exception as e:
                    self.logger.error(f"Failed to map attribute '{column.name}': {e}")
                    # Continue with other attributes
                    continue
            
            # Step 3: Build source mapping
            source_mapping = self._build_source_mapping(
                table_metadata, data_source_name
            )
            
            # Step 4: Generate entity JSON
            entity_json = self._build_entity_json(
                entity_name=entity_name,
                table_metadata=table_metadata,
                attributes=attributes,
                source_mapping=source_mapping
            )
            
            # Step 4.5: Validate generated entity JSON
            is_valid, validation_errors = self._validate_generated_entity(entity_json)
            if not is_valid:
                self.logger.warning(f"Generated entity JSON has validation issues: {validation_errors}")
                if not interactive:
                    raise ValueError(f"Entity validation failed: {validation_errors}")
            
            # Step 5: Write to file
            output_path = self._get_output_path(data_product, data_module, entity_name)
            
            # Interactive confirmation for output path
            if interactive:
                confirmed_path = self._confirm_output_path(output_path)
                output_path = confirmed_path
            
            self._write_entity_file(entity_json, output_path)
            
            return output_path
            
        except Exception as e:
            self.logger.error(f"Failed to generate entity '{entity_name}' from table '{table_name}': {e}")
            raise

    def _determine_entity_name(self, table_name: str, interactive: bool = False) -> str:
        """
        Determine the entity name for a table.
        
        Args:
            table_name (str): Source table name
            interactive (bool): Enable user prompts
            
        Returns:
            str: Entity name
        """
        # Extract table name without schema
        _, clean_table_name = table_name.split('.') if '.' in table_name else (None, table_name)
        
        # Default entity name
        default_name = clean_table_name
        
        if interactive:
            try:
                user_input = input(f"Entity name for table '{table_name}' (default: {default_name}): ").strip()
                return user_input if user_input else default_name
            except (EOFError, KeyboardInterrupt):
                return default_name
        
        return default_name

    def _confirm_attribute_type(self, column_name: str, detected_type: str) -> str:
        """
        Confirm attribute type with user in interactive mode.
        
        Args:
            column_name (str): Column name
            detected_type (str): Auto-detected attribute type
            
        Returns:
            str: Confirmed attribute type
        """
        try:
            user_input = input(f"Attribute type for '{column_name}' (detected: {detected_type}): ").strip()
            return user_input if user_input else detected_type
        except (EOFError, KeyboardInterrupt):
            return detected_type

    def _confirm_output_path(self, default_path: str) -> str:
        """
        Confirm output path with user in interactive mode.
        
        Args:
            default_path (str): Default output path
            
        Returns:
            str: Confirmed output path
        """
        try:
            print(f"Output path: {default_path}")
            user_input = input("Press Enter to confirm or provide alternative path: ").strip()
            return user_input if user_input else default_path
        except (EOFError, KeyboardInterrupt):
            return default_path

    def _build_attribute_definition(self, column: Any, attr_mapping: AttributeTypeMapping) -> Dict[str, Any]:
        """
        Build attribute definition JSON structure.
        
        Args:
            column: Column metadata
            attr_mapping (AttributeTypeMapping): Attribute type mapping
            
        Returns:
            Dict[str, Any]: Attribute definition
        """
        attribute = {
            "ordinalNumber": column.ordinal_position,
            "name": column.name,
            "displayName": column.name,
            "description": "",
            "sourceDataType": {
                "type": attr_mapping.source_data_type.source_type,
                "nullable": attr_mapping.source_data_type.nullable
            },
            "targetDataType": {
                "type": attr_mapping.target_data_type.target_type,
                "nullable": attr_mapping.target_data_type.nullable
            },
            "tags": []
        }
        
        # Only add attributeType if it's explicitly set (not None)
        if attr_mapping.attribute_type is not None:
            attribute["attributeType"] = attr_mapping.attribute_type
        
        # Add character length if applicable
        if attr_mapping.source_data_type.char_len is not None:
            attribute["sourceDataType"]["charLen"] = attr_mapping.source_data_type.char_len
        
        # Add precision and scale based on DataTypes.json configuration
        data_type_config = self.type_mapping_engine.data_types_factory.get_data_type(attr_mapping.target_data_type.target_type)
        if data_type_config:
            if getattr(data_type_config, 'hasPrecision', False) and attr_mapping.source_data_type.precision is not None:
                attribute["sourceDataType"]["precision"] = attr_mapping.source_data_type.precision
            if getattr(data_type_config, 'hasScale', False) and attr_mapping.source_data_type.scale is not None:
                attribute["sourceDataType"]["scale"] = attr_mapping.source_data_type.scale
        
        # Add type classification for special columns
        if column.is_primary_key:
            attribute["type"] = "BK"  # Business Key
        elif column.name.lower().endswith('date') or column.name.lower().endswith('datetime'):
            attribute["type"] = "SCD1"
        
        # Add modification date
        attribute["dateModified"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        return attribute

    def _build_source_mapping(self, table_metadata: Any, data_source_name: str) -> List[Dict[str, Any]]:
        """
        Build source mapping configuration.
        
        Args:
            table_metadata: Table metadata
            data_source_name (str): Data source name
            
        Returns:
            List[Dict[str, Any]]: Source mapping configuration
        """
        # Build column mappings
        mappings = []
        for column in table_metadata.columns:
            mappings.append({
                "targetName": column.name,
                "sourceName": f"[{column.name}]"
            })
        
        # Determine source location
        source_location = f"[{table_metadata.schema_name}].[{table_metadata.table_name}]"
        
        # Build source configuration
        sources = [{
            "type": "source",
            "source": {
                "dataSource": data_source_name,
                "sourceLocation": source_location,
                "extract": {
                    "type": "full",
                    "full": {}
                },
                "mapping": mappings
            }
        }]
        
        return sources

    def _build_entity_json(self, entity_name: str, table_metadata: Any,
                          attributes: List[Dict[str, Any]], 
                          source_mapping: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Build complete entity JSON structure.
        
        Args:
            entity_name (str): Entity name
            table_metadata: Table metadata
            attributes (List[Dict[str, Any]]): Attribute definitions
            source_mapping (List[Dict[str, Any]]): Source mapping configuration
            
        Returns:
            Dict[str, Any]: Complete entity JSON
        """
        entity_json = {
            "$schema": "https://raw.githubusercontent.com/oraylis/datam8-model/refs/heads/feature/v2/schema/ModelDataEntity.json",
            "type": "entity",
            "entity": {
                "name": entity_name,
                "displayName": entity_name,
                "description": f"Staging entity generated from table {table_metadata.schema_name}.{table_metadata.table_name}",
                "tags": [],
                "parameters": [],
                "attribute": attributes
            },
            "functions": {
                "trigger": {
                    "mode": "schedule",
                    "schedule": {
                        "cronExpression": "0 1 * * *",
                        "timezone": "UTC",
                        "maxRetries": 3
                    }
                },
                "store": {
                    "write_mode": "merge",
                    "merge": {
                        "business_key": table_metadata.primary_keys if table_metadata.primary_keys else [attributes[0]["name"]],
                        "sequential": True
                    },
                    "layout": {
                        "type": "liquid_clustering",
                        "keys": table_metadata.primary_keys if table_metadata.primary_keys else [attributes[0]["name"]]
                    },
                    "maintenance": {
                        "retention": "7 days"
                    }
                },
                "sources": source_mapping
            }
        }
        
        return entity_json

    def _get_output_path(self, data_product: str, data_module: str, entity_name: str) -> str:
        """
        Get the output file path for the entity.
        
        Args:
            data_product (str): Data product name
            data_module (str): Data module name
            entity_name (str): Entity name
            
        Returns:
            str: Full output file path
        """
        # Get solution directory
        solution_dir = Path(self.solution_path).parent
        
        # Build path: Model/010-Staging/{data_product}/{data_module}/{entity_name}.json
        output_path = solution_dir / self.model_path / "010-Staging" / data_product / data_module / f"{entity_name}.json"
        
        return str(output_path)

    def _write_entity_file(self, entity_json: Dict[str, Any], output_path: str) -> None:
        """
        Write entity JSON to file.
        
        Args:
            entity_json (Dict[str, Any]): Entity JSON data
            output_path (str): Output file path
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Write JSON file with proper formatting
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(entity_json, f, indent=4, ensure_ascii=False)
            
            self.logger.info(f"Entity file written to: {output_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to write entity file to '{output_path}': {e}")
            raise

    def _validate_data_source_connection(self, data_source_name: str) -> Tuple[bool, Optional[str]]:
        """
        Validate that a data source connection can be established.
        
        Args:
            data_source_name (str): Name of the data source
            
        Returns:
            Tuple[bool, Optional[str]]: (is_valid, error_message)
        """
        try:
            from .SourceDiscovery import get_connector, ConnectionInfo
            from .DataSourceFactory import DataSourceFactory
            
            # Get data source information
            solution_dir = Path(self.solution_path).parent
            data_sources_path = solution_dir / self.base_path / "DataSources.json"
            data_source_factory = DataSourceFactory(
                str(data_sources_path), self.logger.level
            )
            
            data_source = data_source_factory.get_datasource(data_source_name)
            if not data_source:
                return False, f"Data source '{data_source_name}' not found"
            
            # Create connection info
            connection_info = ConnectionInfo(
                data_source_name=data_source.name,
                data_source_type=data_source.type,
                connection_string=data_source.connectionString,
                extended_properties=data_source.ExtendedProperties
            )
            
            # Get connector
            connector = get_connector(connection_info, self.logger.level)
            if not connector:
                return False, f"No connector available for data source type '{data_source.type}'"
            
            # Test connection
            if not connector.test_connection():
                return False, f"Failed to connect to data source '{data_source_name}'"
            
            return True, None
            
        except Exception as e:
            return False, f"Error testing data source connection: {str(e)}"

    def _validate_table_existence(self, data_source_name: str, tables: List[str]) -> Tuple[bool, Dict[str, str]]:
        """
        Validate that specified tables exist in the data source.
        
        Args:
            data_source_name (str): Name of the data source
            tables (List[str]): List of table names to validate
            
        Returns:
            Tuple[bool, Dict[str, str]]: (all_valid, dict of table->error_message)
        """
        try:
            from .SourceDiscovery import get_connector, ConnectionInfo
            from .DataSourceFactory import DataSourceFactory
            
            # Get data source and connector
            solution_dir = Path(self.solution_path).parent
            data_sources_path = solution_dir / self.base_path / "DataSources.json"
            data_source_factory = DataSourceFactory(
                str(data_sources_path), self.logger.level
            )
            
            data_source = data_source_factory.get_datasource(data_source_name)
            connection_info = ConnectionInfo(
                data_source_name=data_source.name,
                data_source_type=data_source.type,
                connection_string=data_source.connectionString,
                extended_properties=data_source.ExtendedProperties
            )
            
            connector = get_connector(connection_info, self.logger.level)
            if not connector:
                error_msg = f"No connector available for data source type '{data_source.type}'"
                return False, {table: error_msg for table in tables}
            
            # Discover available tables
            with connector:
                available_tables = connector.discover_tables()
            
            # Validate each table
            table_errors = {}
            all_valid = True
            
            for table in tables:
                # Normalize table name for comparison
                normalized_table = table.lower()
                normalized_available = [t.lower() for t in available_tables]
                
                if normalized_table not in normalized_available:
                    table_errors[table] = f"Table '{table}' not found in data source"
                    all_valid = False
                else:
                    table_errors[table] = None  # Valid
            
            return all_valid, table_errors
            
        except Exception as e:
            error_msg = f"Error validating table existence: {str(e)}"
            return False, {table: error_msg for table in tables}

    def _validate_generated_entity(self, entity_json: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate generated entity JSON against the schema.
        
        Args:
            entity_json (Dict[str, Any]): Generated entity JSON
            
        Returns:
            Tuple[bool, List[str]]: (is_valid, list_of_errors)
        """
        errors = []
        
        try:
            # Basic structure validation
            if not isinstance(entity_json, dict):
                errors.append("Entity JSON must be a dictionary")
                return False, errors
            
            # Check required top-level fields
            required_fields = ['$schema', 'type', 'entity']
            for field in required_fields:
                if field not in entity_json:
                    errors.append(f"Missing required field: {field}")
            
            # Validate entity structure
            if 'entity' in entity_json:
                entity = entity_json['entity']
                required_entity_fields = ['name', 'displayName']
                for field in required_entity_fields:
                    if field not in entity:
                        errors.append(f"Missing required entity field: {field}")
                
                # Validate attributes
                if 'attribute' in entity and isinstance(entity['attribute'], list):
                    for i, attr in enumerate(entity['attribute']):
                        attr_errors = self._validate_attribute(attr, i)
                        errors.extend(attr_errors)
            
            # Validate functions structure
            if 'functions' in entity_json:
                functions = entity_json['functions']
                if 'sources' in functions and isinstance(functions['sources'], list):
                    for i, source in enumerate(functions['sources']):
                        source_errors = self._validate_source_function(source, i)
                        errors.extend(source_errors)
            
            return len(errors) == 0, errors
            
        except Exception as e:
            errors.append(f"Error validating entity JSON: {str(e)}")
            return False, errors

    def _validate_attribute(self, attribute: Dict[str, Any], index: int) -> List[str]:
        """Validate an attribute definition."""
        errors = []
        
        required_fields = ['name', 'targetDataType']
        for field in required_fields:
            if field not in attribute:
                errors.append(f"Attribute {index}: Missing required field '{field}'")
        
        # Validate data types
        for data_type_field in ['sourceDataType', 'targetDataType']:
            if data_type_field in attribute:
                data_type = attribute[data_type_field]
                if not isinstance(data_type, dict):
                    errors.append(f"Attribute {index}: {data_type_field} must be an object")
                else:
                    required_dt_fields = ['type', 'nullable']
                    for field in required_dt_fields:
                        if field not in data_type:
                            errors.append(f"Attribute {index}: {data_type_field} missing required field '{field}'")
        
        return errors

    def _validate_source_function(self, source: Dict[str, Any], index: int) -> List[str]:
        """Validate a source function definition."""
        errors = []
        
        if not isinstance(source, dict):
            errors.append(f"Source {index}: Must be an object")
            return errors
        
        # Check type field
        if 'type' not in source:
            errors.append(f"Source {index}: Missing required field 'type'")
        
        # Validate based on type
        if source.get('type') == 'source':
            if 'source' not in source:
                errors.append(f"Source {index}: Missing 'source' configuration")
            else:
                source_config = source['source']
                required_fields = ['dataSource', 'sourceLocation']
                for field in required_fields:
                    if field not in source_config:
                        errors.append(f"Source {index}: Missing required source field '{field}'")
        
        return errors