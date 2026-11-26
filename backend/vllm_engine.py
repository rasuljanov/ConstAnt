"""Loopback client for the separately managed Linux/WSL vLLM server."""

import base64
import io
import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from PIL import Image

from .inference import MODEL_ID, REVISION, SYSTEM, build_messages


class VllmEngine:
    max_images = 2

    def __init__(self, base_url=None):
        self.base_url = (base_url or os.getenv("VLLM_BASE_URL", "http://127.0.0.1:8001")).rstrip("/")
        url = urlsplit(self.base_url)
        if (url.scheme != "http" or url.hostname not in ("127.0.0.1", "localhost", "::1")
                or url.username or url.password or url.path or url.query or url.fragment):
            raise ValueError("VLLM_BASE_URL must be a loopback HTTP origin, for example http://127.0.0.1:8001.")
        self.connected = self.loading = False
        self.error = self.version = None
        self.max_model_len = 6144
        self.opener = build_opener(ProxyHandler({}))

    def status(self):
        # The standard models API does not attest a checkpoint revision or quantization.
        return {"model_id": MODEL_ID, "revision": None, "expected_revision": REVISION,
                "backend": "vllm", "managed_gpu": False, "endpoint": self.base_url,
                "state": "loading" if self.loading else "loaded" if self.connected else "unloaded",
                "quantization": "server-managed", "compute_dtype": "server-managed", "attention": "server-managed",
                "server_version": self.version, "max_model_len": self.max_model_len, "error": self.error}

    def _request(self, path, payload=None, timeout=300):
        request = Request(self.base_url + path,
                          data=None if payload is None else json.dumps(payload).encode("utf-8"),
                          headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=timeout) as response:
                result = json.load(response)
            if not isinstance(result, dict):
                raise ValueError("Expected a JSON object.")
            return result
        except HTTPError as exc:
            detail = exc.read(16_384).decode("utf-8", errors="replace")
            try:
                error = json.loads(detail)
                detail = error.get("error", error)
                detail = detail.get("message", detail) if isinstance(detail, dict) else detail
            except ValueError:
                pass
            self.error = f"vLLM HTTP {exc.code}: {str(detail)[:500]}"
            raise RuntimeError(self.error) from exc
        except (URLError, OSError, TimeoutError) as exc:
            self.connected = False
            self.error = f"Cannot reach vLLM at {self.base_url}. Start scripts/serve_vllm.py in WSL; see docs/vllm.md."
            raise RuntimeError(self.error) from exc
        except ValueError as exc:
            self.error = "vLLM returned an invalid JSON response."
            raise RuntimeError(self.error) from exc

    def load(self):
        if self.connected:
            return self.status()
        self.loading, self.error = True, None
        try:
            models = self._request("/v1/models", timeout=5).get("data", [])
            model = next((m for m in models if m.get("id") == MODEL_ID), None)
            if model is None:
                raise RuntimeError(f"vLLM must serve {MODEL_ID}. Check scripts/serve_vllm.py.")
            self.max_model_len = min(6144, int(model.get("max_model_len") or 6144))
            self.version = self._request("/version", timeout=5).get("version")
            self.connected = True
        except Exception as exc:
            self.error = str(exc)
            raise
        finally:
            self.loading = False
        return self.status()

    def unload(self):
        raise RuntimeError("vLLM owns the GPU in its WSL terminal. Stop that server with Ctrl+C to release GPU memory.")

    def generate(self, question, content, max_new_tokens, history=None, system=SYSTEM):
        started = time.perf_counter()
        blocks = []
        for block in content:
            if block["type"] == "text":
                blocks.append(dict(block))
            elif block["type"] == "image" and isinstance(block.get("image"), Image.Image):
                buffer = io.BytesIO()
                block["image"].convert("RGB").save(buffer, format="PNG")
                blocks.append({"type": "image_url", "image_url": {
                    "url": "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")}})
            else:
                raise ValueError("vLLM accepts prepared text and image blocks. Videos must use the frame sampler.")
        image_count = sum(b["type"] == "image_url" for b in blocks)
        if image_count > self.max_images:
            raise ValueError("The 16 GB vLLM profile accepts two prepared views per model call.")
        self.load()
        kept_history = list(history or [])
        while True:
            messages = build_messages(question, blocks, kept_history, system)
            tokens = self._request("/tokenize", {"model": MODEL_ID, "messages": messages,
                                                "add_generation_prompt": True})
            count = tokens.get("count")
            if not isinstance(count, int) or count < 0:
                raise RuntimeError("vLLM /tokenize did not return a valid token count.")
            if count + max_new_tokens <= self.max_model_len:
                break
            if not kept_history:
                raise ValueError("Evidence exceeds the vLLM context budget. Select fewer sources or a shorter table result.")
            kept_history = kept_history[2:]
        request_start = time.perf_counter()
        result = self._request("/v1/chat/completions", {
            "model": MODEL_ID, "messages": messages, "max_tokens": max_new_tokens,
            "temperature": 0, "top_p": 1, "seed": 42, "stream": False})
        request_seconds = time.perf_counter() - request_start
        try:
            choice = result["choices"][0]
            answer = choice["message"]["content"]
            usage = result["usage"]
            if not isinstance(answer, str) or not isinstance(usage["prompt_tokens"], int) or not isinstance(usage["completion_tokens"], int):
                raise ValueError("Missing answer or token usage.")
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RuntimeError("vLLM returned an incomplete chat response.") from exc
        self.error = None
        return answer, {"backend": "vllm", "server_version": self.version,
                        "input_tokens": usage["prompt_tokens"], "output_tokens": usage["completion_tokens"],
                        "history_turns_used": len(kept_history), "history_turns_omitted": len(history or []) - len(kept_history),
                        "request_seconds": round(request_seconds, 3),
                        "inference_seconds": round(time.perf_counter() - started, 3),
                        "request_output_tokens_per_second": round(usage["completion_tokens"] / max(request_seconds, .001), 2),
                        "prepared_images": image_count, "finish_reason": choice.get("finish_reason"),
                        "truncated": choice.get("finish_reason") == "length"}
