"""Start the pinned, loopback-only vLLM server from its Linux environment."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import sysconfig

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.inference import MODEL_ID, REVISION


def server_command():
    return [sys.executable, "-m", "vllm.entrypoints.openai.api_server",
            "--model", MODEL_ID, "--served-model-name", MODEL_ID, "--revision", REVISION,
            "--download-dir", str(ROOT / "data" / "model-cache"),
            "--host", "127.0.0.1", "--port", "8001", "--dtype", "half",
            "--max-model-len", "6144", "--max-num-seqs", "1", "--max-num-batched-tokens", "2048",
            "--gpu-memory-utilization", "0.85", "--enforce-eager", "--compilation-config", json.dumps({"mode": 0}),
            "--enable-prefix-caching", "--generation-config", "vllm", "--seed", "42",
            "--limit-mm-per-prompt", json.dumps({"image": 2, "video": 0}),
            "--mm-processor-kwargs", json.dumps({"size": {"shortest_edge": 128 * 32 * 32, "longest_edge": 768 * 32 * 32}}),
            "--mm-encoder-attn-backend", "TORCH_SDPA", "--mm-processor-cache-gb", "0.25",
            "--no-enable-log-requests"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-command", action="store_true", help="Inspect the server command without loading a model.")
    args = parser.parse_args()
    command = server_command()
    if args.print_command:
        print(shlex.join(command))
        return 0
    if sys.platform != "linux":
        parser.error("Run this script with the Linux/WSL vLLM environment. See docs/vllm.md.")
    if not shutil.which("cc") or not (Path(sysconfig.get_path("include")) / "Python.h").exists():
        parser.error("Triton requires a C compiler and Python headers. Install build-essential and python3-dev in Ubuntu.")
    print("Loading PyTorch in WSL...", flush=True)
    import torch
    print("Loading vLLM...", flush=True)
    import vllm
    if vllm.__version__ != "0.11.2":
        parser.error("Install backend/requirements-vllm.txt in the isolated Linux environment.")
    print("Checking CUDA access...", flush=True)
    if not torch.cuda.is_available() or torch.cuda.get_device_capability() < (7, 5):
        parser.error("The WSL server requires CUDA and compute capability 7.5 or newer.")
    overrides = {"VLLM_ATTENTION_BACKEND": "TRITON_ATTN", "OMP_NUM_THREADS": "1",
                 "VLLM_NO_USAGE_STATS": "1", "DO_NOT_TRACK": "1"}
    environment = {**os.environ, **overrides}
    record = ROOT / "data" / "server" / "vllm-launch.json"
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({"started_at": datetime.now(timezone.utc).isoformat(), "model_id": MODEL_ID,
                                 "revision": REVISION, "command": command, "environment": overrides,
                                 "vllm_version": vllm.__version__, "torch_version": torch.__version__,
                                 "gpu": torch.cuda.get_device_name(), "compute_capability": torch.cuda.get_device_capability()},
                                indent=2), encoding="utf-8")
    print("Starting Qwen3-VL in vLLM on http://127.0.0.1:8001; Ctrl+C stops the GPU server.", flush=True)
    try:
        return subprocess.call(command, env=environment, cwd=ROOT)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nStartup cancelled.", flush=True)
        raise SystemExit(130) from None
