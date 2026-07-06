import pytest

from aves.scaffold import scaffold_project


def test_scaffold_project_copies_template_files(tmp_path):
    destdir = tmp_path / "new_project"
    copied = scaffold_project(destdir=str(destdir))

    assert set(copied) == {"simple_demo.ino", "config.toml"}
    for name in copied:
        assert (destdir / name).is_file()


def test_scaffold_project_creates_destdir(tmp_path):
    destdir = tmp_path / "does" / "not" / "exist" / "yet"
    scaffold_project(destdir=str(destdir))
    assert destdir.is_dir()


def test_scaffold_project_refuses_to_overwrite_existing_files(tmp_path):
    destdir = tmp_path / "new_project"
    destdir.mkdir()
    (destdir / "config.toml").write_text("pretend this is my own file\n")

    with pytest.raises(FileExistsError, match="config.toml"):
        scaffold_project(destdir=str(destdir))

    # Nothing should have been copied: the pre-existing file untouched,
    # and the other template file not copied either (all-or-nothing).
    assert (destdir / "config.toml").read_text() == "pretend this is my own file\n"
    assert not (destdir / "simple_demo.ino").exists()
