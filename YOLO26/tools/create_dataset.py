#!/usr/bin/env python3
"""Create a generic YOLO26 dataset workspace or append new classes."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class DatasetInitError(RuntimeError):
    """Raised when a dataset cannot be created or updated safely."""


def validate_dataset_name(name: str) -> str:
    if not DATASET_NAME_PATTERN.fullmatch(name):
        raise DatasetInitError(
            "Dataset names must start with a lowercase letter or digit and contain "
            "only lowercase letters, digits, underscores, and hyphens."
        )
    return name


def validate_classes(class_names: Sequence[str]) -> list[str]:
    normalized: list[str] = []
    for class_name in class_names:
        value = class_name.strip()
        if not value:
            raise DatasetInitError("Class names cannot be empty.")
        if "\n" in value or "\r" in value:
            raise DatasetInitError("Class names cannot contain line breaks.")
        normalized.append(value)
    duplicates = sorted({name for name in normalized if normalized.count(name) > 1})
    if duplicates:
        raise DatasetInitError(f"Duplicate class names: {', '.join(duplicates)}")
    return normalized


def read_classes(classes_path: Path) -> list[str]:
    if not classes_path.is_file():
        raise DatasetInitError(f"Missing classes file: {classes_path}")
    classes = [line.strip() for line in classes_path.read_text(encoding="utf-8").splitlines()]
    return validate_classes([name for name in classes if name])


def create_dataset(datasets_root: Path, name: str, class_names: Sequence[str]) -> Path:
    validate_dataset_name(name)
    classes = validate_classes(class_names)
    dataset_dir = datasets_root.expanduser().resolve() / name
    if dataset_dir.exists():
        raise DatasetInitError(f"Dataset already exists: {dataset_dir}")

    source_dir = dataset_dir / "source"
    for directory in ("JPEGImages", "Annotations", "ImageSets"):
        (source_dir / directory).mkdir(parents=True, exist_ok=False)
    (source_dir / "classes.names").write_text(
        "".join(f"{class_name}\n" for class_name in classes), encoding="utf-8"
    )
    return dataset_dir


def add_classes(datasets_root: Path, name: str, class_names: Sequence[str]) -> Path:
    validate_dataset_name(name)
    additions = validate_classes(class_names)
    dataset_dir = datasets_root.expanduser().resolve() / name
    if not dataset_dir.is_dir():
        raise DatasetInitError(f"Dataset does not exist: {dataset_dir}")

    classes_path = dataset_dir / "source/classes.names"
    existing = read_classes(classes_path)
    duplicates = sorted(set(existing).intersection(additions))
    if duplicates:
        raise DatasetInitError(
            f"Classes already exist and keep their current IDs: {', '.join(duplicates)}"
        )
    classes_path.write_text(
        "".join(f"{class_name}\n" for class_name in [*existing, *additions]),
        encoding="utf-8",
    )
    return dataset_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a YOLO26 dataset workspace or append classes"
    )
    parser.add_argument("--name", required=True, help="Dataset directory name")
    parser.add_argument(
        "--datasets-root",
        type=Path,
        default=PROJECT_ROOT / "datasets",
        help="Parent directory for datasets",
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument(
        "--classes",
        nargs="+",
        help="Create a dataset with one or more ordered class names",
    )
    action.add_argument(
        "--add-classes",
        nargs="+",
        help="Append classes without changing existing class IDs",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.classes is not None:
            dataset_dir = create_dataset(args.datasets_root, args.name, args.classes)
            action = "Created dataset"
        else:
            dataset_dir = add_classes(args.datasets_root, args.name, args.add_classes)
            action = "Updated dataset"
    except DatasetInitError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc

    classes_path = dataset_dir / "source/classes.names"
    print(f"{action}: {dataset_dir}")
    print(f"Classes: {classes_path}")
    for class_id, class_name in enumerate(read_classes(classes_path)):
        print(f"  {class_id}: {class_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
