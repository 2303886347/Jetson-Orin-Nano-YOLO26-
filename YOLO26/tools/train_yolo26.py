#!/usr/bin/env python3
"""Run reproducible YOLO26 Detect training with stable project paths."""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRETRAINED_MODEL = PROJECT_ROOT / "models/pretrained/yolo26n.pt"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a YOLO26 Detect model")
    parser.add_argument(
        "--model", type=Path, default=PRETRAINED_MODEL
    )
    parser.add_argument(
        "--data",
        type=Path,
        required=True,
    )
    parser.add_argument("--project", type=Path, default=PROJECT_ROOT / "runs")
    parser.add_argument("--name", required=True)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=1)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--device", default="0")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument(
        "--amp",
        choices=("true", "false"),
        default="true",
        help="Enable CUDA automatic mixed precision (default: true)",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    model_path = args.model.expanduser().resolve()
    data_path = args.data.expanduser().resolve()
    project_path = args.project.expanduser().resolve()
    output_path = project_path / args.name
    if model_path.suffix.lower() != ".pt" or not model_path.is_file():
        raise SystemExit(f"Training requires an existing .pt model: {model_path}")
    if not data_path.is_file():
        raise SystemExit(f"Dataset YAML does not exist: {data_path}")
    if output_path.exists():
        if not args.overwrite:
            raise SystemExit(
                f"Training output already exists: {output_path}. "
                "Choose another --name or pass --overwrite."
            )
        shutil.rmtree(output_path)
    project_path.mkdir(parents=True, exist_ok=True)

    amp_enabled = args.amp == "true"
    if amp_enabled and not PRETRAINED_MODEL.is_file():
        raise SystemExit(
            "AMP verification requires the bundled pretrained model: "
            f"{PRETRAINED_MODEL}"
        )

    from ultralytics import YOLO

    print(f"Model: {model_path}")
    print(f"Dataset: {data_path}")
    print(f"Output: {output_path}")
    print(f"AMP: {amp_enabled}")
    model = YOLO(str(model_path), task="detect")
    original_cwd = Path.cwd()
    try:
        # Ultralytics 8.4.x resolves its AMP check model as ./yolo26n.pt.
        # Run that check beside the canonical bundled model without duplicating it.
        if amp_enabled:
            os.chdir(PRETRAINED_MODEL.parent)
        try:
            model.train(
                data=str(data_path),
                imgsz=args.imgsz,
                batch=args.batch,
                epochs=args.epochs,
                device=args.device,
                workers=args.workers,
                seed=args.seed,
                deterministic=True,
                patience=args.patience,
                project=str(project_path),
                name=args.name,
                exist_ok=True,
                plots=True,
                cache=False,
                amp=amp_enabled,
            )
        except RuntimeError as exc:
            error_text = str(exc)
            memory_markers = (
                "CUDA out of memory",
                "NVML_SUCCESS",
                "CUDACachingAllocator",
                "NvMapMemAlloc",
            )
            if any(marker in error_text for marker in memory_markers):
                raise SystemExit(
                    "CUDA/Jetson memory allocation failed. Stop camera, rqt, "
                    "LabelImg, and image collection processes; retry with "
                    "--batch 1. If necessary, reduce --imgsz to 512. Keep "
                    "--amp true because disabling AMP usually uses more memory."
                ) from None
            raise
    finally:
        os.chdir(original_cwd)
    best_path = output_path / "weights/best.pt"
    if not best_path.is_file():
        raise SystemExit(f"Training ended without the expected model: {best_path}")
    print(f"Training completed: {best_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
