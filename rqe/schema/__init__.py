"""
Schema module for benchmark configuration.
"""

from .models import (
    BenchmarkSchema,
    IndexSchema,
    FieldSchema,
    AggregationConfig,
    VectorFieldAttrs,
    TagFieldAttrs,
    TextFieldAttrs,
    NumericFieldAttrs,
    GeoFieldAttrs,
)
from .loader import load_schema, save_schema, validate_schema_file, SchemaLoadError

__all__ = [
    'BenchmarkSchema',
    'IndexSchema',
    'FieldSchema',
    'AggregationConfig',
    'VectorFieldAttrs',
    'TagFieldAttrs',
    'TextFieldAttrs',
    'NumericFieldAttrs',
    'GeoFieldAttrs',
    'load_schema',
    'save_schema',
    'validate_schema_file',
    'SchemaLoadError',
]

