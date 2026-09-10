from cynthia.scanner import scan_project


def test_scan_counts_files_and_languages(tmp_path):
    (tmp_path / "main.py").write_text("print('hi')\n")
    (tmp_path / "README.md").write_text("# Hello\n")
    (tmp_path / "notes.txt").write_text("misc\n")

    result = scan_project(tmp_path)

    assert result.file_count == 3
    assert result.has_readme is True
    assert result.has_tests is False
    langs = dict(result.language_breakdown)
    assert "Python" in langs
    assert "Markdown" in langs


def test_scan_detects_todos_and_tests_dir(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_thing.py").write_text("def test_x():\n    assert True\n")
    (tmp_path / "app.py").write_text("# TODO: refactor this\nprint(1)\n")

    result = scan_project(tmp_path)

    assert result.has_tests is True
    assert len(result.todos) == 1
    assert result.todos[0].tag == "TODO"


def test_scan_detects_python_project_kind(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    (tmp_path / "main.py").write_text("print(1)\n")

    result = scan_project(tmp_path)

    assert result.kind == "python"


def test_human_size_formats_reasonably(tmp_path):
    (tmp_path / "big.py").write_text("x = 1\n" * 200)
    result = scan_project(tmp_path)
    assert result.human_size.endswith("B")
