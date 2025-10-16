"""
Faker-based generators for realistic data.
"""

from typing import Optional, Any
from faker import Faker
from .base import FieldGenerator, GeneratorError


class FakerGenerator(FieldGenerator):
    """
    Generic Faker generator that calls any Faker method.
    
    Examples:
        - method='name' -> faker.name()
        - method='email' -> faker.email()
        - method='sentence' with nb_words=10 -> faker.sentence(nb_words=10)
    """
    
    def __init__(self, seed: int = 42, method: Optional[str] = None, 
                 min_length: Optional[int] = None, max_length: Optional[int] = None,
                 min_words: Optional[int] = None, max_words: Optional[int] = None,
                 **kwargs):
        super().__init__(seed, **kwargs)
        
        if not method:
            raise GeneratorError("FakerGenerator requires 'method' parameter")
        
        self.faker = Faker()
        Faker.seed(seed)
        
        self.method = method
        self.min_length = min_length
        self.max_length = max_length
        self.min_words = min_words
        self.max_words = max_words
        
        # Validate method exists
        if not hasattr(self.faker, method):
            raise GeneratorError(f"Faker has no method '{method}'")
        
        self.faker_method = getattr(self.faker, method)
    
    def generate(self) -> Any:
        """Generate value using Faker method."""
        # Call Faker method with any remaining kwargs
        faker_kwargs = {}
        
        # Handle special parameters for text generation
        if self.method in ['sentence', 'sentences', 'paragraph', 'paragraphs', 'text']:
            if self.min_words is not None or self.max_words is not None:
                # Use average of min/max for nb_words
                if self.min_words and self.max_words:
                    nb_words = (self.min_words + self.max_words) // 2
                elif self.max_words:
                    nb_words = self.max_words
                else:
                    nb_words = self.min_words
                
                if self.method == 'sentence':
                    faker_kwargs['nb_words'] = nb_words
                elif self.method == 'text':
                    faker_kwargs['max_nb_chars'] = nb_words * 6  # Approximate
        
        # Add any other kwargs that were passed
        for key, value in self.kwargs.items():
            if key not in ['method', 'min_length', 'max_length', 'min_words', 'max_words']:
                faker_kwargs[key] = value
        
        # Generate value
        value = self.faker_method(**faker_kwargs) if faker_kwargs else self.faker_method()
        
        # Convert to string if needed for boundary enforcement
        if isinstance(value, str):
            # Apply word count boundaries
            if self.min_words is not None or self.max_words is not None:
                value = self.enforce_word_count(value, self.min_words, self.max_words)
            
            # Apply length boundaries
            if self.min_length is not None or self.max_length is not None:
                value = self.enforce_length_bounds(value, self.min_length, self.max_length)
        
        return value


class NameGenerator(FakerGenerator):
    """Generate random person names."""
    
    def __init__(self, seed: int = 42, **kwargs):
        super().__init__(seed, method='name', **kwargs)


class EmailGenerator(FakerGenerator):
    """Generate random email addresses."""
    
    def __init__(self, seed: int = 42, **kwargs):
        super().__init__(seed, method='email', **kwargs)


class UserNameGenerator(FakerGenerator):
    """Generate random usernames."""
    
    def __init__(self, seed: int = 42, **kwargs):
        super().__init__(seed, method='user_name', **kwargs)


class CompanyGenerator(FakerGenerator):
    """Generate random company names."""
    
    def __init__(self, seed: int = 42, **kwargs):
        super().__init__(seed, method='company', **kwargs)


class AddressGenerator(FakerGenerator):
    """Generate random addresses."""
    
    def __init__(self, seed: int = 42, **kwargs):
        super().__init__(seed, method='address', **kwargs)


class CityGenerator(FakerGenerator):
    """Generate random city names."""
    
    def __init__(self, seed: int = 42, **kwargs):
        super().__init__(seed, method='city', **kwargs)


class CountryGenerator(FakerGenerator):
    """Generate random country names."""
    
    def __init__(self, seed: int = 42, **kwargs):
        super().__init__(seed, method='country', **kwargs)


class CountryCodeGenerator(FakerGenerator):
    """Generate random country codes (ISO 3166-1 alpha-2)."""
    
    def __init__(self, seed: int = 42, **kwargs):
        super().__init__(seed, method='country_code', **kwargs)


class PhoneNumberGenerator(FakerGenerator):
    """Generate random phone numbers."""
    
    def __init__(self, seed: int = 42, **kwargs):
        super().__init__(seed, method='phone_number', **kwargs)


class SentenceGenerator(FakerGenerator):
    """Generate random sentences."""
    
    def __init__(self, seed: int = 42, min_words: Optional[int] = None, max_words: Optional[int] = None, **kwargs):
        super().__init__(seed, method='sentence', min_words=min_words, max_words=max_words, **kwargs)


class ParagraphGenerator(FakerGenerator):
    """Generate random paragraphs."""
    
    def __init__(self, seed: int = 42, min_words: Optional[int] = None, max_words: Optional[int] = None, **kwargs):
        super().__init__(seed, method='paragraph', min_words=min_words, max_words=max_words, **kwargs)


class TextGenerator(FakerGenerator):
    """Generate random text."""
    
    def __init__(self, seed: int = 42, max_length: Optional[int] = None, **kwargs):
        super().__init__(seed, method='text', max_length=max_length, **kwargs)


class URLGenerator(FakerGenerator):
    """Generate random URLs."""
    
    def __init__(self, seed: int = 42, **kwargs):
        super().__init__(seed, method='url', **kwargs)


class IPv4Generator(FakerGenerator):
    """Generate random IPv4 addresses."""
    
    def __init__(self, seed: int = 42, **kwargs):
        super().__init__(seed, method='ipv4', **kwargs)


class DateGenerator(FakerGenerator):
    """Generate random dates."""
    
    def __init__(self, seed: int = 42, **kwargs):
        super().__init__(seed, method='date', **kwargs)


class DateTimeGenerator(FakerGenerator):
    """Generate random datetimes."""
    
    def __init__(self, seed: int = 42, **kwargs):
        super().__init__(seed, method='date_time', **kwargs)

