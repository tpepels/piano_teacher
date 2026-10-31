"""Fast installer checks. No network, compiler, or Godot process required."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "install-inprocess-artifact.py"
spec = importlib.util.spec_from_file_location("install_inprocess_artifact", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def _archive(path: Path, *, revision="a" * 40, abi="3.14") -> Path:
    with ZipFile(path, "w", ZIP_DEFLATED) as f:
        f.writestr(module.BINARY, b"ELF placeholder, not executable")
        f.writestr(module.MANIFEST, b"[configuration]\n")
        f.writestr(module.ABI, abi + "\n")
        f.writestr(module.REVISION, revision + "\n")
    return path


def test_matching_archive_installs_only_expected_files(tmp_path):
    archive = _archive(tmp_path / "native.zip")
    destination = tmp_path / "checkout"
    paths = module.install(archive, root=destination,
                           local_revision="a" * 40,
                           python_abi="3.14", architecture="x86_64")
    assert len(paths) == 4
    assert (destination / module.BINARY).read_bytes().startswith(b"ELF")
    assert (destination / module.ABI).read_text().strip() == "3.14"


@pytest.mark.parametrize("revision,abi,architecture", [
    ("b" * 40, "3.14", "x86_64"),
    ("a" * 40, "3.13", "x86_64"),
    ("a" * 40, "3.14", "aarch64"),
])
def test_incompatible_archive_never_creates_binaries(tmp_path, revision, abi, architecture):
    archive = _archive(tmp_path / "native.zip")
    dest = tmp_path / "checkout"
    with pytest.raises(ValueError):
        module.install(archive, root=dest, local_revision=revision,
                       python_abi=abi, architecture=architecture)
    assert not (dest / module.BINARY).exists()


def test_partial_archive_rejected(tmp_path):
    archive = tmp_path / "native.zip"
    with ZipFile(archive, "w") as f:
        f.writestr(module.BINARY, b"wrong")
    with pytest.raises(ValueError, match="missing"):
        module.install(archive, root=tmp_path / "checkout",
                       local_revision="a" * 40, python_abi="3.14",
                       architecture="x86_64")


def test_zip_parent_path_rejected(tmp_path):
    archive = _archive(tmp_path / "native.zip")
    with ZipFile(archive, "a") as f:
        f.writestr("../oops", b"no")
    with pytest.raises(ValueError, match="Unsafe"):
        module.install(archive, root=tmp_path / "checkout",
                       local_revision="a" * 40, python_abi="3.14",
                       architecture="x86_64")
