"""
Data generators for schema-driven benchmarking.
"""

from .base import FieldGenerator, GeneratorError
from .registry import GeneratorRegistry, get_default_registry, create_generator

# Random generators
from .random_gen import (
    ChoiceGenerator,
    WeightedChoiceGenerator,
    RandIntGenerator,
    RandFloatGenerator,
    GaussianGenerator,
    TimestampGenerator,
    BoolGenerator,
    UUIDGenerator,
    IncrementalGenerator,
    ConstantGenerator,
)

# Faker generators
from .faker_gen import (
    FakerGenerator,
    NameGenerator,
    EmailGenerator,
    UserNameGenerator,
    CompanyGenerator,
    AddressGenerator,
    CityGenerator,
    CountryGenerator,
    CountryCodeGenerator,
    PhoneNumberGenerator,
    SentenceGenerator,
    ParagraphGenerator,
    TextGenerator,
    URLGenerator,
    IPv4Generator,
    DateGenerator,
    DateTimeGenerator,
)

# Vector generators
from .vector_gen import (
    VectorGenerator,
    RandomNormalizedVectorGenerator,
    RandomVectorGenerator,
    GaussianVectorGenerator,
    ZeroVectorGenerator,
    OneHotVectorGenerator,
    BinaryVectorGenerator,
    vector_to_bytes,
    bytes_to_vector,
)

__all__ = [
    # Base
    'FieldGenerator',
    'GeneratorError',
    
    # Registry
    'GeneratorRegistry',
    'get_default_registry',
    'create_generator',
    
    # Random generators
    'ChoiceGenerator',
    'WeightedChoiceGenerator',
    'RandIntGenerator',
    'RandFloatGenerator',
    'GaussianGenerator',
    'TimestampGenerator',
    'BoolGenerator',
    'UUIDGenerator',
    'IncrementalGenerator',
    'ConstantGenerator',
    
    # Faker generators
    'FakerGenerator',
    'NameGenerator',
    'EmailGenerator',
    'UserNameGenerator',
    'CompanyGenerator',
    'AddressGenerator',
    'CityGenerator',
    'CountryGenerator',
    'CountryCodeGenerator',
    'PhoneNumberGenerator',
    'SentenceGenerator',
    'ParagraphGenerator',
    'TextGenerator',
    'URLGenerator',
    'IPv4Generator',
    'DateGenerator',
    'DateTimeGenerator',
    
    # Vector generators
    'VectorGenerator',
    'RandomNormalizedVectorGenerator',
    'RandomVectorGenerator',
    'GaussianVectorGenerator',
    'ZeroVectorGenerator',
    'OneHotVectorGenerator',
    'BinaryVectorGenerator',
    'vector_to_bytes',
    'bytes_to_vector',
]

