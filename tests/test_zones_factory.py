import pytest
import json
import tempfile
import os
from dm8gen.Factory.ZonesFactory import ZonesFactory


@pytest.fixture
def sample_zones():
    """Sample zones data for testing."""
    return {
        "$schema": "../datam8-model/schema/Zones.json",
        "type": "zone",
        "zones": [
            {
                "name": "Raw",
                "targeName": "Bronze",
                "displayName": "Raw Data Layer",
                "localFolderName": "010-Raw"
            },
            {
                "name": "Core",
                "targeName": "Silver",
                "displayName": "Core Business Layer",
                "localFolderName": "020-Core"
            },
            {
                "name": "Curated",
                "targeName": "Gold",
                "displayName": "Curated Analytics Layer",
                "localFolderName": "030-Curated"
            }
        ]
    }


@pytest.fixture
def temp_json_file(sample_zones):
    """Create a temporary JSON file with sample data."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(sample_zones, f)
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
    os.unlink(temp_path)


class TestZonesFactory:
    """Test class for ZonesFactory."""

    def test_initialization(self, temp_json_file):
        """Test factory initialization."""
        factory = ZonesFactory(temp_json_file)
        assert factory.zones_object is not None
        assert factory.errors == []

    def test_get_zone(self, temp_json_file):
        """Test getting a specific zone."""
        factory = ZonesFactory(temp_json_file)
        
        # Test valid zone
        raw_zone = factory.get_zone("Raw")
        assert raw_zone is not None
        assert raw_zone.name == "Raw"
        assert raw_zone.targeName == "Bronze"
        assert raw_zone.displayName == "Raw Data Layer"
        assert raw_zone.localFolderName == "010-Raw"

    def test_get_zone_not_found(self, temp_json_file):
        """Test getting a non-existent zone."""
        factory = ZonesFactory(temp_json_file)
        
        # Test invalid zone
        result = factory.get_zone("NonExistentZone")
        assert result is None
        assert len(factory.errors) > 0

    def test_get_zone_list(self, temp_json_file):
        """Test getting list of all zones."""
        factory = ZonesFactory(temp_json_file)
        
        zones_list = factory.get_zone_list()
        assert len(zones_list) == 3
        
        zone_names = [zone.name for zone in zones_list]
        assert "Raw" in zone_names
        assert "Core" in zone_names
        assert "Curated" in zone_names

    def test_get_target_name(self, temp_json_file):
        """Test getting target name for zones."""
        factory = ZonesFactory(temp_json_file)
        
        # Test valid mappings
        assert factory.get_target_name("Raw") == "Bronze"
        assert factory.get_target_name("Core") == "Silver"
        assert factory.get_target_name("Curated") == "Gold"
        
        # Test invalid zone
        assert factory.get_target_name("NonExistent") is None

    def test_get_folder_structure(self, temp_json_file):
        """Test getting folder structure for zones."""
        factory = ZonesFactory(temp_json_file)
        
        # Test valid folder mappings
        assert factory.get_folder_structure("Raw") == "010-Raw"
        assert factory.get_folder_structure("Core") == "020-Core"
        assert factory.get_folder_structure("Curated") == "030-Curated"
        
        # Test invalid zone
        assert factory.get_folder_structure("NonExistent") is None

    def test_get_display_name(self, temp_json_file):
        """Test getting display name for zones."""
        factory = ZonesFactory(temp_json_file)
        
        # Test valid display names
        assert factory.get_display_name("Raw") == "Raw Data Layer"
        assert factory.get_display_name("Core") == "Core Business Layer"
        assert factory.get_display_name("Curated") == "Curated Analytics Layer"
        
        # Test invalid zone
        assert factory.get_display_name("NonExistent") is None

    def test_get_zone_by_target(self, temp_json_file):
        """Test reverse lookup by target name."""
        factory = ZonesFactory(temp_json_file)
        
        # Test valid reverse lookups
        bronze_zone = factory.get_zone_by_target("Bronze")
        assert bronze_zone is not None
        assert bronze_zone.name == "Raw"
        
        silver_zone = factory.get_zone_by_target("Silver")
        assert silver_zone is not None
        assert silver_zone.name == "Core"
        
        gold_zone = factory.get_zone_by_target("Gold")
        assert gold_zone is not None
        assert gold_zone.name == "Curated"
        
        # Test invalid target
        assert factory.get_zone_by_target("NonExistent") is None

    def test_get_zone_by_folder(self, temp_json_file):
        """Test lookup by folder name."""
        factory = ZonesFactory(temp_json_file)
        
        # Test valid folder lookups
        raw_zone = factory.get_zone_by_folder("010-Raw")
        assert raw_zone is not None
        assert raw_zone.name == "Raw"
        
        core_zone = factory.get_zone_by_folder("020-Core")
        assert core_zone is not None
        assert core_zone.name == "Core"
        
        curated_zone = factory.get_zone_by_folder("030-Curated")
        assert curated_zone is not None
        assert curated_zone.name == "Curated"
        
        # Test invalid folder
        assert factory.get_zone_by_folder("999-NonExistent") is None

    def test_get_zone_names(self, temp_json_file):
        """Test getting list of zone names."""
        factory = ZonesFactory(temp_json_file)
        
        zone_names = factory.get_zone_names()
        assert len(zone_names) == 3
        assert "Raw" in zone_names
        assert "Core" in zone_names
        assert "Curated" in zone_names

    def test_get_target_names(self, temp_json_file):
        """Test getting list of target names."""
        factory = ZonesFactory(temp_json_file)
        
        target_names = factory.get_target_names()
        assert len(target_names) == 3
        assert "Bronze" in target_names
        assert "Silver" in target_names
        assert "Gold" in target_names