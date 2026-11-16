"""Versioned design-number equivalence; never use for immutable audit/file hashes.

Only integral floats inside JSON's interoperable safe-integer range are collapsed.
No tolerance, decimal rounding, bool coercion, key dropping or array reordering.
This deliberately is not RFC8785/JCS and makes no large-number equivalence claim.
"""
from __future__ import annotations
import hashlib
import json
import math

POLICY = 'safe-json-number-v1'
MAX_SAFE_INTEGER = 2**53-1


def normalized(value):
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError('Design JSON must contain finite numbers.')
        if abs(value) <= MAX_SAFE_INTEGER and value.is_integer():
            return int(value)
        return value
    if isinstance(value, list):
        return [normalized(item) for item in value]
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError('Design JSON keys must be strings.')
        return {key: normalized(item) for key, item in value.items()}
    if value is None or isinstance(value, (bool, int, str)):
        return value
    raise ValueError('Use ordinary JSON values for the design.')


def encoded(value):
    return json.dumps(normalized(value), sort_keys=True, allow_nan=False).encode()


def fingerprint(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def legacy_fingerprint(value):
    """Existing native source identity, retained for exact legacy compatibility."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def equal(left, right):
    return encoded(left) == encoded(right)


def fields(spec):
    return {'semantic_fingerprint': fingerprint(spec), 'semantic_fingerprint_policy': POLICY}


def matches(metadata, spec):
    if metadata.get('semantic_fingerprint_policy') == POLICY:
        return metadata.get('semantic_fingerprint') == fingerprint(spec)
    return metadata.get('fingerprint') == legacy_fingerprint(spec)
