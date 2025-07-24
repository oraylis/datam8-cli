import pytest
import json
import tempfile
import os
from dm8gen.Factory.DataSourceTypesFactory import DataSourceTypesFactory


@pytest.fixture
def sample_data_source_types():
    """Sample data source types data for testing."""
    return {
        "$schema": "../datam8-model/schema/DataSourceTypes.json",
        "type": "dataSourceType",
        "dataSourceTypes": [
            {
                "name": "SqlDataSource",
                "displayName": "SQL Database",
                "description": "Traditional SQL database connection",
                "dataTypeMapping": [
                    {
                        "sourceType": "varchar",
                        "targetType": "string"
                    },
                    {
                        "sourceType": "int",
                        "targetType": "integer"
                    }
                ],
                "connectionProperties": [
                    {
                        "name": "connectionString",
                        "required": True,
                        "description": "SQL connection string"
                    },
                    {
                        "name": "timeout",
                        "required": False,
                        "description": "Connection timeout in seconds"
                    }
                ]
            },
            {
                "name": "LakeSource",
                "displayName": "Data Lake Source",
                "description": "Data lake file-based source",
                "dataTypeMapping": [
                    {
                        "sourceType": "string",
                        "targetType": "string"
                    }
                ],
                "connectionProperties": [
                    {
                        "name": "path",
                        "required": True,
                        "description": "Path to data lake location"
                    }
                ]
            }
        ]
    }


@pytest.fixture
def temp_json_file(sample_data_source_types):
    """Create a temporary JSON file with sample data."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(sample_data_source_types, f)
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
    os.unlink(temp_path)


class TestDataSourceTypesFactory:
    """Test class for DataSourceTypesFactory."""

    def test_initialization(self, temp_json_file):
        """Test factory initialization."""
        factory = DataSourceTypesFactory(temp_json_file)
        assert factory.data_source_types_object is not None
        assert factory.errors == []

    def test_get_datasource_type(self, temp_json_file):
        """Test getting a specific data source type."""
        factory = DataSourceTypesFactory(temp_json_file)
        
        # Test valid data source type
        sql_type = factory.get_datasource_type("SqlDataSource")
        assert sql_type is not None
        assert sql_type.name == "SqlDataSource"
        assert sql_type.displayName == "SQL Database"

    def test_get_datasource_type_not_found(self, temp_json_file):
        """Test getting a non-existent data source type."""
        factory = DataSourceTypesFactory(temp_json_file)
        
        # Test invalid data source type
        result = factory.get_datasource_type("NonExistentType")
        assert result is None
        assert len(factory.errors) > 0

    def test_get_datasource_type_list(self, temp_json_file):
        """Test getting list of all data source types."""
        factory = DataSourceTypesFactory(temp_json_file)
        
        types_list = factory.get_datasource_type_list()
        assert len(types_list) == 2
        assert types_list[0].name in ["SqlDataSource", "LakeSource"]
        assert types_list[1].name in ["SqlDataSource", "LakeSource"]

    def test_get_default_type_mapping(self, temp_json_file):
        """Test getting default type mappings."""
        factory = DataSourceTypesFactory(temp_json_file)
        
        # Test valid mapping
        target_type = factory.get_default_type_mapping("SqlDataSource", "varchar")
        assert target_type == "string"
        
        # Test another valid mapping
        target_type = factory.get_default_type_mapping("SqlDataSource", "int")
        assert target_type == "integer"
        
        # Test invalid mapping
        target_type = factory.get_default_type_mapping("SqlDataSource", "nonexistent")
        assert target_type is None

    def test_get_connection_properties(self, temp_json_file):
        """Test getting connection properties."""
        factory = DataSourceTypesFactory(temp_json_file)
        
        # Test SQL data source properties
        properties = factory.get_connection_properties("SqlDataSource")
        assert len(properties) == 2
        
        prop_names = [prop.name for prop in properties]
        assert "connectionString" in prop_names
        assert "timeout" in prop_names
        
        # Test Lake source properties
        properties = factory.get_connection_properties("LakeSource")
        assert len(properties) == 1
        assert properties[0].name == "path"

    def test_validate_connection_config(self, temp_json_file):
        """Test connection configuration validation."""
        factory = DataSourceTypesFactory(temp_json_file)
        
        # Test valid configuration
        valid_config = {
            "connectionString": "server=localhost;database=test",
            "timeout": "30"
        }
        assert factory.validate_connection_config("SqlDataSource", valid_config) == True
        
        # Test missing required property
        invalid_config = {
            "timeout": "30"
        }
        assert factory.validate_connection_config("SqlDataSource", invalid_config) == False
        
        # Test minimal valid configuration
        minimal_config = {
            "connectionString": "server=localhost;database=test"
        }
        assert factory.validate_connection_config("SqlDataSource", minimal_config) == True

    def test_get_required_properties(self, temp_json_file):
        """Test getting required properties list."""
        factory = DataSourceTypesFactory(temp_json_file)
        
        required_props = factory.get_required_properties("SqlDataSource")
        assert "connectionString" in required_props
        assert "timeout" not in required_props
        
        required_props = factory.get_required_properties("LakeSource")
        assert "path" in required_props

    def test_get_optional_properties(self, temp_json_file):
        """Test getting optional properties list."""
        factory = DataSourceTypesFactory(temp_json_file)
        
        optional_props = factory.get_optional_properties("SqlDataSource")
        assert "timeout" in optional_props
        assert "connectionString" not in optional_props
        
        optional_props = factory.get_optional_properties("LakeSource")
        assert len(optional_props) == 0