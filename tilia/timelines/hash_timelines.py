import hashlib


def hash_function(string: str) -> str:
    return hashlib.md5(string.encode("utf-8")).hexdigest()
