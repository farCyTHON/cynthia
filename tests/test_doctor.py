"""Tests for the `cynthia doctor` diagnostic report."""
from __future__ import annotations

import sqlite3

import pytest
from typer.testing import CliRunner

from cynthia import health
from cynthia.cli import app
from cynthia.git_observer import CommitInfo, GitInfo
from cynthia.health import (
    ActivityFacts,
    QualityFacts,
    RepositoryFacts,
    RiskFile,
    build_health_report,
    score_band,
    summarize,
)
from cynthia.storage import Storage
from cynthia.workspace import add_project, init_workspace

runner = CliRunner()


@pytest.fixture
def workspace_home(tmp_path, monkeypatch):
    home = tmp_path / "cynthia-home"
    monkeypatch.setenv("CYNTHIA_HOME", str(home))
    init_workspace("test")
    return home


@pytest.fixture
def sample_project(workspace_home, tmp_path):
    project_dir = tmp_path / "demo-app"
    (project_dir / "tests").mkdir(parents=True)
    (project_dir / "README.md").write_text("# Demo\n")
    (project_dir / "main.py").write_text("print('hi')\n# TODO: ship it\n")
    (project_dir / "tests" / "test_main.py").write_text("def test_ok(): assert True\n")
    return add_project(project_dir)


@pytest.fixture
def stub_git(monkeypatch):
    """Pin git facts so reports don't depend on the machine running the tests."""
    info = GitInfo(
        is_repo=True,
        branch="main",
        commit_count=12,
        contributors=2,
        latest_commit=CommitInfo(
            sha="a" * 40,
            short_sha="aaaaaaa",
            message="Add doctor",
            author="Fardin",
            authored_at=__import__("time").time() - 3600,
        ),
        commits_by_weekday={"Mon": 2, "Tue": 1, "Wed": 0, "Thu": 0, "Fri": 0, "Sat": 0, "Sun": 0},
    )
    monkeypatch.setattr(health, "read_git_info", lambda *a, **k: info)
    monkeypatch.setattr(health, "file_change_counts", lambda *a, **k: {})
    return info


def test_report_score_is_in_range_and_summary_is_written(sample_project, stub_git):
    report = build_health_report(sample_project.id)

    assert 0 <= report.score <= 100
    assert report.summary.strip() != ""
    assert report.band in ("green", "yellow", "red")
    assert report.project_name == sample_project.name
    assert report.file_count > 0


def test_report_collects_repository_and_quality_facts(sample_project, stub_git):
    report = build_health_report(sample_project.id)

    assert report.repository.branch == "main"
    assert report.repository.commit_count == 12
    assert report.repository.contributors == 2
    assert report.repository.last_commit_age is not None
    assert report.quality.todo_count == 1
    assert report.quality.fixme_count == 0
    assert report.quality.has_readme is True
    assert report.quality.has_tests is True
    assert report.activity.commits == 3  # summed from the 7-day weekday buckets


def test_risk_files_come_from_the_event_log(sample_project, stub_git):
    hot = sample_project.path + "/src/auth/login.py"
    warm = sample_project.path + "/src/util.py"
    with Storage() as db:
        for _ in range(6):
            db.log_event(sample_project.id, "file_modified", {"path": hot})
        for _ in range(2):
            db.log_event(sample_project.id, "file_modified", {"path": warm})
        db.log_event(sample_project.id, "commit_observed", {"sha": "abc1234"})

    report = build_health_report(sample_project.id)

    assert [r.path for r in report.risks] == ["src/auth/login.py", "src/util.py"]
    assert report.risks[0].changes == 6
    assert report.activity.most_modified_file == "src/auth/login.py"
    assert report.activity.files_changed == 2  # unique paths, not raw event count
    assert "watcher events" in report.risk_source


def test_risk_list_is_capped_at_five(sample_project, stub_git):
    with Storage() as db:
        for i in range(8):
            db.log_event(sample_project.id, "file_created", {"path": f"{sample_project.path}/f{i}.py"})

    report = build_health_report(sample_project.id)
    assert len(report.risks) == health.MAX_RISK_FILES


