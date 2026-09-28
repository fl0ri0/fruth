"""Select complete, explicitly authored model-facing policy scopes."""

from __future__ import annotations

import hashlib
import re


def select_policy_scope(policy: str, scope: str, *, source: str = 'FRUTH_INFERENCE.md') -> str:
    if scope not in {'routing', 'execution'}:
        raise ValueError(f'Unknown Fruth policy scope: {scope}')
    if '<!-- fruth-policy:' not in policy:
        # User-supplied legacy policy remains complete, including its tail.
        return policy
    blocks = {}
    for name in ('common', 'routing', 'execution'):
        start = f'<!-- fruth-policy:{name}:start -->'
        end = f'<!-- fruth-policy:{name}:end -->'
        if policy.count(start) != 1 or policy.count(end) != 1:
            raise ValueError(f'Fruth policy requires exactly one complete {name} scope.')
        match = re.search(re.escape(start) + r'([\s\S]*?)' + re.escape(end), policy)
        if not match or not match[1].strip() or '<!-- fruth-policy:' in match[1]:
            raise ValueError(f'Fruth policy has an invalid {name} scope.')
        blocks[name] = match[1].strip()
    digest = hashlib.sha256(policy.encode('utf-8')).hexdigest()
    return (
        f'Fruth policy scope: common + {scope}; source: {source}; '
        f'source_sha256: {digest}\n\n{blocks["common"]}\n\n{blocks[scope]}'
    )
