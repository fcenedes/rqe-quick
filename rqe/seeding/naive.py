"""
Naive (sequential) seeding implementation.
"""

import random
from time import time


def seed_dummy_hash_docs_naive(
    r,
    *,
    prefix: str,
    n_docs: int = 200_000,
    chunk: int = 2_000,
    seed: int = 42
):
    """
    Insert n_docs HASH docs under the given prefix, pipelined in chunks for speed.
    
    This is the baseline sequential implementation.
    
    Fields:
      - country (TAG)
      - category (TAG)
      - status (TAG)
      - price (NUMERIC)
      - ts (NUMERIC epoch seconds)
      
    Args:
        r: Redis client
        prefix: Key prefix for documents
        n_docs: Number of documents to create
        chunk: Pipeline batch size
        seed: Random seed for reproducibility
    """
    rnd = random.Random(seed)
    countries = ["US", "FR", "DE", "IN", "BR", "CN", "GB", "ES", "IT", "JP"]
    categories = ["electronics", "books", "toys", "clothing", "grocery", "beauty", "sports"]
    statuses = ["pending", "paid", "shipped", "delivered", "returned", "cancelled"]

    now = int(time())
    day = 86400

    pipe = r.pipeline(transaction=False)
    written = 0
    for i in range(n_docs):
        key = f"{prefix}{i}"
        country = rnd.choice(countries)
        category = rnd.choice(categories)
        status = rnd.choices(statuses, weights=[4, 10, 15, 25, 3, 2], k=1)[0]

        # mildly skewed price & recency
        price = max(1, int(abs(rnd.gauss(60, 25)) * (1 + 0.2 * (category == "electronics"))))
        ts = now - rnd.randint(0, 30 * day)

        pipe.hset(key, mapping={
            "country": country,
            "category": category,
            "status": status,
            "price": price,
            "ts": ts
        })
        written += 1
        if written % chunk == 0:
            pipe.execute()
    if written % chunk:
        pipe.execute()