def test_missing_git_repo_is_reported_not_raised(sample_project, monkeypatch):
    monkeypatch.setattr(
        health, "read_git_info", lambda *a, **k: GitInfo(is_repo=False, git_available=False)
    )
    report = build_health_report(sample_project.id)

    assert report.repository.is_repo is False
    assert any("git is not installed" in w for w in report.warnings)
    assert "Git is not installed" in report.summary


def test_empty_project_is_handled(workspace_home, tmp_path, stub_git):
    empty_dir = tmp_path / "hollow"
    empty_dir.mkdir()
    project = add_project(empty_dir)

    report = build_health_report(project.id)

    assert 0 <= report.score <= 100
    assert report.file_count == 0
    assert "empty" in report.summary
    assert any("no files" in w for w in report.warnings)


def test_deleted_project_path_is_reported(workspace_home, tmp_path, stub_git):
    gone = tmp_path / "vanished"
    gone.mkdir()
    (gone / "main.py").write_text("x = 1\n")
    project = add_project(gone)
    (gone / "main.py").unlink()
    gone.rmdir()

    report = build_health_report(project.id)
    assert any("no longer exists" in w for w in report.warnings)


def test_unreadable_event_log_degrades_gracefully(sample_project, stub_git, monkeypatch):
    def boom(*args, **kwargs):
        raise sqlite3.DatabaseError("database disk image is malformed")

    monkeypatch.setattr(Storage, "recent_events", boom)

    report = build_health_report(sample_project.id)
    assert any("event history unavailable" in w for w in report.warnings)
    assert 0 <= report.score <= 100


def test_unknown_project_id_raises(workspace_home):
    with pytest.raises(health.UnknownProject):
        build_health_report(4242)


def test_score_band_thresholds():
    assert score_band(100) == "green"
    assert score_band(90) == "green"
    assert score_band(89) == "yellow"
    assert score_band(70) == "yellow"
    assert score_band(69) == "red"
    assert score_band(0) == "red"


def _facts(**overrides):
    base = dict(
        band="green",
        file_count=20,
        quality=QualityFacts(has_readme=True, has_tests=True),
        repository=RepositoryFacts(git_available=True, is_repo=True, commit_count=10),
        activity=ActivityFacts(files_changed=4, commits=2),
        risks=[],
    )
    base.update(overrides)
    return base


def test_summary_calls_out_missing_tests():
    summary = summarize(
        **_facts(band="yellow", quality=QualityFacts(has_readme=True, has_tests=False))
    )
    assert summary.startswith("Project is stable but has missing tests.")


def test_summary_names_the_churn_topic():
    summary = summarize(**_facts(risks=[RiskFile("src/auth/login.py", 9)]))
    assert "Project is healthy and actively maintained." in summary
    assert "high churn in authentication-related files" in summary


def test_summary_flags_a_quiet_project():
    summary = summarize(**_facts(activity=ActivityFacts(files_changed=0, commits=0)))
    assert "quiet" in summary
    assert "No commits landed" in summary


def test_summary_lists_every_gap_when_unhealthy():
    summary = summarize(
        **_facts(band="red", quality=QualityFacts(has_readme=False, has_tests=False))
    )
    assert "missing tests and a README" in summary


def test_doctor_command_runs_without_exception(sample_project, stub_git):
    result = runner.invoke(app, ["doctor", sample_project.name])

    assert result.exit_code == 0, result.output
    assert sample_project.name in result.output
    assert "HEALTH" in result.output
    assert "SUMMARY" in result.output


def test_doctor_falls_back_to_most_recent_project(sample_project, stub_git):
    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0, result.output
    assert sample_project.name in result.output


def test_doctor_reports_unknown_project_cleanly(sample_project):
    result = runner.invoke(app, ["doctor", "no-such-project"])

    assert result.exit_code == 1
    assert "No project named" in result.output
