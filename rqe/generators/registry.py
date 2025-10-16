"""
Generator registry and factory for creating generators from schema.
"""

from typing import Dict, Type, Optional
from ..schema.models import FieldSchema
from .base import FieldGenerator, GeneratorError
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
from .vector_gen import (
    RandomNormalizedVectorGenerator,
    RandomVectorGenerator,
    GaussianVectorGenerator,
    ZeroVectorGenerator,
    OneHotVectorGenerator,
    BinaryVectorGenerator,
)


class GeneratorRegistry:
    """
    Registry for field generators.
    Maps generator names to generator classes.
    """
    
    def __init__(self):
        self._registry: Dict[str, Type[FieldGenerator]] = {}
        self._register_defaults()
    
    def _register_defaults(self):
        """Register all built-in generators."""
        
        # Random generators
        self.register('random.choice', ChoiceGenerator)
        self.register('random.weighted_choice', WeightedChoiceGenerator)
        self.register('random.randint', RandIntGenerator)
        self.register('random.randfloat', RandFloatGenerator)
        self.register('random.gauss', GaussianGenerator)
        self.register('random.timestamp', TimestampGenerator)
        self.register('random.bool', BoolGenerator)
        self.register('random.uuid', UUIDGenerator)
        self.register('random.incremental', IncrementalGenerator)
        self.register('random.constant', ConstantGenerator)
        
        # Faker generators - specific
        self.register('faker.name', NameGenerator)
        self.register('faker.email', EmailGenerator)
        self.register('faker.user_name', UserNameGenerator)
        self.register('faker.company', CompanyGenerator)
        self.register('faker.address', AddressGenerator)
        self.register('faker.city', CityGenerator)
        self.register('faker.country', CountryGenerator)
        self.register('faker.country_code', CountryCodeGenerator)
        self.register('faker.phone_number', PhoneNumberGenerator)
        self.register('faker.sentence', SentenceGenerator)
        self.register('faker.paragraph', ParagraphGenerator)
        self.register('faker.text', TextGenerator)
        self.register('faker.url', URLGenerator)
        self.register('faker.ipv4', IPv4Generator)
        self.register('faker.date', DateGenerator)
        self.register('faker.date_time', DateTimeGenerator)
        
        # Vector generators
        self.register('vector.random_normalized', RandomNormalizedVectorGenerator)
        self.register('vector.random', RandomVectorGenerator)
        self.register('vector.gaussian', GaussianVectorGenerator)
        self.register('vector.zero', ZeroVectorGenerator)
        self.register('vector.onehot', OneHotVectorGenerator)
        self.register('vector.binary', BinaryVectorGenerator)
    
    def register(self, name: str, generator_class: Type[FieldGenerator]):
        """
        Register a generator class.
        
        Args:
            name: Generator name (e.g., 'random.choice', 'faker.name')
            generator_class: Generator class
        """
        self._registry[name] = generator_class
    
    def get(self, name: str) -> Optional[Type[FieldGenerator]]:
        """
        Get a generator class by name.
        
        Args:
            name: Generator name
            
        Returns:
            Generator class or None if not found
        """
        # Check exact match first
        if name in self._registry:
            return self._registry[name]
        
        # Check if it's a generic faker method
        if name.startswith('faker.'):
            method = name.replace('faker.', '')
            # Return FakerGenerator with the method pre-configured
            return lambda seed=42, **kwargs: FakerGenerator(seed=seed, method=method, **kwargs)
        
        return None
    
    def create_generator(self, field_schema: FieldSchema, seed: int = 42) -> FieldGenerator:
        """
        Create a generator from a field schema.
        
        Args:
            field_schema: Field schema definition
            seed: Random seed for reproducibility
            
        Returns:
            Configured generator instance
            
        Raises:
            GeneratorError: If generator cannot be created
        """
        # If no generator specified, use defaults based on field type
        if not field_schema.generator:
            return self._create_default_generator(field_schema, seed)
        
        # Get generator class
        generator_class = self.get(field_schema.generator)
        if not generator_class:
            raise GeneratorError(f"Unknown generator: {field_schema.generator}")
        
        # Prepare kwargs
        kwargs = field_schema.generator_args or {}
        
        # Add vector dimensions if it's a vector field
        if field_schema.type == 'vector' and field_schema.attrs:
            if hasattr(field_schema.attrs, 'dims'):
                kwargs['dims'] = field_schema.attrs.dims
        
        # Create generator instance
        try:
            return generator_class(seed=seed, **kwargs)
        except Exception as e:
            raise GeneratorError(f"Failed to create generator '{field_schema.generator}': {e}")
    
    def _create_default_generator(self, field_schema: FieldSchema, seed: int = 42) -> FieldGenerator:
        """
        Create a default generator based on field type.
        
        Args:
            field_schema: Field schema definition
            seed: Random seed
            
        Returns:
            Default generator for the field type
        """
        if field_schema.type == 'tag':
            # Default: random choice from a small set
            return ChoiceGenerator(seed=seed, choices=['A', 'B', 'C', 'D', 'E'])
        
        elif field_schema.type == 'text':
            # Default: random sentence
            return SentenceGenerator(seed=seed, min_words=5, max_words=15)
        
        elif field_schema.type == 'numeric':
            # Default: random integer 0-100
            return RandIntGenerator(seed=seed, min=0, max=100)
        
        elif field_schema.type == 'vector':
            # Default: random normalized vector
            dims = 128
            if field_schema.attrs and hasattr(field_schema.attrs, 'dims'):
                dims = field_schema.attrs.dims
            return RandomNormalizedVectorGenerator(seed=seed, dims=dims)
        
        elif field_schema.type == 'geo':
            # Default: random lat,lon
            # GEO fields in Redis are stored as "lon,lat" strings
            return FakerGenerator(seed=seed, method='local_latlng')
        
        else:
            raise GeneratorError(f"No default generator for field type: {field_schema.type}")


# Global registry instance
_default_registry = GeneratorRegistry()


def get_default_registry() -> GeneratorRegistry:
    """Get the default global registry."""
    return _default_registry


def create_generator(field_schema: FieldSchema, seed: int = 42) -> FieldGenerator:
    """
    Convenience function to create a generator from a field schema.
    Uses the default global registry.
    
    Args:
        field_schema: Field schema definition
        seed: Random seed for reproducibility
        
    Returns:
        Configured generator instance
    """
    return _default_registry.create_generator(field_schema, seed)

