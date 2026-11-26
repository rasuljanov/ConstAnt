import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import threading

from PIL import Image
import pytest

from backend.inference import MODEL_ID, QwenEngine, create_engine
from backend.vllm_engine import VllmEngine
from scripts.serve_vllm import server_command


@pytest.fixture
def server():
    state = {"requests": [], "token_count": 100, "model": MODEL_ID, "fail_chat": False}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path == "/v1/models":
                self.reply({"data": [{"id": state["model"], "max_model_len": 6144}]})
            else:
                assert self.path == "/version"
                self.reply({"version": "TEST SERVER"})

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["requests"].append((self.path, payload))
            if self.path == "/tokenize":
                count = state["token_count"]
                if callable(count):
                    count = count(payload)
                self.reply({"count": count})
            elif state["fail_chat"]:
                self.reply({"error": {"message": "TEST: CUDA out of memory"}}, 500)
            else:
                assert self.path == "/v1/chat/completions"
                self.reply({"choices": [{"message": {"content": "TEST ANSWER"}, "finish_reason": "stop"}],
                            "usage": {"prompt_tokens": 100, "completion_tokens": 3}})

        def reply(self, payload, status=200):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=http.serve_forever, daemon=True)
    worker.start()
    try:
        yield VllmEngine(f"http://127.0.0.1:{http.server_port}"), state
    finally:
        http.shutdown()
        http.server_close()
        worker.join()


def test_factory_selects_explicit_backend_without_importing_vllm(monkeypatch):
    monkeypatch.delenv("CONST_VLM_ENGINE", raising=False)
    assert isinstance(create_engine("unused"), VllmEngine)
    monkeypatch.setenv("CONST_VLM_ENGINE", "transformers")
    assert isinstance(create_engine("unused"), QwenEngine)
    monkeypatch.setenv("CONST_VLM_ENGINE", "vllm")
    assert isinstance(create_engine("unused"), VllmEngine)
    monkeypatch.setenv("CONST_VLM_ENGINE", "typo")
    with pytest.raises(ValueError, match="transformers or vllm"):
        create_engine("unused")


@pytest.mark.parametrize("url", ["https://example.com", "http://192.168.0.1:8001", "http://localhost:8001/v1",
                                  "http://user:pass@localhost:8001", "http://localhost:8001?secret=x"])
def test_only_loopback_origins_can_receive_site_evidence(url):
    with pytest.raises(ValueError, match="loopback"):
        VllmEngine(url)


def test_text_images_history_and_system_reach_server_without_loss(server):
    engine, state = server
    assert engine.status()["state"] == "unloaded" and state["requests"] == []
    image = Image.new("RGB", (32, 48), (12, 34, 56))
    content = [{"type": "text", "text": "Frame at 12.5 seconds"}, {"type": "image", "image": image}]
    history = [{"role": "user", "content": "Earlier question"},
               {"role": "assistant", "content": "Earlier answer [Selected tables]"}]
    answer, metrics = engine.generate("이번 장면은?", content, 64, history=history, system="TEST SYSTEM")
    assert answer == "TEST ANSWER" and metrics["backend"] == "vllm"
    assert metrics["prepared_images"] == 1 and metrics["history_turns_used"] == 2
    assert metrics["input_tokens"] == 100 and metrics["output_tokens"] == 3
    assert "peak_allocated_vram_gb" not in metrics and "generation_seconds" not in metrics
    assert [p for p, _ in state["requests"]] == ["/tokenize", "/v1/chat/completions"]
    body = state["requests"][-1][1]
    assert body["temperature"] == 0 and body["max_tokens"] == 64 and body["stream"] is False
    messages = body["messages"]
    assert messages[0]["content"][0]["text"] == "TEST SYSTEM"
    assert messages[2]["content"][0]["text"] == "Earlier answer"
    assert messages[-1]["content"][-1]["text"] == "이번 장면은?"
    encoded = messages[-1]["content"][1]["image_url"]["url"].split(",")[1]
    decoded = Image.open(io.BytesIO(base64.b64decode(encoded)))
    assert decoded.size == image.size and decoded.tobytes() == image.tobytes()
    assert content[1]["image"] is image and history[-1]["content"].endswith("[Selected tables]")
    assert engine.status()["state"] == "loaded" and engine.status()["revision"] is None
    with pytest.raises(RuntimeError, match=r"Ctrl\+C"):
        engine.unload()


