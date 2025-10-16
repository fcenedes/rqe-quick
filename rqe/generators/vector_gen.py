"""
Vector/embedding generators for vector fields.
"""

from typing import List, Optional
import struct
from .base import FieldGenerator, GeneratorError


class VectorGenerator(FieldGenerator):
    """Base class for vector generators."""
    
    def __init__(self, seed: int = 42, dims: int = 128, **kwargs):
        super().__init__(seed, **kwargs)
        if dims <= 0:
            raise GeneratorError(f"dims must be positive, got {dims}")
        self.dims = dims


class RandomNormalizedVectorGenerator(VectorGenerator):
    """
    Generate random normalized vectors (L2 norm = 1).
    Useful for cosine similarity searches.
    """
    
    def generate(self) -> List[float]:
        """Generate a random normalized vector."""
        # Generate random values
        vector = [self.rnd.gauss(0, 1) for _ in range(self.dims)]
        
        # Calculate L2 norm
        norm = sum(x * x for x in vector) ** 0.5
        
        # Normalize
        if norm > 0:
            vector = [x / norm for x in vector]
        
        return vector


class RandomVectorGenerator(VectorGenerator):
    """
    Generate random vectors (not normalized).
    Values are uniformly distributed in a range.
    """
    
    def __init__(self, seed: int = 42, dims: int = 128, min_val: float = -1.0, max_val: float = 1.0, **kwargs):
        super().__init__(seed, dims, **kwargs)
        self.min_val = min_val
        self.max_val = max_val
    
    def generate(self) -> List[float]:
        """Generate a random vector with values in [min_val, max_val]."""
        return [self.rnd.uniform(self.min_val, self.max_val) for _ in range(self.dims)]


class GaussianVectorGenerator(VectorGenerator):
    """
    Generate random vectors with Gaussian distribution.
    Each dimension is independently sampled from N(mu, sigma).
    """
    
    def __init__(self, seed: int = 42, dims: int = 128, mu: float = 0.0, sigma: float = 1.0, **kwargs):
        super().__init__(seed, dims, **kwargs)
        self.mu = mu
        self.sigma = sigma
    
    def generate(self) -> List[float]:
        """Generate a random Gaussian vector."""
        return [self.rnd.gauss(self.mu, self.sigma) for _ in range(self.dims)]


class ZeroVectorGenerator(VectorGenerator):
    """Generate zero vectors (all zeros)."""
    
    def generate(self) -> List[float]:
        """Generate a zero vector."""
        return [0.0] * self.dims


class OneHotVectorGenerator(VectorGenerator):
    """
    Generate one-hot vectors (single 1, rest 0s).
    The position of the 1 is randomly chosen.
    """
    
    def generate(self) -> List[float]:
        """Generate a one-hot vector."""
        vector = [0.0] * self.dims
        hot_index = self.rnd.randint(0, self.dims - 1)
        vector[hot_index] = 1.0
        return vector


class BinaryVectorGenerator(VectorGenerator):
    """
    Generate binary vectors (values are 0 or 1).
    Useful for binary embeddings.
    """
    
    def __init__(self, seed: int = 42, dims: int = 128, probability: float = 0.5, **kwargs):
        super().__init__(seed, dims, **kwargs)
        if not 0 <= probability <= 1:
            raise GeneratorError(f"probability must be between 0 and 1, got {probability}")
        self.probability = probability
    
    def generate(self) -> List[float]:
        """Generate a binary vector."""
        return [1.0 if self.rnd.random() < self.probability else 0.0 for _ in range(self.dims)]


def vector_to_bytes(vector: List[float], datatype: str = 'float32') -> bytes:
    """
    Convert a vector to bytes for Redis storage.
    
    Args:
        vector: List of floats
        datatype: 'float32' or 'float64'
        
    Returns:
        Bytes representation of the vector
    """
    if datatype == 'float32':
        return struct.pack(f'{len(vector)}f', *vector)
    elif datatype == 'float64':
        return struct.pack(f'{len(vector)}d', *vector)
    else:
        raise ValueError(f"Unsupported datatype: {datatype}")


def bytes_to_vector(data: bytes, datatype: str = 'float32') -> List[float]:
    """
    Convert bytes back to a vector.
    
    Args:
        data: Bytes representation
        datatype: 'float32' or 'float64'
        
    Returns:
        List of floats
    """
    if datatype == 'float32':
        size = len(data) // 4
        return list(struct.unpack(f'{size}f', data))
    elif datatype == 'float64':
        size = len(data) // 8
        return list(struct.unpack(f'{size}d', data))
    else:
        raise ValueError(f"Unsupported datatype: {datatype}")

