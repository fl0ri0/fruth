"""Pin the actual browser bytes and the dashboard's local dependency entry."""
import hashlib
from html.parser import HTMLParser
from pathlib import Path
from flask import Flask, render_template_string

from scripts.build_release_archive import RELEASE_BROWSER_DEPENDENCY_FILES

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / 'static/vendor/axios-1.20.0'


class ScriptSources(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sources = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script' and dict(attrs).get('src'):
            self.sources.append(dict(attrs)['src'])


def test_dashboard_loads_exactly_one_local_axios_before_transport():
    parser = ScriptSources()
    with Flask('browser-dependency-fixture').test_request_context():
        parser.feed(render_template_string((ROOT / 'fruth_webUI.html').read_text()))
    axios = [src for src in parser.sources if 'axios' in src.lower()]
    assert axios == ['/static/vendor/axios-1.20.0/axios.min.js']
    assert parser.sources.index(axios[0]) < parser.sources.index('/static/ui/request-transport.js')


def test_official_browser_build_map_and_license_digests():
    expected = {
        'axios.min.js': '7c433c881c3b0903317193a0dd5af714ce0f65cf77d5c7f067f18b96f0e8e2c7',
        'axios.min.js.map': '15fd3ff1dae38f059a7d7be7b7cc1fa641d7833f93b62a1832eb9c5fa4f62ad1',
        'LICENSE.txt': '82761059eaedacb3356803aea8a170d8298609f91b14fc32ee1bfb40d690183c',
    }
    for name, digest in expected.items():
        assert hashlib.sha256((VENDOR / name).read_bytes()).hexdigest() == digest
    assert 'Axios v1.20.0' in (VENDOR / 'axios.min.js').read_text()[:80]
    assert 'sourceMappingURL=axios.min.js.map' in (VENDOR / 'axios.min.js').read_text()[-100:]
    assert set(p.name for p in RELEASE_BROWSER_DEPENDENCY_FILES) == set(expected) | {'README.txt'}
