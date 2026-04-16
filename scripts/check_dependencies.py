#!/usr/bin/env python3
"""Check and auto-install runtime dependencies for the free-first video pipeline.

What it does:
- Verifies Python packages: `edge-tts`, `openai-whisper`, `requests` (module name `whisper`).
- Attempts to `pip install` missing packages using the current Python interpreter.
- Checks for `ffmpeg` and `ffprobe` on PATH; attempts to install via `choco` or `winget` if available.
- Checks presence of `PEXELS_API_KEY` and `PIXABAY_API_KEY` environment variables.
- Writes a JSON report to `output/dependency_check_report.json` and prints a summary.

Note: Installing `openai-whisper` may require additional system dependencies (CUDA/torch) for best performance.
"""
import sys
import subprocess
import importlib
import shutil
import os
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
OUT.mkdir(parents=True, exist_ok=True)
REPORT = OUT / "dependency_check_report.json"

PACKAGE_MAP = {
    "edge_tts": "edge-tts",
    "whisper": "openai-whisper",
    "requests": "requests",
}

def try_import(module_name: str):
    try:
        importlib.import_module(module_name)
        return True, None
    except Exception as e:
        return False, str(e)

def pip_install(package: str):
    print(f"Installing {package} via pip...")
    cmd = [sys.executable, "-m", "pip", "install", package]
    res = subprocess.run(cmd)
    return res.returncode == 0

def ensure_packages():
    # NOTE: avoid importing heavy packages (e.g., torch) after install because imports
    # can trigger long native init. Instead verify installation via `pip show`.
    results = {}
    for mod, pip_name in PACKAGE_MAP.items():
        ok, err = try_import(mod)
        results[mod] = {"present": ok, "error": err, "pip_name": pip_name, "attempted_install": False, "installed": False}
        if not ok:
            results[mod]["attempted_install"] = True
            success = pip_install(pip_name)
            results[mod]["installed"] = success
            if success:
                # verify via pip show instead of import to avoid expensive runtime init
                try:
                    res = subprocess.run([sys.executable, "-m", "pip", "show", pip_name], capture_output=True)
                    results[mod]["present_after_install"] = (res.returncode == 0)
                    results[mod]["pip_show"] = res.stdout.decode(errors="ignore")[:2000]
                except Exception as e:
                    results[mod]["present_after_install"] = False
                    results[mod]["pip_show_error"] = str(e)
    return results

def check_ffmpeg():
    ff = shutil.which("ffmpeg") is not None
    ffprobe = shutil.which("ffprobe") is not None
    installed_via = None
    if not ff:
        # try chocolatey
        if shutil.which("choco"):
            print("Attempting to install ffmpeg via choco...")
            try:
                subprocess.run(["choco", "install", "ffmpeg", "-y"], check=True)
                ff = shutil.which("ffmpeg") is not None
                installed_via = "choco"
            except Exception as e:
                print("choco install failed:", e)
        elif shutil.which("winget"):
            print("Attempting to install ffmpeg via winget (may require interaction)...")
            try:
                subprocess.run(["winget", "install", "Gyan.FFmpeg", "-e"], check=False)
                ff = shutil.which("ffmpeg") is not None
                installed_via = "winget"
            except Exception as e:
                print("winget install failed:", e)
    return {"ffmpeg_on_path": ff, "ffprobe_on_path": ffprobe, "installed_via": installed_via}

def check_env_vars():
    keys = ["PEXELS_API_KEY", "PIXABAY_API_KEY"]
    return {k: (os.getenv(k) is not None) for k in keys}

def main():
    print("Running dependency check...")
    pkg_res = ensure_packages()
    ff_res = check_ffmpeg()
    env_res = check_env_vars()

    report = {"packages": pkg_res, "ffmpeg": ff_res, "env": env_res}

    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\nDependency check report written to:", REPORT)
    # Print summary
    for mod, info in pkg_res.items():
        status = "OK" if info.get("present") or info.get("present_after_install") else "MISSING"
        print(f"Package {mod}: {status}")
    print(f"ffmpeg on PATH: {ff_res.get('ffmpeg_on_path')}")
    for k, v in env_res.items():
        print(f"Env {k}: {'SET' if v else 'MISSING'}")

if __name__ == "__main__":
    main()
