import base64

import pytest
from test_pipeline import client, store
import config


@pytest.mark.parametrize('path', ['/', '/api/health', '/api/meetings', '/api/assignments', '/static/app.js', '/docs'])
def test_shared_password_protects_entire_app(client, monkeypatch, path):
    monkeypatch.setattr(config, 'APP_AUTH_PASSWORD', 'a-long-test-password', raising=False)
    monkeypatch.setattr(config, 'APP_AUTH_USER', 'demo', raising=False)
    assert client.get(path).status_code == 401
    assert client.get(path, auth=('demo', 'wrong')).status_code == 401
    response = client.get(path, auth=('demo', 'a-long-test-password'))
    assert response.status_code == 200
    assert response.headers.get('cache-control') == 'no-store'


def test_healthz_does_not_expose_configuration(client, monkeypatch):
    monkeypatch.setattr(config, 'APP_AUTH_PASSWORD', 'a-long-test-password', raising=False)
    result = client.get('/healthz')
    assert result.status_code == 200
    assert set(result.json()) == {'status'}


def test_malformed_authorization_is_unauthorized(client, monkeypatch):
    monkeypatch.setattr(config, 'APP_AUTH_PASSWORD', 'a-long-test-password', raising=False)
    for value in ['Basic !!!', 'Bearer test', 'Basic ' + base64.b64encode(b'no-colon').decode()]:
        assert client.get('/api/meetings', headers={'Authorization': value}).status_code == 401


def test_public_mode_requires_strong_password(monkeypatch):
    monkeypatch.setattr(config, 'PUBLIC_MODE', True, raising=False)
    monkeypatch.setattr(config, 'APP_AUTH_PASSWORD', '', raising=False)
    with pytest.raises(ValueError, match='APP_AUTH_PASSWORD'):
        config.validate_deployment()


def test_registry_does_not_load_meeting_history(client, store, monkeypatch):
    from test_pipeline import create_ready
    import db

    create_ready(store)
    monkeypatch.setattr(db, 'get_meeting', lambda _: pytest.fail('Registry loaded full meeting history'))
    assert len(client.get('/api/assignments').json()['assignments']) == 1


def test_dev_files_are_not_public_assets(client):
    assert client.get('/static/package.json').status_code == 404
    assert client.get('/static/node_modules/@playwright/test/package.json').status_code == 404


def test_malformed_and_different_scheme_origin_are_rejected(client):
    for origin in ['http://[', 'https://testserver', 'null']:
        assert client.post('/api/upload', headers={'Origin': origin}).status_code == 403
    # A valid same-origin request reaches route validation instead of being blocked.
    assert client.post('/api/upload', headers={'Origin': 'http://testserver'}).status_code == 422


def test_public_http_redirect_precedes_auth_and_preserves_export_query(client, monkeypatch):
    monkeypatch.setattr(config, 'PUBLIC_MODE', True)
    monkeypatch.setattr(config, 'APP_AUTH_PASSWORD', 'a-long-test-password')
    path = '/api/meetings/1/export?format=pdf&version_id=2'

    response = client.get(path, follow_redirects=False)

    assert response.status_code == 307
    assert response.headers['location'] == 'https://testserver' + path
    assert 'www-authenticate' not in response.headers
    challenge = client.get('https://testserver/api/meetings')
    assert challenge.status_code == 401
    assert challenge.headers['www-authenticate'].startswith('Basic ')
    signed_in = client.get(
        'https://testserver/api/meetings', auth=('demo', 'a-long-test-password')
    )
    assert signed_in.status_code == 200
    assert signed_in.headers['strict-transport-security'].startswith('max-age=')
    assert signed_in.headers['cache-control'] == 'no-store'


def test_correct_password_can_sign_in_after_failed_attempt_window_expires(client, monkeypatch):
    import access
    from types import SimpleNamespace
    now = [10000.0]
    monkeypatch.setattr(access, 'time', SimpleNamespace(monotonic=lambda: now[0]))
    monkeypatch.setattr(config, 'APP_AUTH_PASSWORD', 'a-long-test-password')
    monkeypatch.setattr(config, 'APP_AUTH_USER', 'demo')
    auth = ('demo', 'a-long-test-password')
    # Reset shared middleware state using an ordinary successful sign-in.
    assert client.get('/api/meetings', auth=auth).status_code == 200
    for _ in range(20):
        assert client.get('/api/meetings', auth=('demo', 'wrong')).status_code == 401
    limited = client.get('/api/meetings', auth=('demo', 'wrong'))
    assert limited.status_code == 429
    assert int(limited.headers['retry-after']) > 0
    assert limited.headers['cache-control'] == 'no-store'

    assert client.get('/api/meetings', auth=auth).status_code == 429
    now[0] += 61
    assert client.get('/api/meetings', auth=auth).status_code == 200
    assert client.get('/api/meetings', auth=('demo', 'wrong')).status_code == 401


def test_initial_browser_challenges_do_not_consume_failed_password_budget(client, monkeypatch):
    monkeypatch.setattr(config, 'APP_AUTH_PASSWORD', 'a-long-test-password')
    assert client.get('/api/meetings', auth=('demo', 'a-long-test-password')).status_code == 200
    for _ in range(25):
        assert client.get('/api/meetings').status_code == 401
