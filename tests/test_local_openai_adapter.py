import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from marvis_gateway_lab.local_openai_adapter import (
    LocalOpenAIAdapterConfig,
    run_local_openai_adapter,
)


class UpstreamHandler(BaseHTTPRequestHandler):
    captured = {}

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        UpstreamHandler.captured = {
            "path": self.path,
            "authorization": self.headers.get("Authorization"),
            "payload": json.loads(body),
        }

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        self.wfile.write(b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n')
        self.wfile.write(b"data: [DONE]\n\n")

    def log_message(self, format, *args):
        return


def test_local_openai_adapter_forwards_v1_chat_completions_with_configured_model(tmp_path):
    response, captured = _exercise_chat_endpoint(tmp_path, "/v1/chat/completions")

    assert b'data: {"choices":[{"delta":{"content":"ok"}}]}' in response
    assert captured == {
        "path": "/v1/chat/completions",
        "authorization": "Bearer secret-key",
        "payload": {
            "model": "configured-model",
            "messages": [{"role": "user", "content": "reply ok"}],
            "stream": True,
        },
    }


def test_local_openai_adapter_forwards_root_chat_completions_with_configured_model(tmp_path):
    response, captured = _exercise_chat_endpoint(tmp_path, "/chat/completions")

    assert b'data: {"choices":[{"delta":{"content":"ok"}}]}' in response
    assert captured["path"] == "/v1/chat/completions"
    assert captured["payload"]["model"] == "configured-model"


def test_local_openai_adapter_returns_success_for_canary_phrase_without_upstream(tmp_path):
    response, captured = _exercise_chat_endpoint(
        tmp_path,
        "/v1/chat/completions",
        messages=[{"role": "user", "content": "MARVIS_THIRD_PARTY_PING"}],
    )

    assert _stream_text(response) == "成功"
    assert b"data: [DONE]" in response
    assert captured == {}


def test_local_openai_adapter_exposes_local_model_health_and_model_list(tmp_path):
    adapter_config = LocalOpenAIAdapterConfig(
        listen_host="127.0.0.1",
        listen_port=0,
        upstream_base_url="http://127.0.0.1:1/v1",
        upstream_api_key="unused",
        model="configured-model",
        timeout_seconds=5,
        status_path=tmp_path / "status.json",
    )
    stop_event = threading.Event()
    adapter = run_local_openai_adapter(adapter_config, stop_event=stop_event)

    try:
        health = _get_json(f"http://127.0.0.1:{adapter.server_port}/health")
        models = _get_json(f"http://127.0.0.1:{adapter.server_port}/v1/models")
        root_models = _get_json(f"http://127.0.0.1:{adapter.server_port}/models")
        root = _get_json(f"http://127.0.0.1:{adapter.server_port}/")
    finally:
        stop_event.set()
        adapter.shutdown()

    assert health == {"ok": True}
    assert models == {
        "object": "list",
        "data": [
            {
                "id": "configured-model",
                "object": "model",
                "owned_by": "marvis-gateway-lab",
            }
        ],
    }
    assert root_models == models
    assert root == {
        "ok": True,
        "mode": "local-openai-adapter",
        "model": "configured-model",
    }


def _exercise_chat_endpoint(tmp_path, path, messages=None):
    UpstreamHandler.captured = {}
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()

    stop_event = threading.Event()
    adapter_config = LocalOpenAIAdapterConfig(
        listen_host="127.0.0.1",
        listen_port=0,
        upstream_base_url=f"http://127.0.0.1:{upstream.server_port}/v1",
        upstream_api_key="secret-key",
        model="configured-model",
        timeout_seconds=5,
        status_path=tmp_path / "status.json",
    )
    adapter = run_local_openai_adapter(adapter_config, stop_event=stop_event)

    try:
        response = _post_json(
            f"http://127.0.0.1:{adapter.server_port}{path}",
            {
                "model": "marvis-local-model",
                "messages": messages or [{"role": "user", "content": "reply ok"}],
                "stream": True,
            },
        )
        captured = dict(UpstreamHandler.captured)
    finally:
        stop_event.set()
        adapter.shutdown()
        upstream.shutdown()

    return response, captured


def _post_json(url, payload):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.read()


def _get_json(url):
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read())


def _stream_text(response):
    text = ""
    for raw_line in response.decode("utf-8").splitlines():
        if not raw_line.startswith("data: "):
            continue
        data = raw_line.removeprefix("data: ")
        if data == "[DONE]":
            continue
        payload = json.loads(data)
        text += payload["choices"][0]["delta"].get("content", "")
    return text
