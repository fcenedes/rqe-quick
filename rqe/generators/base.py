"""
Base generator interface for field value generation.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional
import random


class FieldGenerator(ABC):
    """
    Abstract base class for field value generators.
    
    All generators should:
    1. Accept a seed for reproducibility
    2. Implement the generate() method
    3. Respect boundary constraints (min/max, length, etc.)
    """
    
    def __init__(self, seed: int = 42, **kwargs):
        """
        Initialize the generator.
        
        Args:
            seed: Random seed for reproducibility
            **kwargs: Additional generator-specific arguments
        """
        self.seed = seed
        self.rnd = random.Random(seed)
        self.kwargs = kwargs
    
    @abstractmethod
    def generate(self) -> Any:
        """
        Generate a single value.
        
        Returns:
            Generated value (type depends on field type)
        """
        pass
    
    def enforce_numeric_bounds(self, value: float, min_val: Optional[float] = None, max_val: Optional[float] = None) -> float:
        """
        Enforce min/max bounds on a numeric value.
        
        Args:
            value: The value to constrain
            min_val: Minimum allowed value
            max_val: Maximum allowed value
            
        Returns:
            Constrained value
        """
        if min_val is not None:
            value = max(value, min_val)
        if max_val is not None:
            value = min(value, max_val)
        return value
    
    def enforce_length_bounds(self, text: str, min_length: Optional[int] = None, max_length: Optional[int] = None) -> str:
        """
        Enforce min/max length bounds on a string.
        
        Args:
            text: The text to constrain
            min_length: Minimum allowed length
            max_length: Maximum allowed length
            
        Returns:
            Constrained text
        """
        if max_length is not None and len(text) > max_length:
            text = text[:max_length]
        
        if min_length is not None and len(text) < min_length:
            # Pad with spaces or repeat text
            while len(text) < min_length:
                text += " " + text
            text = text[:min_length]
        
        return text
    
    def enforce_word_count(self, text: str, min_words: Optional[int] = None, max_words: Optional[int] = None) -> str:
        """
        Enforce min/max word count on a string.
        
        Args:
            text: The text to constrain
            min_words: Minimum number of words
            max_words: Maximum number of words
            
        Returns:
            Constrained text
        """
        words = text.split()
        
        if max_words is not None and len(words) > max_words:
            words = words[:max_words]
        
        if min_words is not None and len(words) < min_words:
            # Repeat words to reach minimum
            while len(words) < min_words:
                words.extend(words[:min(len(words), min_words - len(words))])
        
        return ' '.join(words)


class GeneratorError(Exception):
    """Exception raised when generator creation or execution fails."""
    pass

