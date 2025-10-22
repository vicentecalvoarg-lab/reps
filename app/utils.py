"""General small utilities used across modules."""
import re
import hashlib

def format_number(x):
    try:
        return f"{int(x):,}"
    except Exception:
        try:
            return f"{float(x):,.0f}"
        except Exception:
            return x

def normalize_nit(val):
    if val is None:
        return ""
    return re.sub(r'\D', '', str(val))

def hash_seed(*args) -> int:
    key = "|".join([str(a) for a in args])
    h = hashlib.md5(key.encode("utf-8")).hexdigest()
    return int(h[:8], 16)
