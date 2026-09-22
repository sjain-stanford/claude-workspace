"""HTTP integration tests for the review queue and mutation boundary."""
import json
import re
import threading
import urllib.error
import urllib.request
from unittest.mock import Mock

import pytest

from peanut_review import review_queue
from peanut_review.web.app import SessionRegistry, make_server


@pytest.fixture
def server(tmp_path):
    registry = SessionRegistry([tmp_path])
    queue = Mock()
    queue.payload.return_value = {"items": [], "accounts": [], "refreshing": False}
    queue.enqueue.return_value = {"id": "job", "status": "queued"}
    http = make_server("127.0.0.1", 0, registry, queue=queue, base_url="/pr")
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{http.server_port}", queue
    http.shutdown()
    http.server_close()
    thread.join()


def request(url, path, *, data=None, headers=None):
    encoded = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url + path, data=encoded, headers=headers or {})
    try:
        with urllib.request.urlopen(req) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def token(url):
    code, html = request(url, "/queue")
    assert code == 200
    return re.search(r'PR_QUEUE_TOKEN = "([^"]+)"', html)[1]


def test_queue_page_assets_and_navigation(server):
    url, queue = server
    code, html = request(url, "/queue")
    assert code == 200
    assert 'href="/pr/"' in html
    assert '/pr/assets/queue.js?v=' in html
    assert "Your review queue" in html
    code, html = request(url, "/")
    assert 'href="/pr/queue"' in html
    code, javascript = request(url, "/assets/queue.js")
    assert code == 200 and "PR_QUEUE_TOKEN" in javascript
    code, payload = request(url, "/api/queue")
    assert code == 200 and json.loads(payload)["items"] == []


def test_queue_post_requires_page_token_and_same_origin(server):
    url, queue = server
    assert request(url, "/api/queue/start", data={"key": "x"})[0] == 403
    headers = {"X-Peanut-Queue-Token": token(url), "Origin": "https://attacker.invalid"}
    assert request(url, "/api/queue/start", data={"key": "x"}, headers=headers)[0] == 403
    queue.enqueue.assert_not_called()
    headers["Origin"] = url
    assert request(url, "/api/queue/start", data={"key": "x"}, headers=headers)[0] == 202
    queue.enqueue.assert_called_once_with("x")


def test_queue_refresh_does_not_launch_review(server):
    url, queue = server
    headers = {"X-Peanut-Queue-Token": token(url)}
    assert request(url, "/api/queue/refresh", data={}, headers=headers)[0] == 202
    queue.refresh_async.assert_called_once()
    queue.enqueue.assert_not_called()


def test_queue_rejects_nonlocal_host_and_invalid_actions(server):
    url, queue = server
    assert request(url, "/api/queue", headers={"Host": "attacker.invalid"})[0] == 403
    headers = {"X-Peanut-Queue-Token": token(url)}
    assert request(url, "/api/queue/start", data=[], headers=headers)[0] == 400
    assert request(url, "/api/queue/start", data={}, headers=headers)[0] == 400
    queue.enqueue.side_effect = ValueError("Worktree unavailable")
    assert request(url, "/api/queue/start", data={"key": "x"}, headers=headers)[0] == 409
    assert request(url, "/api/queue/unknown", data={}, headers=headers)[0] == 404


@pytest.fixture
def startup(tmp_path, monkeypatch):
    from peanut_review.web import app
    http = Mock()
    http.server_address = ("127.0.0.1", 12345)
    captured = {}
    def stop_after_start():
        captured.update(json.loads((tmp_path / "web.pid").read_text()))
        raise KeyboardInterrupt
    http.serve_forever.side_effect = stop_after_start
    factory = Mock(return_value=http)
    monkeypatch.setattr(app, "make_server", factory)
    service = Mock()
    constructor = Mock(return_value=service)
    monkeypatch.setattr(review_queue, "ReviewQueue", constructor)
    return app, factory, constructor, service, captured


def save_queue_config(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"accounts": [{"login": "alice"}]}))
    return path


def test_standard_startup_loads_saved_queue_config(tmp_path, startup):
    app, factory, constructor, service, captured = startup
    config = save_queue_config(tmp_path / ".queue" / "config.json")
    app.serve([tmp_path])
    assert factory.call_args.kwargs["queue"] is service
    assert constructor.call_args.args[1]["accounts"][0]["login"] == "alice"
    assert captured["queue_config"] == str(config)
    service.start.assert_called_once()
    service.close.assert_called_once()


def test_explicit_queue_config_overrides_saved_config(tmp_path, startup):
    app, factory, constructor, service, captured = startup
    save_queue_config(tmp_path / ".queue" / "config.json")
    explicit = tmp_path / "selected.json"
    explicit.write_text(json.dumps({"accounts": [{"login": "bob"}]}))
    app.serve([tmp_path], queue_config=str(explicit))
    assert constructor.call_args.args[1]["accounts"][0]["login"] == "bob"
    assert captured["queue_config"] == str(explicit)


def test_startup_without_saved_config_keeps_session_only_ui(tmp_path, startup):
    app, factory, constructor, service, captured = startup
    app.serve([tmp_path])
    constructor.assert_not_called()
    assert factory.call_args.kwargs["queue"] is None
    assert captured["queue_config"] is None


def test_invalid_saved_config_fails_instead_of_disabling_queue(tmp_path, startup):
    app, factory, constructor, service, captured = startup
    path = save_queue_config(tmp_path / ".queue" / "config.json")
    path.write_text('{"accounts": []}')
    with pytest.raises(ValueError, match="accounts"):
        app.serve([tmp_path])
    factory.assert_not_called()


@pytest.mark.parametrize("inside_docker", [True, False])
def test_queue_supports_container_interface_only_inside_docker(tmp_path, startup, monkeypatch, inside_docker):
    from pathlib import Path
    app, factory, constructor, service, captured = startup
    save_queue_config(tmp_path / ".queue" / "config.json")
    original_is_file = Path.is_file
    monkeypatch.setattr(Path, "is_file", lambda path: inside_docker if str(path) == "/.dockerenv" else original_is_file(path))
    if inside_docker:
        app.serve([tmp_path], host="0.0.0.0")
        assert factory.call_args.args[0] == "0.0.0.0"
        assert factory.call_args.kwargs["queue"] is service
        service.start.assert_called_once()
    else:
        with pytest.raises(ValueError, match="inside Docker"):
            app.serve([tmp_path], host="0.0.0.0")
        factory.assert_not_called()
        constructor.assert_not_called()
