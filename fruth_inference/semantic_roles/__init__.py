"""Semantic work roles for the interpretive inference layer's advisory decision surface."""

from .registry import (
    build_semantic_role_catalog,
    normalize_semantic_role_id,
    normalize_semantic_role_ids,
    semantic_role,
    semantic_role_for_lens,
)

__all__ = [
    'build_semantic_role_catalog',
    'normalize_semantic_role_id',
    'normalize_semantic_role_ids',
    'semantic_role',
    'semantic_role_for_lens',
]
