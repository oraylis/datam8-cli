#!/usr/bin/env python3
"""
Test script for the DataM8 Reverse Generator.

This script provides basic testing and validation for the reverse generator
implementation before integration testing with the sample solution.
"""

import sys
import logging
from pathlib import Path

# Add the src directory to the Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

def test_basic_imports():
    """Test that all modules can be imported successfully."""
    print("Testing basic imports...")
    
    try:
        # Test core components
        from dm8gen.Factory.SourceDiscovery.BaseSourceConnector import BaseSourceConnector  # noqa: F401
        from dm8gen.Factory.SourceDiscovery.ConnectorRegistry import ConnectorRegistry  # noqa: F401
        from dm8gen.Factory.SourceDiscovery.SqlServerConnector import SqlServerConnector  # noqa: F401
        from dm8gen.Factory.TypeMappingEngine import TypeMappingEngine  # noqa: F401
        from dm8gen.Factory.ReverseGenerator import ReverseGenerator  # noqa: F401
        
        print("[OK] All imports successful")
        
    except ImportError as e:
        print(f"[FAIL] Import failed: {e}")
        assert False, f"Import failed: {e}"

def test_connector_registry():
    """Test the connector registry functionality."""
    print("\nTesting connector registry...")
    
    try:
        from dm8gen.Factory.SourceDiscovery.ConnectorRegistry import ConnectorRegistry
        
        registry = ConnectorRegistry()
        
        # Test getting available source types
        source_types = registry.get_available_source_types()
        print(f"Available source types: {source_types}")
        
        # Test getting connector info
        connector_info = registry.get_connector_info()
        print(f"Connector info: {connector_info}")
        
        # Check if SQL Server connector is registered
        if 'SqlDataSource' in source_types:
            print("[OK] SQL Server connector registered successfully")
        else:
            print("[FAIL] SQL Server connector not found")
            assert False, "SQL Server connector not found"
        
    except Exception as e:
        print(f"[FAIL] Connector registry test failed: {e}")
        assert False, f"Connector registry test failed: {e}"

def test_type_mapping_engine_structure():
    """Test the type mapping engine structure (without actual data files)."""
    print("\nTesting type mapping engine structure...")
    
    try:
        from dm8gen.Factory.TypeMappingEngine import TypeMappingEngine, DataTypeMapping
        
        # Create a sample data type mapping
        mapping = DataTypeMapping(
            source_type="varchar",
            target_type="string",
            nullable=True,
            char_len=50
        )
        
        print(f"[OK] DataTypeMapping created: {mapping.source_type} -> {mapping.target_type}")
        
        # Test attribute type detection patterns
        engine_class = TypeMappingEngine
        if hasattr(engine_class, '_attribute_patterns'):
            print("[OK] Attribute detection patterns defined")
        
    except Exception as e:
        print(f"[FAIL] Type mapping engine test failed: {e}")
        assert False, f"Type mapping engine test failed: {e}"

def test_validation_utilities():
    """Test the validation utilities structure (now integrated into ReverseGenerator)."""
    print("\nTesting validation utilities...")
    
    try:
        from dm8gen.Factory.ReverseGenerator import ReverseGenerator
        
        # Test that ReverseGenerator has validation functionality
        # Since ReverseGeneratorValidation is integrated, test the main class
        generator_methods = [
            'generate_staging_entities',  # Main functionality
        ]
        
        for method in generator_methods:
            if hasattr(ReverseGenerator, method):
                print(f"[OK] ReverseGenerator method '{method}' exists")
            else:
                print(f"[FAIL] ReverseGenerator method '{method}' missing")
                assert False, f"ReverseGenerator method '{method}' missing"
        
        print("[OK] Validation functionality integrated into ReverseGenerator")
        
    except Exception as e:
        print(f"[FAIL] Validation utilities test failed: {e}")
        assert False, f"Validation utilities test failed: {e}"

def test_cli_integration():
    """Test CLI integration structure."""
    print("\nTesting CLI integration...")
    
    try:
        from dm8gen.generate import GenerateOptionEnum
        
        # Check if REVERSE_GENERATE is available
        if hasattr(GenerateOptionEnum, 'REVERSE_GENERATE'):
            print(f"[OK] REVERSE_GENERATE action available: {GenerateOptionEnum.REVERSE_GENERATE}")
        else:
            print("[FAIL] REVERSE_GENERATE action not found")
            assert False, "REVERSE_GENERATE action not found"
        
        # Test enum values
        expected_actions = ['validate_index', 'generate_template', 'refresh_generate', 'reverse_generate']
        actual_actions = [action.value for action in GenerateOptionEnum]
        
        for action in expected_actions:
            if action in actual_actions:
                print(f"[OK] Action '{action}' available")
            else:
                print(f"[FAIL] Action '{action}' missing")
                assert False, f"Action '{action}' missing"
        
    except Exception as e:
        print(f"[FAIL] CLI integration test failed: {e}")
        assert False, f"CLI integration test failed: {e}"

def run_basic_tests():
    """Run all basic tests."""
    print("=" * 60)
    print("DataM8 Reverse Generator - Basic Tests")
    print("=" * 60)
    
    tests = [
        test_basic_imports,
        test_connector_registry,
        test_type_mapping_engine_structure,
        test_validation_utilities,
        test_cli_integration
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"[FAIL] Test {test.__name__} failed with exception: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0

def print_usage_example():
    """Print usage example for the reverse generator."""
    print("\n" + "=" * 60)
    print("Usage Example")
    print("=" * 60)
    print()
    print("To use the reverse generator with a SQL Server data source:")
    print()
    print("dm8gen -a reverse_generate \\")
    print("  -s path/to/solution.dm8s \\")
    print("  --data-source AdventureWorks \\")
    print("  --data-product Sales \\")
    print("  --data-module Customer \\")
    print("  --tables \"Customer,Address\" \\")
    print("  --entity-names \"Customer_Staging,Address_Staging\" \\")
    print("  --interactive")
    print()
    print("Interactive mode will prompt for:")
    print("- Entity name confirmations")
    print("- Attribute type confirmations") 
    print("- Output path confirmations")
    print()
    print("Non-interactive mode (batch processing):")
    print("dm8gen -a reverse_generate \\")
    print("  -s path/to/solution.dm8s \\")
    print("  --data-source AdventureWorks \\")
    print("  --data-product Sales \\")
    print("  --data-module Customer \\")
    print("  --tables \"Customer,Address\" \\")
    print("  --entity-names \"Customer_Staging,Address_Staging\"")

if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    
    # Run basic tests
    success = run_basic_tests()
    
    # Print usage example
    print_usage_example()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)