import importlib.util
import sys
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools/create_dataset.py"
SPEC = importlib.util.spec_from_file_location("create_dataset", MODULE_PATH)
create_dataset = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = create_dataset
SPEC.loader.exec_module(create_dataset)


def test_create_single_and_multi_class_datasets(tmp_path):
    single = create_dataset.create_dataset(tmp_path, "single_task", ["target_a"])
    multi = create_dataset.create_dataset(
        tmp_path, "multi_task", ["target_a", "target_b"]
    )

    assert (single / "source/classes.names").read_text() == "target_a\n"
    assert (multi / "source/classes.names").read_text() == "target_a\ntarget_b\n"
    for directory in ("JPEGImages", "Annotations", "ImageSets"):
        assert (multi / "source" / directory).is_dir()


@pytest.mark.parametrize("name", ["Uppercase", "has space", "../outside", ""])
def test_rejects_invalid_dataset_names(tmp_path, name):
    with pytest.raises(create_dataset.DatasetInitError):
        create_dataset.create_dataset(tmp_path, name, ["target_a"])


def test_rejects_duplicate_classes_and_existing_dataset(tmp_path):
    with pytest.raises(create_dataset.DatasetInitError, match="Duplicate"):
        create_dataset.create_dataset(tmp_path, "my_dataset", ["target_a", "target_a"])

    create_dataset.create_dataset(tmp_path, "my_dataset", ["target_a"])
    with pytest.raises(create_dataset.DatasetInitError, match="already exists"):
        create_dataset.create_dataset(tmp_path, "my_dataset", ["target_b"])


def test_add_classes_preserves_existing_ids(tmp_path):
    dataset = create_dataset.create_dataset(tmp_path, "my_dataset", ["target_a"])
    create_dataset.add_classes(tmp_path, "my_dataset", ["target_b", "target_c"])

    assert (dataset / "source/classes.names").read_text() == (
        "target_a\ntarget_b\ntarget_c\n"
    )
    with pytest.raises(create_dataset.DatasetInitError, match="already exist"):
        create_dataset.add_classes(tmp_path, "my_dataset", ["target_b"])
