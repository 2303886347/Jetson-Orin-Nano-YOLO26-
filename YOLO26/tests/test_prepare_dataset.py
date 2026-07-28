import importlib.util
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np
import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools/prepare_dataset.py"
SPEC = importlib.util.spec_from_file_location("prepare_dataset", MODULE_PATH)
prepare_dataset = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = prepare_dataset
SPEC.loader.exec_module(prepare_dataset)


def write_sample(dataset, index, class_name="target_a"):
    image_dir = dataset / "source/JPEGImages"
    xml_dir = dataset / "source/Annotations"
    image_dir.mkdir(parents=True, exist_ok=True)
    xml_dir.mkdir(parents=True, exist_ok=True)
    image_path = image_dir / f"image_{index}.jpg"
    cv2.imwrite(str(image_path), np.zeros((48, 64, 3), dtype=np.uint8) + index)
    root = ET.Element("annotation")
    ET.SubElement(root, "filename").text = image_path.name
    size = ET.SubElement(root, "size")
    ET.SubElement(size, "width").text = "64"
    ET.SubElement(size, "height").text = "48"
    ET.SubElement(size, "depth").text = "3"
    obj = ET.SubElement(root, "object")
    ET.SubElement(obj, "name").text = class_name
    box = ET.SubElement(obj, "bndbox")
    for name, value in (("xmin", 8), ("ymin", 6), ("xmax", 40), ("ymax", 30)):
        ET.SubElement(box, name).text = str(value)
    ET.ElementTree(root).write(xml_dir / f"image_{index}.xml", encoding="utf-8")


def test_split_allocation_is_8_1_1():
    assert prepare_dataset.allocate_counts(10, (0.8, 0.1, 0.1)) == [8, 1, 1]


def test_collect_and_generate_dataset(tmp_path):
    dataset = tmp_path / "dataset"
    (dataset / "source").mkdir(parents=True)
    (dataset / "source/classes.names").write_text("target_a\n", encoding="utf-8")
    for index in range(1, 11):
        write_sample(dataset, index)
    classes = prepare_dataset.load_classes(dataset / "source/classes.names")
    samples = prepare_dataset.collect_samples(dataset / "source", classes, False, False)
    splits = prepare_dataset.create_splits(
        samples, dataset / "source/ImageSets", (0.8, 0.1, 0.1), 42, False
    )
    prepare_dataset.generate_yolo_dataset(dataset, splits, classes, 42)
    assert [len(splits[name]) for name in prepare_dataset.SPLIT_NAMES] == [8, 1, 1]
    assert len(list((dataset / "yolo/labels/train").glob("*.txt"))) == 8
    label = next((dataset / "yolo/labels/train").glob("*.txt")).read_text()
    values = [float(value) for value in label.split()[1:]]
    assert all(0.0 <= value <= 1.0 for value in values)
    report = json.loads((dataset / "yolo/dataset_report.json").read_text())
    assert report["class_objects"]["train"] == {"target_a": 8}


def test_extend_splits_preserves_existing_assignments(tmp_path):
    dataset = tmp_path / "dataset"
    source = dataset / "source"
    source.mkdir(parents=True)
    (source / "classes.names").write_text("target_a\n", encoding="utf-8")
    for index in range(1, 11):
        write_sample(dataset, index)

    classes = prepare_dataset.load_classes(source / "classes.names")
    samples = prepare_dataset.collect_samples(source, classes, False, False)
    initial = prepare_dataset.create_splits(
        samples, source / "ImageSets", (0.8, 0.1, 0.1), 42, False
    )
    initial_assignment = {
        sample.stem: split
        for split, split_samples in initial.items()
        for sample in split_samples
    }

    for index in range(11, 21):
        write_sample(dataset, index)
    samples = prepare_dataset.collect_samples(source, classes, False, False)
    extended = prepare_dataset.create_splits(
        samples,
        source / "ImageSets",
        (0.8, 0.1, 0.1),
        42,
        False,
        True,
    )
    extended_assignment = {
        sample.stem: split
        for split, split_samples in extended.items()
        for sample in split_samples
    }

    assert [len(extended[name]) for name in prepare_dataset.SPLIT_NAMES] == [16, 2, 2]
    assert len(extended_assignment) == 20
    assert all(
        extended_assignment[stem] == split
        for stem, split in initial_assignment.items()
    )


