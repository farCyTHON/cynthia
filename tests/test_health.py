from cynthia.git_observer import GitInfo
from cynthia.health import compute_health
from cynthia.scanner import scan_project


def _clean_git_info():
    return GitInfo(is_repo=True, branch="main", commit_count=10, contributors=1)


def test_healthy_project_scores_high(tmp_path):
    (tmp_path / "README.md").write_text("# Project\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("def test_x(): assert True\n")
    (tmp_path / "main.py").write_text("print('ok')\n")

    scan = scan_project(tmp_path)
    report = compute_health(tmp_path, scan, _clean_git_info())

    assert report.status == "healthy"
    assert report.score >= 80


def test_missing_readme_and_tests_lowers_score(tmp_path):
    (tmp_path / "main.py").write_text("print('ok')\n")

    scan = scan_project(tmp_path)
    report = compute_health(tmp_path, scan, _clean_git_info())

    assert report.score <= 80
    assert any("README" in r for r in report.reasons)
    assert any("tests" in r for r in report.reasons)


def test_many_todos_are_capped_not_unbounded(tmp_path):
    lines = "\n".join(f"# TODO: fix thing {i}" for i in range(100))
    (tmp_path / "messy.py").write_text(lines + "\n")

    scan = scan_project(tmp_path)
    report = compute_health(tmp_path, scan, GitInfo(is_repo=False))

    assert len(scan.todos) == 100
    assert report.score >= 0  # never goes negative even with heavy TODO burden


def test_no_coverage_report_is_reported_as_none(tmp_path):
    scan = scan_project(tmp_path)
    report = compute_health(tmp_path, scan, GitInfo(is_repo=False))
    assert report.test_coverage is None