def test_context_trims_old_pairs_and_performs_one_generation(server):
    engine, state = server
    state["token_count"] = lambda body: 6100 if len(body["messages"]) > 4 else 200
    history = [{"role": "user" if n % 2 == 0 else "assistant", "content": f"turn{n}"} for n in range(4)]
    _, metrics = engine.generate("Latest question", [], 64, history=history)
    assert metrics["history_turns_omitted"] == 2 and metrics["history_turns_used"] == 2
    assert sum(path == "/v1/chat/completions" for path, _ in state["requests"]) == 1
    messages = state["requests"][-1][1]["messages"]
    assert messages[1]["content"][0]["text"] == "turn2" and len(history) == 4


def test_oversized_evidence_never_generates_or_silently_truncates(server):
    engine, state = server
    state["token_count"] = 6140
    with pytest.raises(ValueError, match="context budget"):
        engine.generate("TEST", [], 64)
    assert [p for p, _ in state["requests"]] == ["/tokenize"]


def test_server_errors_do_not_fall_back_to_another_model(server):
    engine, state = server
    state["model"] = "wrong-model"
    with pytest.raises(RuntimeError, match="must serve"):
        engine.load()
    assert engine.status()["state"] == "unloaded"
    state["model"], state["fail_chat"] = MODEL_ID, True
    with pytest.raises(RuntimeError, match="CUDA out of memory"):
        engine.generate("TEST", [], 64)
    assert sum(path == "/v1/chat/completions" for path, _ in state["requests"]) == 1


def test_two_view_limit_fails_before_sending_evidence(server):
    engine, state = server
    with pytest.raises(ValueError, match="two prepared views"):
        engine.generate("TEST", [{"type": "image", "image": Image.new("RGB", (4, 4))}] * 3, 64)
    assert state["requests"] == []


def test_launcher_pins_model_and_turing_compatible_budget():
    args = server_command()
    assert args[args.index("--model") + 1] == MODEL_ID
    assert args[args.index("--host") + 1] == "127.0.0.1"
    assert args[args.index("--dtype") + 1] == "half"
    assert args[args.index("--max-model-len") + 1] == "6144"
    assert json.loads(args[args.index("--limit-mm-per-prompt") + 1]) == {"image": 2, "video": 0}
    assert "--enable-prefix-caching" in args and "--enforce-eager" in args


def test_launcher_reports_missing_compiler_before_loading_model(monkeypatch, capsys):
    from scripts import serve_vllm
    monkeypatch.setattr(serve_vllm.sys, "argv", ["serve_vllm.py"])
    monkeypatch.setattr(serve_vllm.sys, "platform", "linux")
    monkeypatch.setattr(serve_vllm.shutil, "which", lambda name: None)
    with pytest.raises(SystemExit) as exc:
        serve_vllm.main()
    assert exc.value.code == 2 and "build-essential" in capsys.readouterr().err


def test_interrupt_during_torch_import_reports_cancellation_without_traceback(monkeypatch, tmp_path, capsys):
    import builtins
    from pathlib import Path
    import runpy
    import shutil
    import sys
    import sysconfig

    script = Path(__file__).resolve().parents[2] / "scripts" / "serve_vllm.py"
    (tmp_path / "Python.h").touch()
    monkeypatch.setattr(sys, "argv", [str(script)])
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/cc")
    monkeypatch.setattr(sysconfig, "get_path", lambda name: str(tmp_path))
    original_import = builtins.__import__
    def interrupted_import(name, *args, **kwargs):
        if name == "torch":
            raise KeyboardInterrupt()
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", interrupted_import)
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(script), run_name="__main__")
    output = capsys.readouterr()
    assert exc.value.code == 130
    assert "Loading PyTorch in WSL..." in output.out and "Startup cancelled." in output.out
    assert "Traceback" not in output.err
