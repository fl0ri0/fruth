"""Canonical normalization remains stable when parsed JSON takes the fast path."""
import hashlib
import json
from collections import UserDict
from pathlib import Path
from types import MappingProxyType

import pytest

from fruth_services import response_frames as frames


def test_normalization_preserves_scalar_values_filters_and_canonical_digest():
    source = {
        ' padded ': {'zero': 0, 'false': False, 'float': -0.25, 'unicode': 'Grüezi'},
        'empty': '', 'none': None, 'empty_list': [], 'empty_map': {},
        'response_frame': {'not': 'public'}, 'image_data_url': 'hidden',
        'imageDataUrl': 'hidden', ' ': 'hidden',
        'sequence': [0, False, '', None, [], {}, {' keep ': 'yes', 'image_data_url': 'hidden'}],
    }
    expected = {
        'padded': {'zero': 0, 'false': False, 'float': -0.25, 'unicode': 'Grüezi'},
        'sequence': [0, False, {'keep': 'yes'}],
    }
    assert frames._json_safe(source) == expected
    canonical = json.dumps(expected, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    assert frames._response_map_digest(source) == hashlib.sha256(canonical).hexdigest()
    assert source['sequence'][2:6] == ['', None, [], {}]
    normalized = frames._json_safe(source)
    normalized['padded']['zero'] = 1
    normalized['sequence'][-1]['keep'] = 'changed'
    assert source[' padded ']['zero'] == 0
    assert source['sequence'][-1][' keep '] == 'yes'


@pytest.mark.parametrize('value', [None, '', 0, False, True, -3, 1.5, 'Grüezi'])
def test_root_scalars_are_preserved_even_when_empty(value):
    assert frames._json_safe(value) is value


def test_protocol_inputs_and_subclasses_retain_existing_normalization():
    class Integer(int):
        pass

    class Text(str):
        pass

    class CustomDict(dict):
        def items(self):
            return [(' exposed ', (0, False, None, Path('/isolated/evidence.json')))]

    class Description:
        def __str__(self):
            return 'bounded evidence'

    value = UserDict({
        'proxy': MappingProxyType({' text ': Text('kept'), 'count': Integer(2)}),
        'custom': CustomDict(ignored='not exposed'),
        'description': Description(),
    })
    assert frames._json_safe(value) == {
        'proxy': {'text': 'kept', 'count': 2},
        'custom': {'exposed': [0, False, '/isolated/evidence.json']},
        'description': 'bounded evidence',
    }


def test_custom_type_equality_cannot_impersonate_a_builtin_scalar():
    class EqualToEverything(type):
        def __eq__(cls, other):
            return True

        __hash__ = type.__hash__

    class Description(metaclass=EqualToEverything):
        def __str__(self):
            return 'bounded evidence'

    assert frames._json_safe(Description()) == 'bounded evidence'
