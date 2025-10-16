"""
YAML schema loader with validation.
"""

import yaml
from pathlib import Path
from typing import Union
from pydantic import ValidationError
from .models import BenchmarkSchema


class SchemaLoadError(Exception):
    """Exception raised when schema loading fails."""
    pass


def load_schema(path: Union[str, Path]) -> BenchmarkSchema:
    """
    Load and validate a benchmark schema from a YAML file.
    
    Args:
        path: Path to the YAML schema file
        
    Returns:
        Validated BenchmarkSchema object
        
    Raises:
        SchemaLoadError: If file cannot be read or schema is invalid
    """
    path = Path(path)
    
    # Check file exists
    if not path.exists():
        raise SchemaLoadError(f"Schema file not found: {path}")
    
    # Check file extension
    if path.suffix not in ['.yaml', '.yml']:
        raise SchemaLoadError(f"Schema file must be .yaml or .yml, got: {path.suffix}")
    
    # Read YAML file
    try:
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise SchemaLoadError(f"Failed to parse YAML: {e}")
    except Exception as e:
        raise SchemaLoadError(f"Failed to read file: {e}")
    
    # Validate with Pydantic
    try:
        schema = BenchmarkSchema(**data)
    except ValidationError as e:
        # Format validation errors nicely
        errors = []
        for error in e.errors():
            loc = " -> ".join(str(x) for x in error['loc'])
            msg = error['msg']
            errors.append(f"  • {loc}: {msg}")
        
        error_msg = "Schema validation failed:\n" + "\n".join(errors)
        raise SchemaLoadError(error_msg)
    
    return schema


def save_schema(schema: BenchmarkSchema, path: Union[str, Path]) -> None:
    """
    Save a benchmark schema to a YAML file.
    
    Args:
        schema: BenchmarkSchema object to save
        path: Path to save the YAML file
        
    Raises:
        SchemaLoadError: If file cannot be written
    """
    path = Path(path)
    
    # Ensure directory exists
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert to dict and save
    try:
        data = schema.model_dump(exclude_none=True)
        with open(path, 'w') as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
    except Exception as e:
        raise SchemaLoadError(f"Failed to save schema: {e}")


def validate_schema_file(path: Union[str, Path]) -> tuple[bool, Union[BenchmarkSchema, str]]:
    """
    Validate a schema file and return result.
    
    Args:
        path: Path to the YAML schema file
        
    Returns:
        Tuple of (is_valid, schema_or_error_message)
    """
    try:
        schema = load_schema(path)
        return True, schema
    except SchemaLoadError as e:
        return False, str(e)

