#!/usr/bin/env python3
"""Validate Pascal VOC data and build a portable Ultralytics dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import shutil
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import cv2


IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff")
SPLIT_NAMES = ("train", "val", "test")


class DatasetError(RuntimeError):
    pass


@dataclass(frozen=True)
class YoloObject:
    class_id: int
    class_name: str
    x_center: float
    y_center: float
    width: float
    height: float


@dataclass(frozen=True)
class Sample:
    stem: str
    image_path: Path
    annotation_path: Path | None
    objects: tuple[YoloObject, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Pascal VOC XML and generate YOLO train/val/test data."
    )
    parser.add_argument("--dataset", required=True, type=Path, help="Dataset root")
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    split_mode = parser.add_mutually_exclusive_group()
    split_mode.add_argument(
        "--reuse-splits",
        action="store_true",
        help="Reuse source/ImageSets/*.txt; every current sample must already be listed",
    )
    split_mode.add_argument(
        "--extend-splits",
        action="store_true",
        help="Keep existing split assignments and assign only newly added samples",
    )
    parser.add_argument(
        "--allow-unannotated-negatives",
        action="store_true",
        help="Treat images without XML files as explicit negative samples",
    )
    parser.add_argument(
        "--normalize-xml-paths",
        action="store_true",
        help="Remove stale optional <path> elements from source XML files",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_classes(path: Path) -> list[str]:
    if not path.is_file():
        raise DatasetError(f"Missing class list: {path}")
    classes = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    classes = [name for name in classes if name]
    if not classes:
        raise DatasetError(f"No classes are defined in {path}")
    if len(classes) != len(set(classes)):
        raise DatasetError(f"Duplicate class names are not allowed in {path}")
    return classes


def index_images(directory: Path) -> dict[str, Path]:
    if not directory.is_dir():
        raise DatasetError(f"Missing image directory: {directory}")
    images: dict[str, Path] = {}
    seen_lower: set[str] = set()
    for path in sorted(directory.iterdir()):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        key = path.stem
        lowered = key.lower()
        if key in images or lowered in seen_lower:
            raise DatasetError(f"Duplicate image basename: {key}")
        images[key] = path
        seen_lower.add(lowered)
    if not images:
        raise DatasetError(f"No supported images found in {directory}")

    hashes: dict[str, Path] = {}
    for path in images.values():
        digest = sha256_file(path)
        if digest in hashes:
            raise DatasetError(
                f"Duplicate image content: {hashes[digest].name} and {path.name}"
            )
        hashes[digest] = path
    return images


def index_annotations(directory: Path) -> dict[str, Path]:
    if not directory.is_dir():
        raise DatasetError(f"Missing annotation directory: {directory}")
    annotations: dict[str, Path] = {}
    seen_lower: set[str] = set()
    for path in sorted(directory.glob("*.xml")):
        key = path.stem
        lowered = key.lower()
        if key in annotations or lowered in seen_lower:
            raise DatasetError(f"Duplicate XML basename: {key}")
        annotations[key] = path
        seen_lower.add(lowered)
    return annotations


def required_text(root: ET.Element, xpath: str, xml_path: Path) -> str:
    value = root.findtext(xpath)
    if value is None or not value.strip():
        raise DatasetError(f"Missing {xpath!r} in {xml_path}")
    return value.strip()


def parse_box(
    obj: ET.Element,
    width: int,
    height: int,
    class_ids: dict[str, int],
    xml_path: Path,
) -> YoloObject:
    class_name = required_text(obj, "name", xml_path)
    if class_name not in class_ids:
        raise DatasetError(
            f"Unknown class {class_name!r} in {xml_path}; update classes.names first"
        )
    box = obj.find("bndbox")
    if box is None:
        raise DatasetError(f"Only Pascal VOC bndbox annotations are supported: {xml_path}")
    try:
        xmin = float(required_text(box, "xmin", xml_path))
        ymin = float(required_text(box, "ymin", xml_path))
        xmax = float(required_text(box, "xmax", xml_path))
        ymax = float(required_text(box, "ymax", xml_path))
    except ValueError as exc:
        raise DatasetError(f"Non-numeric bounding box in {xml_path}") from exc

    if not (0 <= xmin < xmax <= width and 0 <= ymin < ymax <= height):
        raise DatasetError(
            f"Out-of-range box in {xml_path}: {(xmin, ymin, xmax, ymax)} "
            f"for image {width}x{height}"
        )
    return YoloObject(
        class_id=class_ids[class_name],
        class_name=class_name,
        x_center=(xmin + xmax) / (2.0 * width),
        y_center=(ymin + ymax) / (2.0 * height),
        width=(xmax - xmin) / width,
        height=(ymax - ymin) / height,
    )


def parse_annotation(
    xml_path: Path,
    image_path: Path,
    class_ids: dict[str, int],
    normalize_xml_paths: bool,
) -> tuple[YoloObject, ...]:
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError as exc:
        raise DatasetError(f"Invalid XML: {xml_path}: {exc}") from exc
    root = tree.getroot()

    filename = required_text(root, "filename", xml_path)
    if Path(filename).stem != image_path.stem:
        raise DatasetError(
            f"XML filename {filename!r} does not match image {image_path.name!r}"
        )

    frame = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
    if frame is None:
        raise DatasetError(f"OpenCV cannot read image: {image_path}")
    actual_height, actual_width = frame.shape[:2]
    try:
        xml_width = int(required_text(root, "size/width", xml_path))
        xml_height = int(required_text(root, "size/height", xml_path))
    except ValueError as exc:
        raise DatasetError(f"Invalid image size in {xml_path}") from exc
    if (xml_width, xml_height) != (actual_width, actual_height):
        raise DatasetError(
            f"Image/XML size mismatch for {image_path.name}: image "
            f"{actual_width}x{actual_height}, XML {xml_width}x{xml_height}"
        )

    objects = tuple(
        parse_box(obj, xml_width, xml_height, class_ids, xml_path)
        for obj in root.findall("object")
    )

    if normalize_xml_paths:
        changed = False
        for path_node in list(root.findall("path")):
            root.remove(path_node)
            changed = True
        if changed:
            ET.indent(tree, space="\t")
            tree.write(xml_path, encoding="utf-8", xml_declaration=False)
    return objects


def collect_samples(
    source_dir: Path,
    classes: list[str],
    allow_unannotated_negatives: bool,
    normalize_xml_paths: bool,
) -> list[Sample]:
    images = index_images(source_dir / "JPEGImages")
    annotations = index_annotations(source_dir / "Annotations")
    extra_xml = sorted(set(annotations) - set(images))
    if extra_xml:
        raise DatasetError(f"XML files without matching images: {', '.join(extra_xml)}")
    missing_xml = sorted(set(images) - set(annotations))
    if missing_xml and not allow_unannotated_negatives:
        raise DatasetError(
            "Images without XML annotations: "
            + ", ".join(missing_xml)
            + ". Pass --allow-unannotated-negatives only after confirming they are negatives."
        )

    class_ids = {name: index for index, name in enumerate(classes)}
    samples: list[Sample] = []
    for stem, image_path in sorted(images.items()):
        annotation_path = annotations.get(stem)
        objects: tuple[YoloObject, ...] = ()
        if annotation_path is not None:
            objects = parse_annotation(
                annotation_path,
                image_path,
                class_ids,
                normalize_xml_paths,
            )
        samples.append(Sample(stem, image_path, annotation_path, objects))
    return samples


def allocate_counts(total: int, ratios: tuple[float, float, float]) -> list[int]:
    if any(ratio < 0 for ratio in ratios) or not math.isclose(sum(ratios), 1.0, abs_tol=1e-9):
        raise DatasetError("Train, validation, and test ratios must be non-negative and sum to 1")
    active = [index for index, ratio in enumerate(ratios) if ratio > 0]
    if total < len(active):
        raise DatasetError("There are not enough samples to populate every requested split")

    raw = [total * ratio for ratio in ratios]
    counts = [math.floor(value) for value in raw]
    for index in active:
        if counts[index] == 0:
            counts[index] = 1
    while sum(counts) > total:
        candidates = [i for i in active if counts[i] > 1]
        if not candidates:
            raise DatasetError("Unable to allocate the requested split ratios")
        index = min(candidates, key=lambda i: raw[i] - counts[i])
        counts[index] -= 1
    while sum(counts) < total:
        index = max(range(3), key=lambda i: (raw[i] - counts[i], ratios[i]))
        counts[index] += 1
    return counts


def read_split_file(path: Path) -> list[str]:
    if not path.is_file():
        raise DatasetError(f"Missing split file: {path}")
    values = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if value:
            values.append(Path(value).stem)
    return values


def create_splits(
    samples: list[Sample],
    image_sets: Path,
    ratios: tuple[float, float, float],
    seed: int,
    reuse_splits: bool,
    extend_splits: bool = False,
) -> dict[str, list[Sample]]:
    by_stem = {sample.stem: sample for sample in samples}
    if reuse_splits or extend_splits:
        split_stems = {
            name: read_split_file(image_sets / f"{name}.txt") for name in SPLIT_NAMES
        }
        flattened = [stem for values in split_stems.values() for stem in values]
        if len(flattened) != len(set(flattened)):
            raise DatasetError("A sample appears in more than one ImageSets split")
        listed = set(flattened)
        current = set(by_stem)
        unknown = sorted(listed - current)
        if unknown:
            raise DatasetError(
                "ImageSets reference samples that no longer exist: "
                + ", ".join(unknown)
            )
        new_stems = sorted(current - listed)
        if reuse_splits and new_stems:
            raise DatasetError(
                "ImageSets do not include newly added samples: "
                + ", ".join(new_stems)
                + ". Use --extend-splits to preserve old assignments and add them."
            )
        if extend_splits:
            target_counts = allocate_counts(len(samples), ratios)
            existing_counts = [len(split_stems[name]) for name in SPLIT_NAMES]
            oversized = [
                name
                for name, existing, target in zip(
                    SPLIT_NAMES, existing_counts, target_counts
                )
                if existing > target
            ]
            if oversized:
                raise DatasetError(
                    "Existing split assignments cannot be preserved with the requested "
                    "ratios; oversized splits: "
                    + ", ".join(oversized)
                    + ". Keep the previous ratios or regenerate all splits without "
                    "--extend-splits."
                )
            shuffled_new = list(new_stems)
            random.Random(seed).shuffle(shuffled_new)
            offset = 0
            for name, existing, target in zip(
                SPLIT_NAMES, existing_counts, target_counts
            ):
                add_count = target - existing
                split_stems[name].extend(shuffled_new[offset : offset + add_count])
                offset += add_count
            if offset != len(shuffled_new):
                raise DatasetError("Unable to assign every new sample to a split")
            image_sets.mkdir(parents=True, exist_ok=True)
            for name, stems in split_stems.items():
                (image_sets / f"{name}.txt").write_text(
                    "".join(f"{stem}\n" for stem in stems), encoding="utf-8"
                )
    else:
        shuffled = sorted(by_stem)
        random.Random(seed).shuffle(shuffled)
        train_count, val_count, test_count = allocate_counts(len(shuffled), ratios)
        split_stems = {
            "train": shuffled[:train_count],
            "val": shuffled[train_count : train_count + val_count],
            "test": shuffled[train_count + val_count : train_count + val_count + test_count],
        }
        image_sets.mkdir(parents=True, exist_ok=True)
        for name, stems in split_stems.items():
            (image_sets / f"{name}.txt").write_text(
                "".join(f"{stem}\n" for stem in stems), encoding="utf-8"
            )
    return {
        name: [by_stem[stem] for stem in split_stems[name]] for name in SPLIT_NAMES
    }


def write_yolo_label(path: Path, objects: tuple[YoloObject, ...]) -> None:
    lines = [
        f"{obj.class_id} {obj.x_center:.6f} {obj.y_center:.6f} "
        f"{obj.width:.6f} {obj.height:.6f}\n"
        for obj in objects
    ]
    path.write_text("".join(lines), encoding="ascii")


def write_yaml(path: Path, classes: list[str], include_test: bool) -> None:
    lines = ["train: images/train\n", "val: images/val\n"]
    if include_test:
        lines.append("test: images/test\n")
    lines.append("names:\n")
    for index, name in enumerate(classes):
        lines.append(f"  {index}: {json.dumps(name, ensure_ascii=False)}\n")
    path.write_text("".join(lines), encoding="utf-8")


def class_object_counts(
    samples: list[Sample], classes: list[str]
) -> dict[str, int]:
    counts = {name: 0 for name in classes}
    for sample in samples:
        for obj in sample.objects:
            counts[obj.class_name] += 1
    return counts


def generate_yolo_dataset(
    dataset_dir: Path,
    splits: dict[str, list[Sample]],
    classes: list[str],
    seed: int,
) -> None:
    output_dir = dataset_dir / "yolo"
    staging = dataset_dir / f".yolo-staging-{os.getpid()}"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        for split_name, samples in splits.items():
            image_dir = staging / "images" / split_name
            label_dir = staging / "labels" / split_name
            image_dir.mkdir(parents=True, exist_ok=True)
            label_dir.mkdir(parents=True, exist_ok=True)
            for sample in samples:
                shutil.copy2(sample.image_path, image_dir / sample.image_path.name)
                write_yolo_label(label_dir / f"{sample.stem}.txt", sample.objects)
        write_yaml(staging / "data.yaml", classes, bool(splits["test"]))
        report = {
            "seed": seed,
            "classes": classes,
            "splits": {name: len(samples) for name, samples in splits.items()},
            "objects": {
                name: sum(len(sample.objects) for sample in samples)
                for name, samples in splits.items()
            },
            "class_objects": {
                name: class_object_counts(samples, classes)
                for name, samples in splits.items()
            },
        }
        (staging / "dataset_report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        if output_dir.exists():
            shutil.rmtree(output_dir)
        staging.rename(output_dir)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main() -> int:
    args = parse_args()
    dataset_dir = args.dataset.expanduser().resolve()
    source_dir = dataset_dir / "source"
    try:
        classes = load_classes(source_dir / "classes.names")
        samples = collect_samples(
            source_dir,
            classes,
            args.allow_unannotated_negatives,
            args.normalize_xml_paths,
        )
        ratios = (args.train_ratio, args.val_ratio, args.test_ratio)
        splits = create_splits(
            samples,
            source_dir / "ImageSets",
            ratios,
            args.seed,
            args.reuse_splits,
            args.extend_splits,
        )
        train_class_counts = class_object_counts(splits["train"], classes)
        missing_train_classes = [
            name for name, count in train_class_counts.items() if count == 0
        ]
        if missing_train_classes:
            raise DatasetError(
                "Training split has no objects for declared classes: "
                + ", ".join(missing_train_classes)
                + ". Add labeled samples or adjust source/ImageSets before training."
            )
        generate_yolo_dataset(dataset_dir, splits, classes, args.seed)
    except DatasetError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Dataset prepared: {dataset_dir / 'yolo'}")
    print("Classes: " + ", ".join(classes))
    print(
        "Split: "
        + ", ".join(f"{name}={len(splits[name])}" for name in SPLIT_NAMES)
    )
    split_mode = (
        "extended"
        if args.extend_splits
        else "reused" if args.reuse_splits else "regenerated"
    )
    print(f"Split mode: {split_mode}")
    for name in SPLIT_NAMES:
        counts = class_object_counts(splits[name], classes)
        print(
            f"Class objects ({name}): "
            + ", ".join(f"{class_name}={count}" for class_name, count in counts.items())
        )
        missing = [class_name for class_name, count in counts.items() if count == 0]
        if name != "train" and missing:
            print(
                f"WARNING: {name} split cannot evaluate classes without objects: "
                + ", ".join(missing),
                file=sys.stderr,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
