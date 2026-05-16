"""Tests for forge.py — parser, semver, markdown, idempotency."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "forge.py"
sys.path.insert(0, str(ROOT / "scripts"))

from forge import (  # type: ignore  # noqa: E402
    CONVENTIONAL_TYPES,
    bump_version,
    build_report,
    group_commits,
    parse_commit,
    render_markdown,
    suggested_bump,
    write_changelog,
)


def _git(repo: Path, *args: str) -> None:
    env = os.environ.copy()
    env.update({
        "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@pluginpool.local",
        "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@pluginpool.local",
    })
    subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@pluginpool.local")
    _git(repo, "config", "user.name", "Test")
    return repo


def _commit(repo: Path, subject: str, body: str = "") -> None:
    p = repo / "f"
    p.write_text((p.read_text() if p.exists() else "") + subject + "\n")
    _git(repo, "add", "-A")
    args = ["commit", "-q", "-m", subject]
    if body:
        args += ["-m", body]
    _git(repo, *args)


def test_parses_all_conventional_types():
    for t in CONVENTIONAL_TYPES:
        c = parse_commit("abc1234", f"{t}: do thing", "")
        assert c["type"] == t
        assert c["breaking"] is False


def test_detects_bang_breaking():
    c = parse_commit("abc1234", "feat!: rip out api", "")
    assert c["breaking"] is True


def test_detects_breaking_change_in_body():
    c = parse_commit("abc1234", "feat: new", "BREAKING CHANGE: old api removed")
    assert c["breaking"] is True


def test_scope_captured():
    c = parse_commit("abc1234", "fix(auth): correct cookie path", "")
    assert c["scope"] == "auth"
    assert c["type"] == "fix"
    assert c["subject"] == "correct cookie path"


def test_non_conventional_falls_into_other():
    c = parse_commit("abc1234", "tweaked something", "")
    assert c["type"] == "other"


def test_suggested_bump_major_minor_patch():
    feat = [parse_commit("h", "feat: x", "")]
    fix = [parse_commit("h", "fix: x", "")]
    brk = [parse_commit("h", "feat!: x", "")]
    chore = [parse_commit("h", "chore: x", "")]
    assert suggested_bump(brk) == "major"
    assert suggested_bump(feat) == "minor"
    assert suggested_bump(fix) == "patch"
    assert suggested_bump(chore) == "patch"


def test_bump_version_math():
    assert bump_version("1.2.3", "major") == "2.0.0"
    assert bump_version("1.2.3", "minor") == "1.3.0"
    assert bump_version("1.2.3", "patch") == "1.2.4"
    assert bump_version("v0.1.0", "minor") == "0.2.0"


def test_render_markdown_groups_by_type():
    commits = [
        parse_commit("a1b2c3d", "feat(api): add endpoint", ""),
        parse_commit("e4f5g6h", "fix: handle nil", ""),
        parse_commit("9876543", "feat!: drop legacy", ""),
    ]
    report = {
        "sections": group_commits(commits),
        "suggested_bump": "major",
        "suggested_version": "2.0.0",
    }
    md = render_markdown(report)
    assert "### Features" in md
    assert "### Bug Fixes" in md
    assert "**api**: add endpoint" in md
    assert "⚠ BREAKING" in md
    assert "**major**" in md


def test_end_to_end_with_temp_repo(tmp_path):
    repo = _init_repo(tmp_path)
    _commit(repo, "feat: alpha")
    _git(repo, "tag", "v0.1.0")
    _commit(repo, "fix(auth): correct cookie path")
    _commit(repo, "feat!: drop /v0 endpoints", "BREAKING CHANGE: gone")
    report = build_report(str(repo), "v0.1.0", "HEAD")
    assert report["suggested_bump"] == "major"
    assert report["suggested_version"] == "1.0.0"
    assert len(report["breaking_changes"]) == 1
    subjects = [c["subject"] for c in report["commits"]]
    assert "correct cookie path" in subjects
    assert "drop /v0 endpoints" in subjects


def test_write_changelog_idempotent(tmp_path):
    section = "## [Unreleased] - 2026-05-16\n\n### Features\n- alpha (abc1234)\n\n_Suggested bump: **minor**_\n"
    path = tmp_path / "CHANGELOG.md"
    write_changelog(str(path), section)
    first = path.read_text()
    write_changelog(str(path), section)
    second = path.read_text()
    assert first == second
    assert first.count("## [Unreleased]") == 1


def test_write_changelog_replaces_existing_unreleased(tmp_path):
    path = tmp_path / "CHANGELOG.md"
    path.write_text(
        "# Changelog\n\n"
        "## [Unreleased] - 2026-05-15\n\n### Features\n- old (000)\n\n"
        "## [v0.1.0] - 2026-05-10\n\nfrozen\n"
    )
    new_section = "## [Unreleased] - 2026-05-16\n\n### Bug Fixes\n- newer (abc1234)\n\n"
    write_changelog(str(path), new_section)
    text = path.read_text()
    assert "old (000)" not in text
    assert "newer (abc1234)" in text
    assert "## [v0.1.0]" in text


def test_help_works():
    r = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True)
    assert r.returncode == 0
    assert "changelog" in r.stdout.lower()


def test_write_changelog_inserts_after_leading_title(tmp_path):
    """When CHANGELOG.md has `# Changelog` title but no `[Unreleased]` block yet,
    the new section must land AFTER the title, not above it."""
    path = tmp_path / "CHANGELOG.md"
    path.write_text("# Changelog\n\nAll notable changes follow Keep-a-Changelog.\n\n## [1.0.0] - 2025-01-01\n\n- initial\n")
    section = "## [Unreleased] - 2026-05-16\n\n### Bug Fixes\n- urgent (abc1234)\n\n"
    write_changelog(str(path), section)
    text = path.read_text()
    assert text.startswith("# Changelog\n"), text[:80]
    title_idx = text.index("# Changelog")
    unreleased_idx = text.index("## [Unreleased]")
    v1_idx = text.index("## [1.0.0]")
    assert title_idx < unreleased_idx < v1_idx
