"""Request/deployment regressions found during the pre-push review."""
import pytest
from types import SimpleNamespace
from test_pipeline import client, store
import config


def test_local_mode_cannot_bind_to_all_network_interfaces(monkeypatch):
    monkeypatch.setattr(config, 'PUBLIC_MODE', False)
    monkeypatch.setattr(config, 'HOST', '0.0.0.0')
    with pytest.raises(ValueError, match='loopback'):
        config.validate_deployment()


def test_password_limit_blocks_further_guesses_until_window_expires(client, monkeypatch):
    import access
    monkeypatch.setattr(config, 'APP_AUTH_PASSWORD', 'a-long-test-password')
    monkeypatch.setattr(config, 'APP_AUTH_USER', 'demo')
    now = [1000.0]
    monkeypatch.setattr(access, 'time', SimpleNamespace(monotonic=lambda: now[0]))
    assert client.get('/api/meetings', auth=('demo', config.APP_AUTH_PASSWORD)).status_code == 200
    for _ in range(20):
        assert client.get('/api/meetings', auth=('demo', 'wrong')).status_code == 401
    response = client.get('/api/meetings', auth=('demo', config.APP_AUTH_PASSWORD))
    assert response.status_code == 429
    assert 0 < int(response.headers['retry-after']) <= 60
    now[0] += 61
    assert client.get('/api/meetings', auth=('demo', config.APP_AUTH_PASSWORD)).status_code == 200


def test_negative_content_length_is_rejected(client):
    assert client.post('/api/upload', headers={'Content-Length': '-1'}).status_code == 400
