import hashlib


def hash_function(string: str) -> str:
    # "surrogatepass": a lone surrogate, such as a label cut inside an emoji, which a
    # file can hold, can't make this raise. Any other text gives the same bytes as
    # plain UTF-8, so no digest changes.
    return hashlib.md5(string.encode("utf-8", "surrogatepass")).hexdigest()
