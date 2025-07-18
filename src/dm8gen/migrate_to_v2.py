#!/usr/bin/env python3
"""
DataM8 V1 to V2 Migration Script

This script migrates existing zone-specific JSON entity files (Raw, Stage, Core, Curated)
to the unified ModelDataEntity.json v2 schema format.

Usage:
    dm8gen -a migrate_to_v2 -s solution.dm8s -dest output_v2/

Key Transformations:
- Raw: function.dataSource -> functions.sources[].dataSource
- Stage: function.attributeMapping -> functions.sources[].mapping  
- Core: function.source[] -> functions.sources[]
- Curated: function[] -> functions.transformations[]
"""

import json
import os
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass

from dm8gen.Helper.Helper import Helper


@dataclass
class MigrationResult:
    """Result of migration operation"""
    success: bool
    message: str
    source_file: str
    target_file: str
    warnings: List[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class V2EntityMigrator:
    """Main migration class for converting V1 entities to V2 format"""
    
    def __init__(self, solution_path: str, destination_path: str):
        self.solution_path = Path(solution_path)
        self.destination_path = Path(destination_path)
        self.logger = Helper.start_logger("V2EntityMigrator")
        self.solution_config = self._load_solution_config()
        
    def _load_solution_config(self) -> Dict[str, Any]:
        """Load solution configuration from .dm8s file"""
        try:
            with open(self.solution_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load solution config: {e}")
            raise
    
    def migrate_solution(self) -> List[MigrationResult]:
        """Migrate entire solution from V1 to V2 format"""
        results = []
        
        # Create destination directory
        self.destination_path.mkdir(parents=True, exist_ok=True)
        
        # Copy solution file
        shutil.copy2(self.solution_path, self.destination_path / self.solution_path.name)
        
        # Copy Base directory (unchanged)
        base_path = self.solution_path.parent / self.solution_config.get('basePath', 'Base')
        if base_path.exists():
            shutil.copytree(base_path, self.destination_path / 'Base', dirs_exist_ok=True)
        
        # Migrate each zone
        zones = ['Raw', 'Staging', 'Core', 'Curated']
        for zone in zones:
            zone_results = self._migrate_zone(zone)
            results.extend(zone_results)
        
        return results
    
    def _migrate_zone(self, zone: str) -> List[MigrationResult]:
        """Migrate all entities in a specific zone"""
        results = []
        
        # Get zone path from solution config
        zone_path_key = f"{zone.lower()}Path" if zone != 'Staging' else 'stagingPath'
        zone_path = self.solution_path.parent / self.solution_config.get(zone_path_key, zone)
        
        if not zone_path.exists():
            self.logger.warning(f"Zone path does not exist: {zone_path}")
            return results
        
        # Find all JSON files in zone
        for json_file in zone_path.rglob('*.json'):
            relative_path = json_file.relative_to(zone_path)
            result = self._migrate_entity_file(json_file, zone, relative_path)
            results.append(result)
        
        return results
    
    def _migrate_entity_file(self, source_file: Path, zone: str, relative_path: Path) -> MigrationResult:
        """Migrate a single entity file"""
        try:
            # Load source entity
            with open(source_file, 'r', encoding='utf-8') as f:
                source_entity = json.load(f)
            
            # Convert to V2 format
            v2_entity = self._convert_entity_to_v2(source_entity, zone, relative_path)
            
            # Create target directory
            target_dir = self.destination_path / zone / relative_path.parent
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # Write converted entity
            target_file = target_dir / relative_path.name
            with open(target_file, 'w', encoding='utf-8') as f:
                json.dump(v2_entity, f, indent=2, ensure_ascii=False)
            
            return MigrationResult(
                success=True,
                message=f"Successfully migrated {zone} entity",
                source_file=str(source_file),
                target_file=str(target_file)
            )
            
        except Exception as e:
            return MigrationResult(
                success=False,
                message=f"Failed to migrate entity: {str(e)}",
                source_file=str(source_file),
                target_file=""
            )
    
    def _convert_entity_to_v2(self, source_entity: Dict[str, Any], zone: str, relative_path: Path) -> Dict[str, Any]:
        """Convert a V1 entity to V2 unified format"""
        
        # Extract entity and function data
        entity_data = source_entity.get('entity', {})
        function_data = source_entity.get('function', {})
        
        # Create V2 entity structure
        v2_entity = {
            "$schema": "../../../datam8-model/schema/ModelDataEntity.json",
            "type": "entity",
            "entity": self._convert_entity_section(entity_data, relative_path),
            "functions": self._convert_functions_section(function_data, zone)
        }
        
        return v2_entity
    
    def _convert_entity_section(self, entity_data: Dict[str, Any], relative_path: Path) -> Dict[str, Any]:
        """Convert entity section to V2 format"""
        
        # Start with existing entity data
        v2_entity = dict(entity_data)
        
        # Add deprecation warning for dataProduct/dataModule
        if 'dataProduct' in v2_entity:
            v2_entity['dataProduct'] = v2_entity['dataProduct']  # Keep for transition
        if 'dataModule' in v2_entity:
            v2_entity['dataModule'] = v2_entity['dataModule']    # Keep for transition
        
        # Ensure required fields exist
        if 'name' not in v2_entity:
            v2_entity['name'] = relative_path.stem
        if 'displayName' not in v2_entity:
            v2_entity['displayName'] = v2_entity['name']
        
        # Convert attribute array name if needed
        if 'attribute' in v2_entity:
            v2_entity['attribute'] = v2_entity['attribute']
        
        # Ensure relationship array exists for Core/Curated
        if 'relationship' not in v2_entity:
            v2_entity['relationship'] = []
        
        return v2_entity
    
    def _convert_functions_section(self, function_data: Dict[str, Any], zone: str) -> Dict[str, Any]:
        """Convert function section to V2 unified format"""
        
        functions = {}
        
        # Convert based on zone type
        if zone == 'Raw':
            functions = self._convert_raw_functions(function_data)
        elif zone == 'Staging':
            functions = self._convert_stage_functions(function_data)
        elif zone == 'Core':
            functions = self._convert_core_functions(function_data)
        elif zone == 'Curated':
            functions = self._convert_curated_functions(function_data)
        
        return functions
    
    def _convert_raw_functions(self, function_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Raw function to V2 format"""
        functions = {
            "trigger": {"mode": "module"},
            "load": {"mode": "full"},
            "store": {"mode": "overwrite"}
        }
        
        # Convert dataSource to sources
        if 'dataSource' in function_data and 'sourceLocation' in function_data:
            functions["sources"] = [{
                "type": "source",
                "dataSource": function_data['dataSource'],
                "sourceLocation": function_data['sourceLocation']
            }]
        
        return functions
    
    def _convert_stage_functions(self, function_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Stage function to V2 format"""
        functions = {
            "trigger": {"mode": "module"},
            "load": {"mode": "incremental"},
            "store": {"mode": "overwrite"}
        }
        
        # Convert dataSource and attributeMapping to sources
        if 'dataSource' in function_data and 'sourceLocation' in function_data:
            source = {
                "type": "source",
                "dataSource": function_data['dataSource'],
                "sourceLocation": function_data['sourceLocation']
            }
            
            # Convert attributeMapping to mapping
            if 'attributeMapping' in function_data:
                mapping = []
                for attr_map in function_data['attributeMapping']:
                    mapping.append({
                        "sourceName": attr_map['source'],
                        "name": attr_map['target']
                    })
                source["mapping"] = mapping
            
            functions["sources"] = [source]
        
        return functions
    
    def _convert_core_functions(self, function_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Core function to V2 format"""
        functions = {
            "trigger": {"mode": "module"},
            "load": {"mode": "incremental"},
            "store": {"mode": "history"}
        }
        
        # Convert source array to sources
        if 'source' in function_data:
            sources = []
            for source_item in function_data['source']:
                if 'dm8l' in source_item:
                    converted_source = {
                        "type": "model",
                        "dm8l": source_item['dm8l']
                    }
                    
                    # Convert mapping if present
                    if 'mapping' in source_item:
                        converted_source["mapping"] = source_item['mapping']
                    
                    # Convert filter if present
                    if 'filter' in source_item:
                        converted_source["filter"] = source_item['filter']
                    
                    sources.append(converted_source)
            
            functions["sources"] = sources
        
        return functions
    
    def _convert_curated_functions(self, function_data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> Dict[str, Any]:
        """Convert Curated function(s) to V2 format"""
        functions = {
            "trigger": {"mode": "schedule"},
            "load": {"mode": "period"},
            "store": {"mode": "snapshot"}
        }
        
        # Handle both single function and function array
        curated_functions = function_data if isinstance(function_data, list) else [function_data]
        
        transformations = []
        for i, func in enumerate(curated_functions):
            if isinstance(func, dict) and 'name' in func:
                transformation = {
                    "stepNo": i + 1,
                    "kind": "custom",
                    "name": func['name']
                }
                transformations.append(transformation)
        
        if transformations:
            functions["transformations"] = transformations
        
        return functions
    
    def print_migration_summary(self, results: List[MigrationResult]):
        """Print summary of migration results"""
        total = len(results)
        successful = sum(1 for r in results if r.success)
        failed = total - successful
        
        print(f"\n=== Migration Summary ===")
        print(f"Total files processed: {total}")
        print(f"Successfully migrated: {successful}")
        print(f"Failed migrations: {failed}")
        
        if failed > 0:
            print(f"\nFailed migrations:")
            for result in results:
                if not result.success:
                    print(f"  - {result.source_file}: {result.message}")
        
        print(f"\nMigration complete. Output available at: {self.destination_path}")


def migrate_solution_to_v2(solution_path: str, destination_path: str) -> bool:
    """Main entry point for migration"""
    try:
        migrator = V2EntityMigrator(solution_path, destination_path)
        results = migrator.migrate_solution()
        migrator.print_migration_summary(results)
        
        # Return success if all migrations succeeded
        return all(r.success for r in results)
        
    except Exception as e:
        print(f"Migration failed: {str(e)}")
        return False


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) != 3:
        print("Usage: python migrate_to_v2.py <solution.dm8s> <output_directory>")
        sys.exit(1)
    
    solution_path = sys.argv[1]
    output_path = sys.argv[2]
    
    success = migrate_solution_to_v2(solution_path, output_path)
    sys.exit(0 if success else 1)