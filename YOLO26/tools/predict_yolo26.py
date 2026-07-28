#!/usr/bin/env python3
"""Run saved-image/video inference with a PT or TensorRT YOLO26 model."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run YOLO26 prediction")
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--project", type=Path, default=PROJECT_ROOT / "runs/predict")
    parser.add_argument("--name", default="predict")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", default="0")
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--iou", type=float, default=0.45)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    model_path = args.model.expanduser().resolve()
    source_path = args.source.expanduser().resolve()
    project_path = args.project.expanduser().resolve()
    output_path = project_path / args.name
    if model_path.suffix.lower() not in {".pt", ".engine"} or not model_path.is_file():
        raise SystemExit(f"Model must be an existing .pt or .engine file: {model_path}")
    if not source_path.exists():
        raise SystemExit(f"Prediction source does not exist: {source_path}")
    if output_path.exists():
        if not args.overwrite:
            raise SystemExit(
                f"Prediction output already exists: {output_path}. "
                "Choose another --name or pass --overwrite."
            )
        shutil.rmtree(output_path)

    from ultralytics import YOLO

    model = YOLO(str(model_path), task="detect")
    results = model.predict(
        source=str(source_path),
        imgsz=args.imgsz,
        device=args.device,
        conf=args.conf,
        iou=args.iou,
        project=str(project_path),
        name=args.name,
        exist_ok=True,
        save=True,
        show=False,
        verbose=False,
    )
    if not results:
        raise SystemExit("Prediction returned no results")
    print(f"Prediction completed: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
