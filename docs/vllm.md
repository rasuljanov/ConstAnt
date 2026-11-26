# vLLM on the Quadro RTX 5000

ConstAnt can send its Qwen calls to a separate **vLLM 0.11.2** server in Ubuntu 24.04 under WSL 2. FastAPI and Vue stay on Windows. Native Windows vLLM is not supported by the upstream project. The RTX 5000 reports CUDA capability 7.5; the launch profile uses FP16, Triton language attention and PyTorch SDPA vision attention, without BF16 or FlashAttention 2.

## Run

Use two terminals from the ConstAnt project root. The vLLM environment is `/opt/constant-vllm` inside the `Ubuntu-24.04` WSL distribution. It is separate from the Windows `.venv`.

Terminal 1, PowerShell:

```powershell
.\scripts\start-vllm.ps1
```

The launcher prints progress while importing PyTorch/vLLM, checking CUDA and starting the server. A cold startup can take a few minutes; the earlier GPU validation took about three minutes. Leave this terminal open until `Application startup complete` appears on port **8001**. Ctrl+C cancels startup. You do not need to activate Windows `.venv` for this command: the script uses the Linux environment directly.

Then use terminal 2, PowerShell:

```powershell
$env:CONST_VLM_ENGINE = "vllm"
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. vLLM is the default backend; the explicit environment variable above also overrides a previous Transformers selection in that terminal. Settings identifies it as `vllm`; **Connect vLLM** verifies the served model. The first question also connects automatically. No periodic model-health polling is added. A server error is reported directly; the app never silently changes inference engines.

Stop FastAPI with Ctrl+C in terminal 2. Stop vLLM with Ctrl+C in terminal 1 to free GPU memory. The app cannot unload a model owned by a separate process. Do not load the Transformers engine while vLLM owns the GPU.

### Interrupted startup or commands not found

If you pressed Ctrl+C while Ubuntu was starting, retry and let it finish. A failed or cancelled `wslpath` call does not establish that Ubuntu is missing. `wsl.exe --list --verbose` lists installed distributions; `Stopped` is a normal state before launch. The launcher starts `Ubuntu-24.04` automatically. Do not recreate the existing environment for this error alone.

Run both startup commands from the project root, where `scripts`, `.venv`, and `backend` are sibling directories. From inside `backend`, run `cd ..` first.

Reference: [Microsoft WSL basic commands](https://learn.microsoft.com/en-us/windows/wsl/basic-commands).

## Profile and behavior

- Same pinned `Qwen/Qwen3-VL-4B-Instruct` revision as the existing runtime. Cached model files are reused from `data/model-cache`.
- FP16 weights and KV cache, 6,144 total tokens, one active sequence, 85% GPU memory budget, eager execution and prefix caching. Two images per call, each bounded to the same processor pixel budget as Transformers. This is a conservative Turing profile; measured improvements must be established on the actual workload.
- Full orthophotos retain the existing tile scanner and progress/stop behavior. Videos retain the timestamped frame sampler; raw long videos are not uploaded to vLLM. More than two ordinary images also use the existing batched observation path.
- PNG data URLs preserve prepared image pixels. Evidence goes only to a configured loopback HTTP origin; the default is `http://127.0.0.1:8001`.
- `/tokenize` checks the context budget, removing oldest history pairs if necessary. This does not generate an answer. Each successful `generate` performs one chat-completion/model generation.
- Run metrics identify the backend, server version, token usage, omitted history and end-to-end request duration. Request throughput includes HTTP/queue time. Per-request GPU-kernel time and peak VRAM are not available through this API and are not fabricated.
- The models API does not attest the checkpoint revision or quantization. Runtime status marks these as server-managed; the launcher writes its actual arguments, pinned revision and installed versions to `data/server/vllm-launch.json`.

## Compare with Transformers

Stop the vLLM server first, then select the original engine in the FastAPI terminal:

```powershell
.\.venv\Scripts\python.exe -m pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-inference.txt
$env:CONST_VLM_ENGINE = "transformers"
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

The original Transformers profile defaults to **NF4**, while this vLLM profile uses **FP16**. That comparison changes both engine and precision. For an engine-only comparison, set `QWEN_LOAD_IN_4BIT=0` for Transformers and keep the same evidence, output limit and processor budget. Verify memory feasibility first. Record these as separate cohorts in the experiment notes. A backend switch does not fine-tune the model or implement RAG.

## Recreate the Linux environment

Only needed on a fresh installation. In PowerShell:

```powershell
wsl --install --distribution Ubuntu-24.04 --no-launch
wsl -d Ubuntu-24.04 -u root -- bash -lc 'apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv build-essential python3-dev && python3 -m venv /opt/constant-vllm'
$linuxProject = (wsl -d Ubuntu-24.04 -u root -- wslpath -a "$($PWD.Path)").Trim()
wsl -d Ubuntu-24.04 -u root --cd "$linuxProject" -- /opt/constant-vllm/bin/python -m pip install -r backend/requirements-vllm.txt
```

Do not install those requirements into Windows `.venv`. They include a different PyTorch build. This project pins an explicit vLLM version so its Turing attention backends and CLI arguments are reproducible; do not upgrade it independently of the launcher and validation checks.

If startup fails, keep the error log and inspect GPU use with `nvidia-smi`; close the competing model process before retrying. Do not disable multimodal memory profiling to hide an out-of-memory failure. `--print-command` prints the launch profile without loading a model:

```powershell
.\.venv\Scripts\python.exe -B scripts/serve_vllm.py --print-command
```

Upstream references: [GPU/Windows requirements](https://docs.vllm.ai/en/stable/getting_started/installation/gpu/), [Qwen3-VL recipe](https://docs.vllm.ai/projects/recipes/en/stable/Qwen/Qwen3-VL.html), [v0.11.2 OpenAI-compatible API](https://docs.vllm.ai/en/v0.11.2/serving/openai_compatible_server/), [v0.11.2 CUDA attention selection](https://docs.vllm.ai/en/v0.11.2/api/vllm/platforms/cuda/).
