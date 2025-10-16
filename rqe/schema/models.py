"""
Pydantic models for schema validation.
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Literal, Optional, Dict, Any, List, Union


class VectorFieldAttrs(BaseModel):
    """Attributes for vector fields."""
    algorithm: Literal["flat", "hnsw"]
    dims: int = Field(gt=0, description="Vector dimensions")
    distance_metric: Literal["cosine", "l2", "ip"]
    datatype: Literal["float32", "float64"] = "float32"
    initial_cap: Optional[int] = Field(None, gt=0, description="Initial capacity for HNSW")
    m: Optional[int] = Field(None, gt=0, description="Number of edges per node for HNSW")
    ef_construction: Optional[int] = Field(None, gt=0, description="Number of candidates for HNSW construction")
    ef_runtime: Optional[int] = Field(None, gt=0, description="Number of candidates for HNSW search")


class TagFieldAttrs(BaseModel):
    """Attributes for tag fields."""
    separator: Optional[str] = Field(None, description="Tag separator character")
    casesensitive: Optional[bool] = Field(None, description="Case sensitive matching")


class TextFieldAttrs(BaseModel):
    """Attributes for text fields."""
    weight: Optional[float] = Field(None, gt=0, description="Field weight for scoring")
    nostem: Optional[bool] = Field(None, description="Disable stemming")
    phonetic: Optional[str] = Field(None, description="Phonetic algorithm")
    withsuffixtrie: Optional[bool] = Field(None, description="Enable suffix trie")


class NumericFieldAttrs(BaseModel):
    """Attributes for numeric fields."""
    sortable: Optional[bool] = Field(None, description="Enable sorting on this field")
    noindex: Optional[bool] = Field(None, description="Don't index, only store")


class GeoFieldAttrs(BaseModel):
    """Attributes for geo fields."""
    noindex: Optional[bool] = Field(None, description="Don't index, only store")


class FieldSchema(BaseModel):
    """Schema definition for a single field."""
    name: str = Field(description="Field name")
    type: Literal["tag", "text", "numeric", "vector", "geo"]
    attrs: Optional[Union[VectorFieldAttrs, TagFieldAttrs, TextFieldAttrs, NumericFieldAttrs, GeoFieldAttrs, Dict[str, Any]]] = None
    
    # Data generation configuration
    generator: Optional[str] = Field(None, description="Generator type (e.g., 'random.choice', 'faker.name')")
    generator_args: Optional[Dict[str, Any]] = Field(None, description="Arguments for the generator")
    
    @field_validator('generator_args')
    @classmethod
    def validate_generator_args(cls, v, info):
        """Validate generator arguments based on generator type."""
        if v is None:
            return v
        
        generator = info.data.get('generator')
        if not generator:
            return v
        
        # Validate common boundary parameters
        if 'min' in v and 'max' in v:
            if v['min'] > v['max']:
                raise ValueError(f"min ({v['min']}) must be <= max ({v['max']})")
        
        if 'min_words' in v and 'max_words' in v:
            if v['min_words'] > v['max_words']:
                raise ValueError(f"min_words ({v['min_words']}) must be <= max_words ({v['max_words']})")
        
        if 'min_length' in v and 'max_length' in v:
            if v['min_length'] > v['max_length']:
                raise ValueError(f"min_length ({v['min_length']}) must be <= max_length ({v['max_length']})")
        
        return v
    
    @model_validator(mode='after')
    def validate_field_type_attrs(self):
        """Validate that attrs match the field type."""
        if self.attrs is None:
            return self
        
        # Convert dict to appropriate model if needed
        if isinstance(self.attrs, dict):
            if self.type == "vector":
                self.attrs = VectorFieldAttrs(**self.attrs)
            elif self.type == "tag":
                self.attrs = TagFieldAttrs(**self.attrs)
            elif self.type == "text":
                self.attrs = TextFieldAttrs(**self.attrs)
            elif self.type == "numeric":
                self.attrs = NumericFieldAttrs(**self.attrs)
            elif self.type == "geo":
                self.attrs = GeoFieldAttrs(**self.attrs)
        
        return self


class IndexSchema(BaseModel):
    """Schema definition for the index."""
    name: str = Field(description="Index name")
    prefix: str = Field(description="Key prefix for documents")
    storage_type: Literal["hash", "json"] = Field(default="hash", description="Storage type")
    
    @field_validator('prefix')
    @classmethod
    def validate_prefix(cls, v):
        """Ensure prefix ends with colon."""
        if not v.endswith(':'):
            return f"{v}:"
        return v


class AggregationConfig(BaseModel):
    """Configuration for aggregation on a field."""
    field: str = Field(description="Field name to aggregate")
    enabled: bool = Field(default=True, description="Whether aggregation is enabled")
    limit: Optional[int] = Field(None, gt=0, description="Limit for top-K aggregation")


class BenchmarkSchema(BaseModel):
    """Root schema for benchmark configuration."""
    version: str = Field(description="Schema version")
    index: IndexSchema
    fields: List[FieldSchema] = Field(min_length=1, description="List of field definitions")
    aggregations: Optional[List[AggregationConfig]] = Field(None, description="Aggregation configuration")
    
    @field_validator('version')
    @classmethod
    def validate_version(cls, v):
        """Validate schema version format."""
        parts = v.split('.')
        if len(parts) != 3:
            raise ValueError(f"Version must be in format 'X.Y.Z', got '{v}'")
        
        for part in parts:
            if not part.isdigit():
                raise ValueError(f"Version parts must be numeric, got '{v}'")
        
        return v
    
    @model_validator(mode='after')
    def validate_aggregations(self):
        """Validate that aggregation fields exist in field definitions."""
        if self.aggregations is None:
            return self
        
        field_names = {f.name for f in self.fields}
        
        for agg in self.aggregations:
            if agg.field not in field_names:
                raise ValueError(f"Aggregation field '{agg.field}' not found in field definitions")
            
            # Check that aggregated field is TAG or NUMERIC
            field = next(f for f in self.fields if f.name == agg.field)
            if field.type not in ["tag", "numeric"]:
                raise ValueError(f"Aggregation field '{agg.field}' must be TAG or NUMERIC, got {field.type}")
        
        return self
    
    def get_aggregation_fields(self) -> List[str]:
        """Get list of fields enabled for aggregation."""
        if self.aggregations is None:
            return []
        return [agg.field for agg in self.aggregations if agg.enabled]
    
    def get_field(self, name: str) -> Optional[FieldSchema]:
        """Get field schema by name."""
        for field in self.fields:
            if field.name == name:
                return field
        return None
    
    def validate_against_redis_index(self, index_info) -> tuple[bool, List[str]]:
        """
        Validate schema against actual Redis index info.

        Args:
            index_info: Result from FT.INFO command (dict or list depending on protocol)

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        # Extract attributes from FT.INFO response
        # Protocol 3 returns dict, Protocol 2 returns list
        try:
            if isinstance(index_info, dict):
                # Protocol 3: dict format
                redis_fields = index_info.get('attributes') or index_info.get(b'attributes')
            else:
                # Protocol 2: list format [b'index_name', b'myindex', b'attributes', [...]]
                attrs_idx = index_info.index(b'attributes') if b'attributes' in index_info else index_info.index('attributes')
                redis_fields = index_info[attrs_idx + 1]

            if not redis_fields:
                errors.append("No attributes found in FT.INFO response")
                return False, errors
        except (ValueError, IndexError, KeyError) as e:
            errors.append(f"Could not parse index attributes from FT.INFO response: {e}")
            return False, errors

        # Build map of Redis fields
        redis_field_map = {}
        for field_info in redis_fields:
            # Each field is a dict (protocol 3) or list (protocol 2)
            if isinstance(field_info, dict):
                # Protocol 3: already a dict
                field_dict = {
                    k.decode() if isinstance(k, bytes) else k:
                    v.decode() if isinstance(v, bytes) else v
                    for k, v in field_info.items()
                }
            else:
                # Protocol 2: list like [b'identifier', b'country', b'attribute', b'country', b'type', b'TAG', ...]
                field_dict = {}
                for i in range(0, len(field_info), 2):
                    key = field_info[i].decode() if isinstance(field_info[i], bytes) else field_info[i]
                    value = field_info[i + 1].decode() if isinstance(field_info[i + 1], bytes) else field_info[i + 1]
                    field_dict[key] = value

            field_name = field_dict.get('attribute', field_dict.get('identifier'))
            redis_field_map[field_name] = field_dict

        # Validate each schema field exists in Redis
        for field in self.fields:
            if field.name not in redis_field_map:
                errors.append(f"Field '{field.name}' defined in schema but not found in Redis index")
                continue

            redis_field = redis_field_map[field.name]
            redis_type = redis_field.get('type', '').upper()
            schema_type = field.type.upper()

            if redis_type != schema_type:
                errors.append(f"Field '{field.name}' type mismatch: schema={schema_type}, redis={redis_type}")

        # Check for extra fields in Redis not in schema
        schema_field_names = {f.name for f in self.fields}
        for redis_field_name in redis_field_map.keys():
            if redis_field_name not in schema_field_names:
                errors.append(f"Field '{redis_field_name}' exists in Redis index but not in schema")

        return len(errors) == 0, errors

