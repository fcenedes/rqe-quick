"""
Random-based generators for field values.
"""

from typing import List, Optional, Any
from time import time
from .base import FieldGenerator, GeneratorError


class ChoiceGenerator(FieldGenerator):
    """Generate random choice from a list of options."""
    
    def __init__(self, seed: int = 42, choices: Optional[List[Any]] = None, **kwargs):
        super().__init__(seed, **kwargs)
        if not choices:
            raise GeneratorError("ChoiceGenerator requires 'choices' parameter")
        self.choices = choices
    
    def generate(self) -> Any:
        return self.rnd.choice(self.choices)


class WeightedChoiceGenerator(FieldGenerator):
    """Generate weighted random choice from a list of options."""
    
    def __init__(self, seed: int = 42, choices: Optional[List[Any]] = None, weights: Optional[List[float]] = None, **kwargs):
        super().__init__(seed, **kwargs)
        if not choices:
            raise GeneratorError("WeightedChoiceGenerator requires 'choices' parameter")
        if not weights:
            raise GeneratorError("WeightedChoiceGenerator requires 'weights' parameter")
        if len(choices) != len(weights):
            raise GeneratorError(f"Length of choices ({len(choices)}) must match weights ({len(weights)})")
        
        self.choices = choices
        self.weights = weights
    
    def generate(self) -> Any:
        return self.rnd.choices(self.choices, weights=self.weights, k=1)[0]


class RandIntGenerator(FieldGenerator):
    """Generate random integer in a range."""
    
    def __init__(self, seed: int = 42, min: int = 0, max: int = 100, **kwargs):
        super().__init__(seed, **kwargs)
        if min > max:
            raise GeneratorError(f"min ({min}) must be <= max ({max})")
        self.min = min
        self.max = max
    
    def generate(self) -> int:
        return self.rnd.randint(self.min, self.max)


class RandFloatGenerator(FieldGenerator):
    """Generate random float in a range."""
    
    def __init__(self, seed: int = 42, min: float = 0.0, max: float = 1.0, **kwargs):
        super().__init__(seed, **kwargs)
        if min > max:
            raise GeneratorError(f"min ({min}) must be <= max ({max})")
        self.min = min
        self.max = max
    
    def generate(self) -> float:
        return self.rnd.uniform(self.min, self.max)


class GaussianGenerator(FieldGenerator):
    """Generate random value from Gaussian (normal) distribution."""
    
    def __init__(self, seed: int = 42, mu: float = 0.0, sigma: float = 1.0, 
                 min: Optional[float] = None, max: Optional[float] = None, **kwargs):
        super().__init__(seed, **kwargs)
        self.mu = mu
        self.sigma = sigma
        self.min = min
        self.max = max
    
    def generate(self) -> float:
        value = self.rnd.gauss(self.mu, self.sigma)
        return self.enforce_numeric_bounds(value, self.min, self.max)


class TimestampGenerator(FieldGenerator):
    """Generate random timestamp within a time range."""
    
    def __init__(self, seed: int = 42, days_ago: int = 30, days_future: int = 0, **kwargs):
        super().__init__(seed, **kwargs)
        self.days_ago = days_ago
        self.days_future = days_future
        
        # Calculate time range in seconds
        now = time()
        self.min_time = now - (days_ago * 86400)  # 86400 seconds per day
        self.max_time = now + (days_future * 86400)
    
    def generate(self) -> int:
        """Generate random timestamp as integer (epoch seconds)."""
        return int(self.rnd.uniform(self.min_time, self.max_time))


class BoolGenerator(FieldGenerator):
    """Generate random boolean value."""
    
    def __init__(self, seed: int = 42, probability: float = 0.5, **kwargs):
        super().__init__(seed, **kwargs)
        if not 0 <= probability <= 1:
            raise GeneratorError(f"probability must be between 0 and 1, got {probability}")
        self.probability = probability
    
    def generate(self) -> bool:
        return self.rnd.random() < self.probability


class UUIDGenerator(FieldGenerator):
    """Generate random UUID-like strings."""
    
    def __init__(self, seed: int = 42, **kwargs):
        super().__init__(seed, **kwargs)
    
    def generate(self) -> str:
        """Generate a UUID-like string (not cryptographically secure)."""
        import uuid
        # Use random bytes from our seeded RNG
        random_bytes = bytes([self.rnd.randint(0, 255) for _ in range(16)])
        return str(uuid.UUID(bytes=random_bytes))


class IncrementalGenerator(FieldGenerator):
    """Generate incremental integer values."""
    
    def __init__(self, seed: int = 42, start: int = 1, step: int = 1, **kwargs):
        super().__init__(seed, **kwargs)
        self.current = start
        self.step = step
    
    def generate(self) -> int:
        value = self.current
        self.current += self.step
        return value


class ConstantGenerator(FieldGenerator):
    """Generate constant value."""
    
    def __init__(self, seed: int = 42, value: Any = None, **kwargs):
        super().__init__(seed, **kwargs)
        if value is None:
            raise GeneratorError("ConstantGenerator requires 'value' parameter")
        self.value = value
    
    def generate(self) -> Any:
        return self.value

