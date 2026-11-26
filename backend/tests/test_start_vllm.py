"""Exercise the PowerShell launcher without starting WSL or loading a model."""

from pathlib import Path
import shutil
import subprocess

import pytest


LAUNCHER = Path(__file__).resolve().parents[2] / "scripts" / "start-vllm.ps1"
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")
pytestmark = pytest.mark.skipif(not POWERSHELL, reason="PowerShell is not installed")


@pytest.mark.parametrize("exit_code", [1, 130, -1073741510])
def test_failed_or_cancelled_wsl_lookup_does_not_claim_ubuntu_is_missing(tmp_path, exit_code):
    command = f"""
function wsl.exe {{
    if ($args -notcontains 'wslpath') {{ throw 'Server must not start after failed lookup.' }}
    $global:LASTEXITCODE = {exit_code}
}}
& '{LAUNCHER}'
"""
    result = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", command],
                            cwd=tmp_path, capture_output=True, text=True, timeout=30)
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert f"exit code {exit_code}" in output
    assert "failed or was cancelled" in output
    assert "wsl.exe --list --verbose" in output
    assert "Ubuntu-24.04 is unavailable" not in output
    assert "Server must not start" not in output


def test_launcher_uses_its_project_root_from_another_directory(tmp_path):
    command = f"""
function wsl.exe {{
    if ($args -contains 'wslpath') {{
        if ($args[-1] -ne '{LAUNCHER.parents[1]}') {{ throw 'Incorrect project root.' }}
        $global:LASTEXITCODE = 0
        return '/mnt/c/constant-test'
    }}
    if ($args -notcontains '/mnt/c/constant-test' -or $args -notcontains '/opt/constant-vllm/bin/python') {{
        throw 'Incorrect Linux launch path.'
    }}
    Write-Output 'Launch paths verified.'
    $global:LASTEXITCODE = 0
}}
& '{LAUNCHER}'
"""
    result = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", command],
                            cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Launch paths verified." in result.stdout
