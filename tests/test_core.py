import subprocess
from pathlib import Path

import numpy as np
import pytest

from goodboy import config
from goodboy import index as idx
from goodboy.cli import main
from goodboy.install import install, read_file
from goodboy.router import FEATURES, FeatureIndex, Model, Router, best_sections, split_sections

TRAINING_SKILLS = Path(__file__).resolve().parents[1] / "skills"


def _make_repo(root: Path) -> Path:
    repo = root / "skills-repo"
    (repo / "skills" / "pdf").mkdir(parents=True)
    (repo / "skills" / "pdf" / "SKILL.md").write_text(
        "---\nname: pdf\ndescription: Extract text and tables from PDF files, merge or split PDFs.\n---\n"
        "# PDF\nIntro.\n\n## Merging\nUse pypdf PdfWriter to merge files.\n\n## Tables\nUse pdfplumber.\n\n"
        "## Forms\nFill fields.\n")
    (repo / "skills" / "pdf" / "reference.md").write_text("pypdf.PdfReader(path)")
    (repo / "skills" / "pdf" / "evil").symlink_to("/etc/passwd")
    (repo / "template").mkdir()
    (repo / "template" / "SKILL.md").write_text("---\nname: template-skill\ndescription: Replace with x\n---\n")
    for c in (["init", "-q"], ["add", "."], ["commit", "-qm", "init"]):
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *c], cwd=repo, check=True)
    return repo


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("GOODBOY_HOME", str(tmp_path / "home"))
    repo = _make_repo(tmp_path)
    cfg = config.Config(sources=[f"file://{repo}", str(TRAINING_SKILLS)])
    cfg.save()
    return cfg, idx.load_index(cfg, log=lambda m: None)


def test_index_skips_templates_and_keeps_body(env):
    _, skills = env
    names = {s.name for s in skills}
    assert "pdf" in names and "nmap-triage" in names and "template-skill" not in names
    assert "pypdf" in idx.resolve(skills, "pdf").body


def test_shipped_model_loads_and_matches_features():
    m = Model.load()
    assert len(m.mean) == len(FEATURES) and 0 < m.threshold < 1


@pytest.mark.parametrize("request_, want", [
    ("merge two pdf files", "pdf"),
    ("which open ports in my nmap scan are dangerous", "nmap-triage"),
    ("i pushed my aws key to github by accident", "secrets-scanning"),
    ("undo my last commit", "git-workflow"),
])
def test_router_routes(env, request_, want):
    _, skills = env
    p, s = Router(skills).rank(request_, k=1)[0]
    assert s.name == want


def test_router_abstains_on_small_talk(env):
    _, skills = env
    assert Router(skills).route("hi how are you") is None


def test_features_shape(env):
    _, skills = env
    X = FeatureIndex(skills).features("merge pdfs")
    assert X.shape == (len(skills), len(FEATURES)) and np.isfinite(X).all()


def test_sections():
    body = "Intro\n\n## Merging\nmerge with pypdf\n\n```\n# not a heading\n```\n\n## Tables\npdfplumber tables\n\n## Other\nx"
    titles = [t for t, _ in split_sections(body)]
    assert titles == ["Overview", "Merging", "Tables", "Other"]
    assert [t for t, _ in best_sections(body, "extract tables", k=1)] == ["Tables"]


def test_install_skips_symlinks_and_traversal(env):
    _, skills = env
    dest = install(idx.resolve(skills, "pdf"))
    assert (dest / "SKILL.md").exists() and not (dest / "evil").exists()
    with pytest.raises(FileNotFoundError):
        read_file(dest, "../../../../etc/passwd")


def test_cli_fetch(env, capsys):
    assert main(["fetch", "--local", "merge", "these", "pdf", "files"]) == 0
    out = capsys.readouterr().out
    assert "Fetched:" in out and ":pdf" in out and "## Merging" in out
    assert main(["fetch", "--local", "tell me a joke"]) == 0
    assert "Nothing to fetch" in capsys.readouterr().out
