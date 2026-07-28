"""Select the dedicated YOLO26 virtual environment at node startup."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def desired_python() -> Path:
    configured = os.environ.get("YOLO26_PYTHON")
    if configured:
        return Path(configured).expanduser().absolute()
    return (Path.home() / ".venvs/yolo26/bin/python").absolute()


def ensure_yolo_runtime() -> None:
    target = desired_python()
    current = Path(sys.executable).absolute()
    if current == target:
        return
    if os.environ.get("YOLO26_RUNTIME_REEXEC") == "1":
        raise RuntimeError(
            f"YOLO26 runtime re-exec failed: current={current}, requested={target}"
        )
    if not target.is_file() or not os.access(target, os.X_OK):
        raise RuntimeError(
            f"YOLO26 Python was not found at {target}. Complete the YOLO26 "
            "environment tutorial or set YOLO26_PYTHON."
        )
    environment = os.environ.copy()
    environment["YOLO26_RUNTIME_REEXEC"] = "1"
    environment["PYTHONNOUSERSITE"] = "1"
    os.execve(
        str(target),
        [str(target), "-m", "yolo26_ros.detector_node", *sys.argv[1:]],
        environment,
    )
