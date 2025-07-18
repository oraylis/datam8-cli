# DataM8 Generator - Comprehensive Documentation

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Data Model](#data-model)
4. [Code Generation](#code-generation)
5. [Usage Guide](#usage-guide)
6. [Development](#development)
7. [Reference](#reference)

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

#### 1. Factory Pattern
Each entity type has specialized processing:
- **RawEntityFactory**: Source data ingestion
- **StageEntityFactory**: Data cleansing and standardization
- **CoreEntityFactory**: Business logic and relationships
- **CuratedEntityFactory**: Analytics and aggregation

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

# Entity factories
from dm8gen.Factory.CoreEntityFactory import CoreEntityFactory
factory = CoreEntityFactory(model)

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

**DataM8 Generator** - Enterprise Data Pipeline Automation
*Developed by ORAYLIS GmbH - Licensed under GPL-3.0*