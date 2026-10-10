#!/usr/bin/env python3
from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from pathlib import Path


PACKAGES = (
    "numpy",
    "pandas",
    "scikit-learn",
    "PyYAML",
    "pytest",
    "ruff",
    "scipy",
    "joblib",
    "threadpoolctl",
    "cloudpickle",
    "narwhals",
)


def command(*args: str) -> str | None:
    try:
        return subprocess.run(
            list(args),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main() -> None:
    out = Path(os.environ.get("PUBLICATION_ENV_OUT", "artifacts/publication-freeze/environment.json"))
    out.parent.mkdir(parents=True, exist_ok=True)

    packages: dict[str, str | None] = {}
    for name in PACKAGES:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None

    payload = {
        "git_commit": command("git", "rev-parse", "HEAD"),
        "git_status_porcelain": command("git", "status", "--porcelain"),
        "python": {
            "version": sys.version,
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "platform": platform.platform(),
        },
        "runner": {
            "os": os.environ.get("RUNNER_OS"),
            "arch": os.environ.get("RUNNER_ARCH"),
            "name": os.environ.get("RUNNER_NAME"),
            "image_os": os.environ.get("ImageOS"),
            "image_version": os.environ.get("ImageVersion"),
        },
        "tools": {
            "pip": command(sys.executable, "-m", "pip", "--version"),
            "git": command("git", "--version"),
            "docker": command("docker", "--version"),
            "tshark": command("tshark", "--version"),
        },
        "packages": packages,
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
