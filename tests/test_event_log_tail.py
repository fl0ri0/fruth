"""Recent-event reads use synthetic logs only; no runtime or provider access."""
import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from fruth_services import events


def legacy_read(path, limit=200, **filters):
    matches = []
    for line in reversed(path.read_text(encoding='utf-8').splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and all(
                not expected or str(value.get(key) or '') == expected
                for key, expected in filters.items()):
            matches.append(value)
            if len(matches) >= limit:
                break
    return matches


@pytest.mark.parametrize('chunk_size', [1, 3, 17, 65536])
@pytest.mark.parametrize('separator', ['\n', '\r\n', '\r', '\u2028'])
def test_reverse_reader_preserves_order_filters_and_text_boundaries(tmp_path, chunk_size, separator):
    path = tmp_path / 'events.jsonl'
    rows = [' ', '{broken', '[]', 'null']
    rows += [json.dumps({'id': n, 'message': 'Grüezi 🐈 東京', 'category': 'chat' if n % 3 else 'runtime',
                        'action': 'request' if n % 2 else 'start', 'status': 'ok' if n % 5 else 'failed'},
                       ensure_ascii=False) for n in range(35)]
    path.write_bytes(separator.join(rows).encode('utf-8'))  # valid final row without LF
    before = path.read_bytes()
    with patch.object(events, '_EVENT_READ_CHUNK_BYTES', chunk_size):
        for filters in ({}, {'category': 'runtime'}, {'status': 'failed', 'action': 'start'},
                        {'category': 'absent'}, {'category': '', 'status': ''}):
            assert events.read_events(path=path, limit=4, **filters) == legacy_read(path, limit=4, **filters)
    assert path.read_bytes() == before


def test_large_record_and_partial_tail_keep_exact_older_evidence(tmp_path):
    path = tmp_path / 'events.jsonl'
    older = {'id': 'older', 'message': 'Zürich 🐈' * 30000}
    newest = {'id': 'newest', 'message': 'intact'}
    path.write_bytes(('\n'.join(json.dumps(row, ensure_ascii=False) for row in [older, newest])
                      + '\n  \n[]\n{"interrupted":').encode('utf-8'))
    assert events.read_events(path=path, limit=2) == [newest, older]


def test_missing_empty_and_nonpositive_limit_do_not_open_log(tmp_path):
    path = tmp_path / 'events.jsonl'
    assert events.read_events(path=path) == []
    path.touch()
    assert events.read_events(path=path) == []
    with patch.object(Path, 'open', side_effect=AssertionError('unnecessary open')):
        assert events.read_events(path=path, limit=0) == []
        assert events.read_events(path=path, limit=-1) == []


def test_recent_limit_stops_disk_reads_before_unrelated_history(tmp_path):
    path = tmp_path / 'events.jsonl'
    path.write_bytes(b'{"category":"old","message":"history"}\n' * 100000)
    recent = [{'id': n, 'category': 'chat'} for n in range(12)]
    with path.open('ab') as handle:
        handle.write((''.join(json.dumps(row) + '\n' for row in recent)).encode())
    native_open = Path.open
    reads = []
    handles = []

    class CountedReader:
        def __init__(self, handle):
            self.handle = handle

        def __getattr__(self, name):
            return getattr(self.handle, name)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.handle.close()

        def read(self, size=-1):
            assert 0 < size <= events._EVENT_READ_CHUNK_BYTES
            result = self.handle.read(size)
            reads.append(len(result))
            return result

    def open_counted(target, *args, **kwargs):
        assert target == path and args == ('rb',)
        wrapped = CountedReader(native_open(target, *args, **kwargs))
        handles.append(wrapped.handle)
        return wrapped

    with patch.object(Path, 'open', side_effect=open_counted, autospec=True), \
            patch.object(Path, 'read_text', side_effect=AssertionError('whole-file read')):
        assert events.read_events(path=path, limit=12) == list(reversed(recent))
    assert sum(reads) == events._EVENT_READ_CHUNK_BYTES
    assert len(handles) == 1 and handles[0].closed


def test_each_read_observes_fresh_append_and_replacement(tmp_path):
    path = tmp_path / 'events.jsonl'
    path.write_text('{"id":1}\n')
    assert events.read_events(path=path, limit=1) == [{'id': 1}]
    with path.open('a') as handle:
        handle.write('{"id":2}\n')
    assert events.read_events(path=path, limit=1) == [{'id': 2}]
    replacement = tmp_path / 'replacement.jsonl'
    replacement.write_text('{"id":3}\n')
    replacement.replace(path)
    assert events.read_events(path=path, limit=1) == [{'id': 3}]


def test_append_during_read_stays_outside_initial_end_boundary():
    class AppendingFile(io.BytesIO):
        def read(self, size=-1):
            position = self.tell()
            self.seek(0, io.SEEK_END)
            self.write(b'{"id":"later"}\n')
            self.seek(position)
            return super().read(size)

    with AppendingFile(b'{"id":"initial"}\n') as handle:
        assert list(events._iter_event_lines_reverse(handle)) == ['{"id":"initial"}']


def test_encountered_invalid_utf8_is_not_silently_replaced(tmp_path):
    path = tmp_path / 'events.jsonl'
    path.write_bytes(b'{"id":1}\n{"message":"\xff"}\n')
    with pytest.raises(UnicodeDecodeError):
        events.read_events(path=path)
