# DataM8 Generator - Comprehensive Documentation

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Data Model](#data-model)
4. [Code Generation](#code-generation)
5. [Usage Guide](#usage-guide)
6. [Development](#development)
7. [Testing & Validation](#testing--validation)
8. [Reference](#reference)

---

## Overview

**DataM8 Generator** is an enterprise-grade data pipeline automation framework developed by ORAYLIS GmbH. It transforms JSON schema definitions into complete data warehouse solutions using template-based code generation.

### Key Features
- **Multi-layered Architecture**: Raw → Stage → Core → Curated data pipeline
- **Template-driven Generation**: Jinja2-based flexible code generation
- **Schema-first Design**: JSON Schema validation with Pydantic models
- **Platform Agnostic**: Supports multiple output formats and platforms
- **Enterprise Ready**: Comprehensive error handling, logging, and validation

### Technology Stack
- **Python 3.8+** with Pydantic 2.8+ for data validation
- **Jinja2 3.1+** for template rendering
- **Typer** for CLI interface
- **pytest** for comprehensive testing
- **GPL-3.0 License** for open-source data tooling

---

## Architecture

### Core Components

```
datam8-generator/
├── src/dm8gen/
│   ├── Factory/          # Entity processing factories
│   ├── Generated/        # Auto-generated Pydantic models
│   ├── Helper/           # Utility functions
│   ├── cli.py           # Command-line interface
│   └── generate.py      # Core generation engine
├── datam8-model/        # Schema definitions
├── template/            # Code generation templates
└── tests/               # Test suites
```

### Design Patterns

#### 1. Unified Factory Pattern
All entity processing uses the unified factory:
- **UnifiedEntityFactory**: Handles all entity types (Raw, Stage, Core, Curated) with v2 schema

#### 2. Template Engine
- **Jinja2-based**: Flexible template inheritance
- **Multi-format Output**: Python, SQL, JSON, YAML
- **Auto-formatting**: Integrated code beautification
- **Error Handling**: Comprehensive template debugging

#### 3. Schema Validation
- **Pydantic Models**: Runtime validation and serialization
- **JSON Schema**: Design-time validation
- **Type Safety**: Strong typing throughout pipeline

---

## Data Model

### Data Pipeline Layers

#### 1. Raw Layer
- **Purpose**: Source-aligned data ingestion
- **Characteristics**: Preserves original data types and structure
- **Entity Structure**: Minimal transformation, direct source mapping

```json
{
  "type": "RawEntity",
  "dataSource": "AdventureWorks",
  "sourceLocation": "[SalesLT].[Customer]",
  "attributes": [
    {
      "name": "CustomerID",
      "type": "int",
      "sourceColumn": "CustomerID"
    }
  ]
}
```

#### 2. Stage Layer
- **Purpose**: Data cleansing and standardization
- **Characteristics**: Type standardization, quality checks
- **Features**: Attribute mapping, data validation

```json
{
  "type": "StageEntity",
  "sourceLocation": "raw/Sales/Customer/Customer",
  "attributeMapping": [
    {
      "source": "CustomerID",
      "target": "CustomerID"
    }
  ],
  "attributes": [
    {
      "name": "CustomerID",
      "type": "int",
      "attributeType": "ID"
    }
  ]
}
```

#### 3. Core Layer
- **Purpose**: Business-focused integration
- **Characteristics**: Entity relationships, business keys, SCD support
- **Features**: Multi-source integration, complex transformations

```json
{
  "type": "CoreEntity",
  "dataProduct": "Sales",
  "dataModule": "Customer",
  "source": [
    {
      "dm8l": "/Stage/Sales/Customer/Customer_DE",
      "mapping": [
        {
          "name": "CustomerID",
          "sourceName": "KundenID"
        }
      ]
    }
  ],
  "relationships": [
    {
      "dm8lKey": "/Core/Sales/Other/Address",
      "role": "many-to-one",
      "fields": [
        {
          "name": "AddressID",
          "referenceName": "AddressID"
        }
      ]
    }
  ]
}
```

#### 4. Curated Layer
- **Purpose**: Analytics-ready dimensional models
- **Characteristics**: Aggregations, computed columns, optimized for BI
- **Features**: Scheduled processing, merge strategies

```json
{
  "type": "CuratedEntity",
  "baseEntity": "/Core/Sales/Customer/Customer",
  "curatedFunctions": [
    {
      "name": "Customer_Compute",
      "type": "python",
      "fileName": "Customer_Compute.py",
      "mergeType": "merge",
      "frequency": "daily"
    }
  ]
}
```

### Schema Architecture

#### Foundation Schemas
- **Solution.json**: Root configuration and path definitions
- **Zones.json**: Data processing layer definitions
- **Index.json**: Entity registry and dependency tracking

#### Type System
- **DataTypes.json**: Platform-specific type mappings
- **AttributeTypes.json**: Semantic attribute templates
- **DataSourceTypes.json**: Connection template definitions

#### Organization
- **DataProducts.json**: Business domain definitions
- **DataModules.json**: Functional grouping within domains
- **DataSources.json**: Concrete data source instances

---

## Code Generation

### Template System

#### Template Structure
```
template/
├── Core Templates
│   ├── Enum.jinja2          # Enum classes
│   ├── dataclass.jinja2     # Python dataclasses
│   └── TypedDict.jinja2     # TypedDict definitions
├── Pydantic Templates
│   ├── pydantic_v2/         # Pydantic v2 support
│   │   ├── BaseModel.jinja2
│   │   └── RootModel.jinja2
└── Platform Templates
    └── databricks-v2/       # Databricks-specific templates
```

#### Template Features
- **Inheritance**: `{% extends %}` and `{% include %}` support
- **Conditional Logic**: Dynamic template selection
- **Multi-file Output**: Single template generates multiple files
- **Auto-formatting**: Integrated Python and SQL formatting

### Generation Process

#### 1. Schema Validation
```python
# Pydantic model validation
solution = Solution.model_validate_json(solution_json)
```

#### 2. Entity Processing
```python
# Factory pattern for entity processing
factory = EntityFactory.create(entity_type)
processed_entity = factory.process(entity_json)
```

#### 3. Template Rendering
```python
# Jinja2 template rendering
template = jinja_env.get_template('template.jinja2')
output = template.render(model=entity, **context)
```

#### 4. Output Generation
```python
# Multi-file output with formatting
for file_path, content in output_files:
    formatted_content = format_content(content, file_type)
    write_file(file_path, formatted_content)
```

---

## Usage Guide

### Command Line Interface

#### Basic Commands
```bash
# Validate entity index
dm8gen -a validate_index -s solution.json

# Generate code from templates
dm8gen -a generate_template -s solution.json -src templates/ -dest output/

# Full refresh and generate
dm8gen -a refresh_generate -s solution.json -src templates/ -dest output/
```

#### Advanced Options
```bash
# Custom module loading
dm8gen -a generate_template -s solution.json -src templates/ -dest output/ -m custom_module.py

# Logging configuration
dm8gen -a generate_template -s solution.json -src templates/ -dest output/ -ll DEBUG
```

### Project Structure

#### Recommended Layout
```
my-data-project/
├── solution.json           # Solution configuration
├── Base/                   # Foundation definitions
│   ├── DataProducts.json
│   ├── DataSources.json
│   ├── DataTypes.json
│   └── AttributeTypes.json
├── Raw/                    # Raw layer entities
├── Staging/                # Staging layer entities
├── Core/                   # Core layer entities
├── Curated/                # Curated layer entities
├── Generate/               # Custom templates
└── Output/                 # Generated code
```

#### Entity Definition Example
```json
{
  "type": "CoreEntity",
  "dataProduct": "Sales",
  "dataModule": "Customer",
  "attributes": [
    {
      "name": "CustomerID",
      "type": "int",
      "attributeType": "ID",
      "businessKey": true
    },
    {
      "name": "FirstName",
      "type": "string",
      "attributeType": "Name"
    }
  ],
  "source": [
    {
      "dm8l": "/Stage/Sales/Customer/Customer",
      "mapping": [
        {
          "name": "CustomerID",
          "sourceName": "CustomerID"
        }
      ]
    }
  ]
}
```

### Best Practices

#### 1. Schema Design
- Use semantic attribute types for consistency
- Define business keys for each core entity
- Implement proper data module organization
- Document entity relationships clearly

#### 2. Template Development
- Follow template inheritance patterns
- Use macros for reusable components
- Implement proper error handling
- Test templates with sample data

#### 3. Project Organization
- Separate concerns by layer (Raw/Stage/Core/Curated)
- Use meaningful naming conventions
- Maintain clean directory structure
- Version control all configurations

---

## Development

### Setup Environment

#### Prerequisites
```bash
# Python 3.8+ with pip/uv
python --version  # >= 3.8
pip install uv    # Modern package manager
```

#### Installation
```bash
# Clone repository
git clone https://github.com/oraylis/datam8-generator.git
cd datam8-generator

# Install dependencies
uv sync

# Install in development mode
uv pip install -e .
```

#### Development Tools
```bash
# Run tests
pytest tests/

# Code formatting
ruff format src/

# Type checking
mypy src/dm8gen/
```

### Contributing

#### Code Standards
- **PEP 8**: Follow Python style guidelines
- **Type Hints**: Use type annotations throughout
- **Documentation**: Comprehensive docstrings
- **Testing**: Unit tests for all functionality

#### Testing Strategy
```bash
# Run all tests
pytest

# Run specific test categories
pytest tests/test_010_model.py          # Model tests
pytest tests/test_020_helper.py         # Helper tests
pytest tests/test_050_generate.py       # Generation tests
```

#### Template Development
1. Create template in `template/` directory
2. Use proper Jinja2 syntax and inheritance
3. Add multi-file output markers if needed
4. Test with sample data
5. Document template variables

---

## Reference

### CLI Reference

#### Commands
| Command | Description |
|---------|-------------|
| `validate_index` | Validates and builds entity index |
| `generate_template` | Generates code from templates |
| `refresh_generate` | Full refresh and generation |

#### Options
| Option | Description | Default |
|--------|-------------|---------|
| `-s, --solution` | Solution file path | Required |
| `-a, --action` | Action to perform | Required |
| `-src, --source` | Template source directory | `Generate/` |
| `-dest, --destination` | Output directory | `Output/` |
| `-m, --module` | Custom module to load | None |
| `-ll, --log-level` | Logging level | `INFO` |

### Schema Reference

#### Entity Types
- **RawEntity**: Source data ingestion
- **StageEntity**: Data cleansing and standardization
- **CoreEntity**: Business logic and relationships
- **CuratedEntity**: Analytics and aggregation

#### Attribute Types
- **ID**: Identifier fields
- **Name**: Text name fields
- **Description**: Descriptive text
- **Amount**: Monetary values
- **Date**: Date values
- **DateTime**: Timestamp values
- **Boolean**: True/false values
- **Email**: Email addresses
- **Phone**: Phone numbers
- **URL**: Web addresses

#### Data Types
- **string**: Text data
- **int**: Integer numbers
- **float**: Decimal numbers
- **boolean**: True/false values
- **datetime**: Date/time values
- **date**: Date-only values
- **time**: Time-only values

### API Reference

#### Core Classes
```python
# Main generation class
from dm8gen.generate import Generate
generator = Generate(solution_path, action, source_path, destination_path)

# Model system
from dm8gen.Factory.Model import Model
model = Model(solution_path)

# Unified entity factory
from dm8gen.Factory.UnifiedEntityFactory import UnifiedEntityFactory
factory = UnifiedEntityFactory(entity_path, log_level)

# Template engine
from dm8gen.Factory.Jinja2Factory import Jinja2Factory
template_engine = Jinja2Factory(template_paths)
```

#### Helper Functions
```python
# JSON utilities
from dm8gen.Helper.Helper import Helper
data = Helper.read_json(file_path)
Helper.write_json(file_path, data)

# Logging
from dm8gen.Helper.Helper import Helper
Helper.get_logger("dm8gen", level="INFO")
```

### Error Handling

#### Common Errors
- **Schema Validation**: Pydantic model validation failures
- **Template Syntax**: Jinja2 template syntax errors
- **File System**: Path resolution and permission issues
- **Dependency**: Missing or circular entity dependencies

#### Debugging Tips
1. Use `--log-level DEBUG` for detailed output
2. Check schema validation errors carefully
3. Validate JSON syntax before processing
4. Verify template paths and permissions
5. Review entity dependencies and locators

---

## Testing & Validation

### Overview

DataM8 provides comprehensive testing and validation capabilities across three main components:
- **Model Component** (`datam8-model/`): Schema validation and reference testing
- **Generator Component** (`datam8-generator/`): Unit tests, integration tests, and template generation
- **Sample Solution** (`datam8-sample-solution/`): End-to-end validation and entity testing

### Environment Setup

#### Prerequisites
```bash
# Ensure Python 3.8+ is available
python --version  # >= 3.8

# For schema validation only (basic testing)
# No additional dependencies needed - uses built-in jsonschema

# For full testing (unit tests, CLI commands)
pip install -e ".[dev]"
# or using uv (if available)
uv sync --group dev

# Alternative: Install individual dependencies (TESTED and WORKING)
pip install pydantic typer jinja2 jsonschema pytest pytest-cases sqlparse autopep8
```

#### Environment Variables
```bash
# Set solution path for testing (optional)
# Note: Assumes datam8-generator and datam8-sample-solution are sibling directories
export DATAM8_SOLUTION_PATH="../datam8-sample-solution"

# Set Python version if needed (adjust to available version)
pyenv local 3.10.2  # or available version like 3.8, 3.9, 3.11

# Add source directory to Python path for testing without installation
export PYTHONPATH="${PWD}/src:${PYTHONPATH}"
```

### Schema Validation

#### Validate JSON Schema Structure
```bash
# Test basic schema loading
python -c "
import json
schema = json.load(open('datam8-model/schema/ModelDataEntity.json'))
print('Schema loaded successfully, definitions:', len(schema.get('definitions', {})))
"

# Validate schema references resolution
python -c "
import json, jsonschema, os
with open('datam8-model/schema/ModelDataEntity.json', 'r') as f:
    schema = json.load(f)
resolver = jsonschema.RefResolver(
    base_uri='file://' + os.path.abspath('datam8-model/schema/') + '/',
    referrer=schema
)
validator = jsonschema.Draft7Validator(schema, resolver=resolver)
print('Schema validation setup successful')
"
```

#### Test Enhanced Parameter Types
```bash
# Validate new parameter value types (string, object, number, boolean)
python -c "
import json, jsonschema
with open('datam8-model/schema/common/Parameter.json', 'r') as f:
    param_schema = json.load(f)
validator = jsonschema.Draft7Validator(param_schema)

test_cases = [
    {'name': 'string_param', 'value': 'hello'},
    {'name': 'number_param', 'value': 42},
    {'name': 'bool_param', 'value': True},
    {'name': 'object_param', 'value': {'key': 'value'}}
]

for test_case in test_cases:
    try:
        validator.validate(test_case)
        print(f'✓ {test_case[\"name\"]}: {type(test_case[\"value\"]).__name__}')
    except Exception as e:
        print(f'✗ {test_case[\"name\"]}: {str(e)}')
"
```

### Unit Testing

#### Run All Tests
```bash
# From datam8-generator directory (requires dependencies installed)
pytest

# Run with verbose output
pytest -v

# Run specific test files
pytest tests/test_010_model.py
pytest tests/test_020_helper.py
pytest tests/test_050_generate.py

# Check if tests can be discovered (without running)
pytest --collect-only

# Note: If you get "ModuleNotFoundError: No module named 'pydantic'", 
# install dependencies first: pip install pydantic typer jinja2 jsonschema pytest pytest-cases sqlparse autopep8

# TESTED WORKING EXAMPLES:
# Run specific test with environment variable:
DATAM8_SOLUTION_PATH="/Users/fabio/Documents/ORAYLIS/DataM8/Repos/datam8-sample-solution" pytest tests/test_010_model.py::test_perform_initial_checks -v
```

#### Run Tests with Different Targets
```bash
# Test with specific template target
pytest tests/test_050_generate.py --target=databricks-lake

# Test with custom solution path
pytest --solution-path="/path/to/custom/solution"
```

#### Test Categories
```bash
# Model validation tests
pytest tests/test_010_model.py -v

# Helper function tests
pytest tests/test_020_helper.py -v

# Template generation tests
pytest tests/test_050_generate.py -v

# V2 schema validation tests
pytest tests/test_v2_schemas.py -v

# Factory tests
pytest tests/test_datasourcetypes_factory.py -v
pytest tests/test_zones_factory.py -v
```

### Integration Testing

#### Complete Pipeline Validation
```bash
# Validate entity index and perform checks
python -c "
from dm8gen.Factory.Model import Model
model = Model('/path/to/solution.dm8s')
model.validate_index(full_index_scan=True)
result = model.perform_initial_checks('raw', 'stage', 'core', 'curated')
print(f'Validation result: {result}')
"
```

#### CLI Testing

**Setup for uv (from datam8-generator directory):**
```bash
# Install uv if not available
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

# Install dependencies and set up environment
uv sync
uv pip install -e .
```

**Commands:**
```bash
# Test index validation (from datam8-generator directory)
# Note: All relative paths assume datam8-generator and datam8-sample-solution are sibling directories
PYTHONPATH=src uv run python -m dm8gen.cli -a validate_index -s /path/to/solution.dm8s

# Test template generation with modules (for macro imports)
PYTHONPATH=src uv run python -m dm8gen.cli -a generate_template -s /path/to/solution.dm8s -src Generate -dest Output -m Generate/databricks-lake/__modules

# Test full refresh and generation
PYTHONPATH=src uv run python -m dm8gen.cli -a refresh_generate -s /path/to/solution.dm8s -src Generate/ -dest Output/

# Alternative: Use Python module if uv not available
PYTHONPATH=src python -m dm8gen.cli -a validate_index -s /path/to/solution.dm8s

# Note: CLI commands require dependencies installed
# Template generation uses modules parameter (-m) for helper modules and macro imports
# Option 1 (Recommended): Use uv if available: uv sync && PYTHONPATH=src uv run python -m dm8gen.cli
# Option 2 (Fallback): Use Python module: pip install deps + PYTHONPATH=src python -m dm8gen.cli
# Note: The dm8gen script installation has path issues, use python -m dm8gen.cli instead

# TESTED WORKING EXAMPLES:
# Option 1: Using uv (TESTED and WORKING - from datam8-generator directory):
PYTHONPATH=src uv run python -m dm8gen.cli --help
PYTHONPATH=src uv run python -m dm8gen.cli -a validate_index -s ../datam8-sample-solution/ORAYLISDatabricksSample.dm8s
PYTHONPATH=src uv run python -m dm8gen.cli -a generate_template -s ../datam8-sample-solution/ORAYLISDatabricksSample.dm8s -src ../datam8-sample-solution/Generate -dest ../datam8-sample-solution/Output -m ../datam8-sample-solution/Generate/databricks-lake/__modules

# Option 2: Using Python module (TESTED and WORKING):
PYTHONPATH=src python -m dm8gen.cli --help
PYTHONPATH=../datam8-generator/src python -m dm8gen.cli -a validate_index -s ORAYLISDatabricksSample.dm8s

# Generate templates using modules parameter:
cd ../datam8-sample-solution && PYTHONPATH=../datam8-generator/src python -m dm8gen.cli -a generate_template -s ORAYLISDatabricksSample.dm8s -src Generate -dest Output -m Generate/databricks-lake/__modules
```

### Sample Solution Validation

#### Validate All Sample Entities
```bash
# From datam8-generator directory
python -c "
import json, jsonschema, os, glob

# Load schema
with open('datam8-model/schema/ModelDataEntity.json', 'r') as f:
    schema = json.load(f)

resolver = jsonschema.RefResolver(
    base_uri='file://' + os.path.abspath('datam8-model/schema/') + '/',
    referrer=schema
)
validator = jsonschema.Draft7Validator(schema, resolver=resolver)

# Test sample solution entities
sample_dir = '../datam8-sample-solution/Model'
json_files = glob.glob(sample_dir + '/**/*.json', recursive=True)

passed = failed = 0
for json_file in json_files:
    try:
        with open(json_file, 'r') as f:
            entity = json.load(f)
        validator.validate(entity)
        passed += 1
        print(f'✓ {json_file.split(\"/\")[-1]}')
    except Exception as e:
        failed += 1
        print(f'✗ {json_file.split(\"/\")[-1]}: {str(e)[:100]}...')

print(f'Results: {passed} passed, {failed} failed')
"
```

#### Test Sample Solution Generation

**Important: Use Default Output Paths**

The sample solution defines default paths in `ORAYLISDatabricksSample.dm8s`:
- `"generatePath": "Generate"` → Templates are in `Generate/databricks-lake/`
- `"outputPath": "Output"` → Generated files go to `Output/`

```bash
# Change to sample solution directory
cd ../datam8-sample-solution

# Validate sample solution (from sample solution directory)
uv run ../datam8-generator/dm8gen -a validate_index -s ORAYLISDatabricksSample.dm8s

# Alternative without uv:
PYTHONPATH=../datam8-generator/src python -m dm8gen.cli -a validate_index -s ORAYLISDatabricksSample.dm8s

# Generate templates using modules parameter (from datam8-generator directory):
PYTHONPATH=src uv run python -m dm8gen.cli -a generate_template -s ../datam8-sample-solution/ORAYLISDatabricksSample.dm8s -src ../datam8-sample-solution/Generate -dest ../datam8-sample-solution/Output -m ../datam8-sample-solution/Generate/databricks-lake/__modules

# Python module approach (TESTED and WORKING):
PYTHONPATH=../datam8-generator/src python -m dm8gen.cli -a generate_template -s ORAYLISDatabricksSample.dm8s -src Generate -dest Output -m Generate/databricks-lake/__modules

# Check generated output:
ls -la Output/  # Will show generated README.md, databricks.yml, and other files
```

### Template Testing

#### Test Specific Templates
```bash
# Test stage template generation
pytest tests/test_050_generate.py::test_generate_template__stage -v

# Test individual template types
python -c "
from dm8gen.Factory.Jinja2Factory import Jinja2Factory
from dm8gen.Factory.Model import Model

model = Model('/path/to/solution.dm8s')
factory = Jinja2Factory(model, 'INFO')

# Test template generation
factory.generate_template(
    path_template_source='template/pydantic_v2/',
    path_template_destination='Output/test/',
    path_modules=None,
    path_collections=None
)
print('Template generation completed')
"
```

### Debugging & Troubleshooting

#### Common Issues and Solutions

**Schema Validation Errors:**
```bash
# Check schema syntax
python -m json.tool datam8-model/schema/ModelDataEntity.json

# Validate with detailed error messages
python -c "
import json, jsonschema
try:
    with open('datam8-model/schema/ModelDataEntity.json') as f:
        schema = json.load(f)
    jsonschema.Draft7Validator.check_schema(schema)
    print('Schema is valid')
except Exception as e:
    print(f'Schema error: {e}')
"
```

**Reference Resolution Issues:**
```bash
# Check if referenced files exist
ls -la datam8-model/schema/common/

# Test reference resolution manually
python -c "
import json, os
base_path = 'datam8-model/schema/'
refs = ['./common/Parameter.json', './common/AttributeMapping.json', './common/DataModule.json']
for ref in refs:
    file_path = os.path.join(base_path, ref)
    if os.path.exists(file_path):
        print(f'✓ {ref}')
    else:
        print(f'✗ {ref} - NOT FOUND')
"
```

**Template Generation Issues:**
```bash
# Debug with verbose logging
dm8gen -a generate_template -s solution.dm8s -src Generate/ -dest Output/ -ll DEBUG

# Test specific entity processing
python -c "
from dm8gen.Factory.UnifiedEntityFactory import UnifiedEntityFactory
import logging

factory = UnifiedEntityFactory('/path/to/entity.json', logging.DEBUG)
print(f'Entity: {factory.entity_name}')
print(f'Locator: {factory.locator}')
print(f'Layer: {factory.entity_layer}')
"
```

#### Performance Testing
```bash
# Time full generation
time dm8gen -a refresh_generate -s solution.dm8s -src Generate/ -dest Output/

# Memory usage monitoring
python -c "
import psutil, os
from dm8gen.Factory.Model import Model

process = psutil.Process(os.getpid())
print(f'Memory before: {process.memory_info().rss / 1024 / 1024:.2f} MB')

model = Model('/path/to/solution.dm8s')
model.validate_index(full_index_scan=True)

print(f'Memory after: {process.memory_info().rss / 1024 / 1024:.2f} MB')
"
```

### Continuous Integration Testing

#### GitHub Actions / CI Pipeline
```bash
# Install dependencies
pip install -e ".[dev]"

# Run linting
ruff check src/
ruff format --check src/

# Run tests
pytest --junitxml=results.xml

# Validate schemas
python scripts/validate_schemas.py

# Test generation
dm8gen -a validate_index -s tests/sample_solution.dm8s
```

### Quick Validation Checklist

When making changes to DataM8, run these commands to ensure everything works:

```bash
# 1. Schema validation (always works, no dependencies needed)
python -c "import json; json.load(open('datam8-model/schema/ModelDataEntity.json')); print('✓ Schema loads')"

# 2. Schema reference resolution test
python -c "
import json, jsonschema, os
with open('datam8-model/schema/ModelDataEntity.json', 'r') as f:
    schema = json.load(f)
resolver = jsonschema.RefResolver(
    base_uri='file://' + os.path.abspath('datam8-model/schema/') + '/',
    referrer=schema
)
validator = jsonschema.Draft7Validator(schema, resolver=resolver)
print('✓ Schema validation setup successful')
"

# 3. Sample solution validation (works without dependencies)
python -c "
import json, jsonschema, os, glob
with open('datam8-model/schema/ModelDataEntity.json', 'r') as f:
    schema = json.load(f)
resolver = jsonschema.RefResolver(
    base_uri='file://' + os.path.abspath('datam8-model/schema/') + '/',
    referrer=schema
)
validator = jsonschema.Draft7Validator(schema, resolver=resolver)
sample_dir = '../datam8-sample-solution/Model'
json_files = glob.glob(sample_dir + '/**/*.json', recursive=True)
passed = sum(1 for f in json_files if validator.validate(json.load(open(f))) or True)
print(f'✓ {passed} entities validated successfully')
"

# 4. Enhanced parameter validation
python -c "
import json, jsonschema
with open('datam8-model/schema/common/Parameter.json', 'r') as f:
    param_schema = json.load(f)
validator = jsonschema.Draft7Validator(param_schema)
test_cases = [
    {'name': 'test', 'value': 'string'},
    {'name': 'test', 'value': 42},
    {'name': 'test', 'value': True},
    {'name': 'test', 'value': {'key': 'value'}}
]
for case in test_cases:
    validator.validate(case)
print('✓ All parameter types validated')
"

# The following require dependencies (TESTED - pip install pydantic typer jinja2 jsonschema pytest sqlparse autopep8):

# 5. Unit tests (TESTED and WORKING)
DATAM8_SOLUTION_PATH="../datam8-sample-solution" pytest tests/test_010_model.py::test_perform_initial_checks -v

# 6. CLI validation (TESTED and WORKING)  
PYTHONPATH=src python -m dm8gen.cli -a validate_index -s ../datam8-sample-solution/ORAYLISDatabricksSample.dm8s

# 7. Template generation test (FIXED - includes collections parameter for working generation)
cd ../datam8-sample-solution && PYTHONPATH=../datam8-generator/src python -m dm8gen.cli -a generate_template -s ORAYLISDatabricksSample.dm8s -src Generate/databricks-lake/ -c Generate/ -dest Output/
```

This comprehensive testing approach ensures reliability across all DataM8 components and provides confidence when making changes to schemas, generators, or templates.

---

**DataM8 Generator** - Enterprise Data Pipeline Automation
*Developed by ORAYLIS GmbH - Licensed under GPL-3.0*