import pytest

from aves.scaffold import scaffold_project


def test_scaffold_project_copies_template_files(tmp_path):
    destdir = tmp_path / "new_project"
    copied = scaffold_project(destdir=str(destdir), template="simple_demo")

    assert set(copied) == {"simple_demo.ino", "config.yaml"}
    for name in copied:
        assert (destdir / name).is_file()


def test_scaffold_project_creates_destdir(tmp_path):
    destdir = tmp_path / "does" / "not" / "exist" / "yet"
    scaffold_project(destdir=str(destdir), template="simple_demo")
    assert destdir.is_dir()


def test_scaffold_project_rejects_unknown_template(tmp_path):
    with pytest.raises(ValueError, match="not a valid template"):
        scaffold_project(destdir=str(tmp_path), template="does-not-exist")


def test_scaffold_project_refuses_to_overwrite_existing_files(tmp_path):
    destdir = tmp_path / "new_project"
    destdir.mkdir()
    (destdir / "config.yaml").write_text("pretend this is my own file\n")

    with pytest.raises(FileExistsError, match="config.yaml"):
        scaffold_project(destdir=str(destdir), template="simple_demo")

    # Nothing should have been copied: the pre-existing file untouched,
    # and the other template file not copied either (all-or-nothing).
    assert (destdir / "config.yaml").read_text() == "pretend this is my own file\n"
    assert not (destdir / "simple_demo.ino").exists()
