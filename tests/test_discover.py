"""Discovery tests with a fake GitHub search and local git repos (no network)."""
import subprocess
from pathlib import Path

import pytest

from goodboy import discover as d
from goodboy.cli import main


def _repo(root: Path, name: str, skills: dict[str, str]) -> Path:
    repo = root / name.replace("/", "__")
    for sk, desc in skills.items():
        f = repo / "skills" / sk
        f.mkdir(parents=True)
        (f / "SKILL.md").write_text(f"---\nname: {sk}\ndescription: {desc}\n---\n# {sk}\n\n## Usage\n{desc}\n")
        (f / "helper.py").write_text("print('hi')\n")
    (repo / "README.md").write_text("big file not needed " * 100)
    for c in (["init", "-q"], ["add", "."], ["commit", "-qm", "x"]):
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *c], cwd=repo, check=True)
    return repo


@pytest.fixture
def fake_github(tmp_path, monkeypatch):
    monkeypatch.setenv("GOODBOY_HOME", str(tmp_path / "home"))
    repos = {
        "big/design-skills": (90000, {"ui-design": "Design beautiful UI, landing pages and web interfaces."}),
        "mid/landing": (20000, {"landing-page": "Build high converting landing page designs with sections and copy."}),
        "huge/unrelated": (300000, {"pdf-tools": "Merge and split PDF files."}),
        "small/design": (50, {"design-lite": "Small design helper for landing pages."}),
        "empty/none": (70000, {}),
    }
    paths = {n: _repo(tmp_path / "gh", n, sk) if sk else None for n, (_, sk) in repos.items()}
    empty = tmp_path / "gh" / "empty"
    empty.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=empty, check=True)
    paths["empty/none"] = empty
    monkeypatch.setattr(d, "clone_url", lambda full: f"file://{paths[full]}")
    calls = []

    def search(q, per_page=15):
        calls.append(q)
        return [d.Repo(n, s, "") for n, (s, _) in repos.items()]
    monkeypatch.setattr(d, "search_repos", search)
    return calls


def test_keywords():
    assert d.keywords("can you make me a design skill for my landing page") == ["design", "landing", "page"]
    assert d.keywords("hi") == []


def test_discover_picks_top_starred_relevant_repos(fake_github):
    kws, found = d.discover("design my landing page", top=3)
    names = [r.full_name for r, _, _ in found]
    assert "huge/unrelated" not in names          # most stars, but no matching skill
    assert "empty/none" not in names              # no SKILL.md at all
    assert names[:2] == ["big/design-skills", "mid/landing"]   # sorted by stars


def test_lazy_clone_downloads_only_skill_files(fake_github, tmp_path):
    _, found = d.discover("design my landing page", top=3)
    repo, skills, _ = found[0]
    root = Path(skills[0].path).parents[1]
    assert (Path(skills[0].path) / "SKILL.md").exists()
    assert not (root / "README.md").exists() and not (Path(skills[0].path) / "helper.py").exists()
    d.materialize(skills[0])
    assert (Path(skills[0].path) / "helper.py").exists()


def test_cli_fetch_from_github(fake_github, capsys):
    assert main(["fetch", "build", "a", "landing", "page", "design"]) == 0
    out = capsys.readouterr().out
    assert "Top" in out and "stars" in out and "Fetched:" in out and "landing-page" in out


def test_cli_get_remote(fake_github, capsys):
    assert main(["get", "mid/landing:landing-page"]) == 0
    assert "Fetched mid/landing:landing-page" in capsys.readouterr().out
