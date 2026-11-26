$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Write-Host 'Starting Ubuntu and the vLLM environment (cold startup may take a few minutes; Ctrl+C cancels)...'
$linuxProject = & wsl.exe -d Ubuntu-24.04 -u root --exec wslpath -a $projectRoot
if ($LASTEXITCODE -ne 0) { throw "WSL startup/path lookup failed or was cancelled (exit code $LASTEXITCODE). Run 'wsl.exe --list --verbose' to check Ubuntu-24.04, then retry and allow startup to finish. See docs/vllm.md." }
& wsl.exe -d Ubuntu-24.04 -u root --cd $linuxProject.Trim() --exec /opt/constant-vllm/bin/python -B scripts/serve_vllm.py
exit $LASTEXITCODE
