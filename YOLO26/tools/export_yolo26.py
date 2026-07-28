#!/usr/bin/env python3
"""Export a trained YOLO26 PT model and place the result predictably."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a YOLO26 model")
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--format", default="engine", choices=("engine", "onnx", "openvino"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", default="0")
    parser.add_argument(
        "--half", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    model_path = args.model.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    if model_path.suffix.lower() != ".pt" or not model_path.is_file():
        raise SystemExit(f"Export requires an existing .pt model: {model_path}")
    if output_path.exists():
        if not args.overwrite:
            raise SystemExit(f"Export output already exists: {output_path}")
        if output_path.is_dir():
            shutil.rmtree(output_path)
        else:
            output_path.unlink()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    from ultralytics import YOLO

    model = YOLO(str(model_path), task="detect")
    exported = Path(
        model.export(
            format=args.format,
            imgsz=args.imgsz,
            half=args.half,
            device=args.device,
        )
    ).resolve()
    if not exported.exists():
        raise SystemExit(f"Ultralytics reported an export path that does not exist: {exported}")
    if exported != output_path:
        shutil.move(str(exported), str(output_path))
    print(f"Export completed: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
