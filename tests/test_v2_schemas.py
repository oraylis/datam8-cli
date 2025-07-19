"""
DataM8
Copyright (C) 2024-2025 ORAYLIS GmbH

This file is part of DataM8.

DataM8 is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

DataM8 is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

Test cases for DataM8 v2 schema features.
Tests the new unified schema structure and field migrations.
"""
import json
import pytest
from pathlib import Path

# Import generated models
from dm8gen.Generated.Solution import Model as Solution
from dm8gen.Generated.Zones import Model as Zones
from dm8gen.Generated.DataSourceTypes import Model as DataSourceTypes
from dm8gen.Generated.ModelDataEntity import Model as ModelDataEntity
from dm8gen.Generated.AttributeTypes import Model as AttributeTypes


class TestV2Schemas:
    """Test v2 schema features."""
    
    @pytest.fixture
    def test_data_dir(self):
        """Path to test data directory."""
        return Path(__file__).parent
    
    def test_solution_v2_structure(self, test_data_dir):
        """Test new Solution schema with schemaVersion and modelPath."""
        sample_path = test_data_dir / "sample_solution.dm8s"
        
        with open(sample_path) as f:
            data = json.load(f)
        
        # Validate using Pydantic model
        solution = Solution.model_validate(data)
        
        # Test new v2 fields
        assert solution.schemaVersion == "2.0.0"
        assert solution.modelPath == "Model"
        
        # Test preserved fields
        assert solution.basePath == "Base"
        assert solution.generatePath == "Generate"
        assert solution.diagramPath == "Diagram"
        assert solution.outputPath == "Output"
    
    def test_zones_schema(self, test_data_dir):
        """Test new Zones schema replacing AreaTypes."""
        sample_path = test_data_dir / "sample_zones.json"
        
        with open(sample_path) as f:
            data = json.load(f)
        
        # Validate using Pydantic model
        zones = Zones.model_validate(data)
        
        # Test structure
        assert zones.type.value == "zones"
        assert len(zones.zones) == 3
        
        # Test zone properties
        raw_zone = zones.zones[0]
        assert raw_zone.name == "Raw"
        assert raw_zone.targeName == "Bronze"
        assert raw_zone.displayName == "Raw Data Layer"
        assert raw_zone.localFolderName == "010-Raw"
    
    def test_datasourcetypes_schema(self, test_data_dir):
        """Test new DataSourceTypes schema."""
        sample_path = test_data_dir / "sample_datasourcetypes.json"
        
        with open(sample_path) as f:
            data = json.load(f)
        
        # Validate using Pydantic model
        dst = DataSourceTypes.model_validate(data)
        
        # Test structure
        assert dst.type.value == "dataSourceTypes"
        assert len(dst.sourceTypes) == 2
        
        # Test SQL source type
        sql_type = dst.sourceTypes[0]
        assert sql_type.name == "SqlDataSource"
        assert sql_type.displayName == "SQL Database"
        assert sql_type.description == "Traditional SQL database connection"
        assert len(sql_type.dataTypeMapping) == 3
        assert len(sql_type.connectionProperties) == 2
    
    def test_unified_entity_schema(self, test_data_dir):
        """Test new unified ModelDataEntity schema."""
        sample_path = test_data_dir / "sample_entity.json"
        
        with open(sample_path) as f:
            data = json.load(f)
        
        # Validate using Pydantic model
        entity = ModelDataEntity.model_validate(data)
        
        # Test unified type
        assert entity.type.value == "entity"
        
        # Test entity structure
        assert entity.entity.name == "Customer"
        assert entity.entity.displayName == "Customer Entity"
        assert entity.entity.description == "Core customer information entity"
        
        # Test new v2 fields
        assert entity.entity.tags == ["customer", "core", "business"]
        assert len(entity.entity.parameters) == 2
        assert entity.entity.parameters[0].name == "scd_type"
        assert entity.entity.parameters[0].value == "SCD2"
        
        # Test attributes with v2 features
        customer_id_attr = entity.entity.attribute[0]
        assert customer_id_attr.name == "customer_id"
        assert customer_id_attr.description == "Unique customer identifier"
        assert customer_id_attr.tags == ["business_key"]
        
        # Test functions
        assert entity.functions.trigger.mode.value == "schedule"
        assert entity.functions.load.mode.value == "incremental"
        assert entity.functions.store.mode.value == "history"
    
    def test_migrated_field_structure(self, test_data_dir):
        """Test that purpose/explanation fields were properly migrated to description."""
        # Test with actual AttributeTypes data structure
        sample_data = {
            "$schema": "../datam8-model/schema/AttributeTypes.json",
            "type": "attributeType",
            "items": [
                {
                    "name": "TestAttribute",
                    "displayName": "Test Attribute",
                    "description": "Migrated from purpose/explanation fields",
                    "tags": ["test", "migration"],
                    "parameters": [
                        {"name": "param1", "value": "value1"}
                    ],
                    "defaultType": "string"
                }
            ]
        }
        
        # Validate using Pydantic model
        attr_types = AttributeTypes.model_validate(sample_data)
        
        # Test migrated structure
        test_attr = attr_types.items[0]
        assert test_attr.name == "TestAttribute"
        assert test_attr.description == "Migrated from purpose/explanation fields"
        assert test_attr.tags == ["test", "migration"]
        assert len(test_attr.parameters) == 1
        assert test_attr.parameters[0].name == "param1"
        assert test_attr.parameters[0].value == "value1"
        
        # Ensure old fields don't exist (would be caught by Pydantic validation)
        assert not hasattr(test_attr, 'purpose')
        assert not hasattr(test_attr, 'explanation')
    
    def test_json_schema_validation_all_samples(self, test_data_dir):
        """Test JSON schema validation for all sample files using their schema references."""
        import jsonschema
        
        # Define test cases: (sample_file, expected_schema_file)
        test_cases = [
            ("sample_solution.dm8s", "Solution.json"),
            ("sample_zones.json", "Zones.json"),
            ("sample_datasourcetypes.json", "DataSourceTypes.json"),
            ("sample_entity.json", "ModelDataEntity.json")
        ]
        
        for sample_file, schema_file in test_cases:
            with self.subtest(sample_file=sample_file):
                # Load sample data
                sample_path = test_data_dir / sample_file
                with open(sample_path) as f:
                    sample_data = json.load(f)
                
                # Load corresponding schema
                schema_path = test_data_dir.parent / "datam8-model" / "schema" / schema_file
                with open(schema_path) as f:
                    schema_data = json.load(f)
                
                # Validate sample against schema
                try:
                    jsonschema.validate(instance=sample_data, schema=schema_data)
                except jsonschema.ValidationError as e:
                    pytest.fail(f"Schema validation failed for {sample_file}: {e.message}")
                except FileNotFoundError:
                    pytest.skip(f"Schema file not found: {schema_path}")
    
    def test_pydantic_validation_all_samples(self, test_data_dir):
        """Test Pydantic model validation for all sample files."""
        # Test cases: (sample_file, pydantic_model)
        test_cases = [
            ("sample_solution.dm8s", Solution),
            ("sample_zones.json", Zones),
            ("sample_datasourcetypes.json", DataSourceTypes),
            ("sample_entity.json", ModelDataEntity)
        ]
        
        for sample_file, model_class in test_cases:
            with self.subtest(sample_file=sample_file):
                # Load sample data
                sample_path = test_data_dir / sample_file
                with open(sample_path) as f:
                    sample_data = json.load(f)
                
                # Validate using Pydantic model
                try:
                    model_instance = model_class.model_validate(sample_data)
                    assert model_instance is not None
                except Exception as e:
                    pytest.fail(f"Pydantic validation failed for {sample_file} with {model_class.__name__}: {str(e)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])