def test_reuse_splits_rejects_new_samples(tmp_path):
    dataset = tmp_path / "dataset"
    source = dataset / "source"
    source.mkdir(parents=True)
    (source / "classes.names").write_text("target_a\n", encoding="utf-8")
    for index in range(1, 11):
        write_sample(dataset, index)

    classes = prepare_dataset.load_classes(source / "classes.names")
    samples = prepare_dataset.collect_samples(source, classes, False, False)
    prepare_dataset.create_splits(
        samples, source / "ImageSets", (0.8, 0.1, 0.1), 42, False
    )
    write_sample(dataset, 11)
    samples = prepare_dataset.collect_samples(source, classes, False, False)

    try:
        prepare_dataset.create_splits(
            samples, source / "ImageSets", (0.8, 0.1, 0.1), 42, True
        )
    except prepare_dataset.DatasetError as exc:
        assert "--extend-splits" in str(exc)
    else:
        raise AssertionError("reuse_splits accepted an unassigned new sample")


def test_multiple_classes_receive_stable_class_ids(tmp_path):
    dataset = tmp_path / "dataset"
    source = dataset / "source"
    source.mkdir(parents=True)
    (source / "classes.names").write_text("target_a\ntarget_b\n", encoding="utf-8")
    write_sample(dataset, 1, "target_a")
    write_sample(dataset, 2, "target_b")

    classes = prepare_dataset.load_classes(source / "classes.names")
    samples = prepare_dataset.collect_samples(source, classes, False, False)
    objects = {sample.stem: sample.objects[0] for sample in samples}

    assert objects["image_1"].class_id == 0
    assert objects["image_1"].class_name == "target_a"
    assert objects["image_2"].class_id == 1
    assert objects["image_2"].class_name == "target_b"


def test_unknown_class_is_rejected(tmp_path):
    dataset = tmp_path / "dataset"
    source = dataset / "source"
    source.mkdir(parents=True)
    (source / "classes.names").write_text("target_a\n", encoding="utf-8")
    write_sample(dataset, 1, "target_b")

    with pytest.raises(prepare_dataset.DatasetError, match="Unknown class"):
        prepare_dataset.collect_samples(source, ["target_a"], False, False)


def test_out_of_range_box_is_rejected(tmp_path):
    dataset = tmp_path / "dataset"
    source = dataset / "source"
    source.mkdir(parents=True)
    (source / "classes.names").write_text("target_a\n", encoding="utf-8")
    write_sample(dataset, 1)
    xml_path = source / "Annotations/image_1.xml"
    tree = ET.parse(xml_path)
    tree.getroot().find("object/bndbox/xmax").text = "100"
    tree.write(xml_path, encoding="utf-8")

    with pytest.raises(prepare_dataset.DatasetError, match="Out-of-range box"):
        prepare_dataset.collect_samples(source, ["target_a"], False, False)


def test_unannotated_negative_requires_explicit_opt_in(tmp_path):
    dataset = tmp_path / "dataset"
    source = dataset / "source"
    image_dir = source / "JPEGImages"
    annotation_dir = source / "Annotations"
    image_dir.mkdir(parents=True)
    annotation_dir.mkdir(parents=True)
    (source / "classes.names").write_text("target_a\n", encoding="utf-8")
    cv2.imwrite(
        str(image_dir / "negative.jpg"), np.zeros((48, 64, 3), dtype=np.uint8)
    )

    with pytest.raises(prepare_dataset.DatasetError, match="without XML"):
        prepare_dataset.collect_samples(source, ["target_a"], False, False)

    samples = prepare_dataset.collect_samples(source, ["target_a"], True, False)
    assert len(samples) == 1
    assert samples[0].objects == ()


def test_one_image_can_contain_multiple_classes(tmp_path):
    dataset = tmp_path / "dataset"
    source = dataset / "source"
    source.mkdir(parents=True)
    classes = ["target_a", "target_b"]
    (source / "classes.names").write_text("target_a\ntarget_b\n", encoding="utf-8")
    write_sample(dataset, 1, "target_a")
    xml_path = source / "Annotations/image_1.xml"
    tree = ET.parse(xml_path)
    obj = ET.SubElement(tree.getroot(), "object")
    ET.SubElement(obj, "name").text = "target_b"
    box = ET.SubElement(obj, "bndbox")
    for name, value in (("xmin", 16), ("ymin", 12), ("xmax", 56), ("ymax", 42)):
        ET.SubElement(box, name).text = str(value)
    tree.write(xml_path, encoding="utf-8")

    samples = prepare_dataset.collect_samples(source, classes, False, False)
    assert [obj.class_id for obj in samples[0].objects] == [0, 1]
    assert [obj.class_name for obj in samples[0].objects] == ["target_a", "target_b"]
