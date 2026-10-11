"""Explicit native HTTP fixture; security tests can disable its action marker."""

from flask.testing import FlaskClient

from fruth_core.http_contract import action_headers


class _ApiClient(FlaskClient):
    def open(self, *args, **kwargs):
        kwargs.setdefault('base_url', 'http://127.0.0.1:5011')
        return super().open(*args, **kwargs)


def api_client(app, *, authorized: bool = True):
    environ = {}
    if authorized:
        environ.update({'HTTP_' + key.upper().replace('-', '_'): value
                        for key, value in action_headers().items()})
    client = _ApiClient(app, app.response_class)
    client.environ_base.update(environ)
    return client
