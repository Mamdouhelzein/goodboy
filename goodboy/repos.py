"""Fetch skill repositories from GitHub with shallow git clones.

Cloning (instead of calling the GitHub REST API per file) means one network
round-trip indexes a whole repo and there is no 60-requests/hour API limit.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import config

_GH_SHORT = re.compile(r"^(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)(?:/(?P<sub>[^@]+?))?(?:@(?P<ref>[\w./-]+))?$")


class SourceError(RuntimeError):
    pass


@dataclass(frozen=True)
class Source:
    spec: str            # what the user typed
    url: str | None      # git URL, or None for a local directory
    local: Path | None   # local directory source
    ref: str | None      # branch / tag
    subdir: str          # only index skills under this path

    @property
    def slug(self) -> str:
        s = re.sub(r"[^\w.-]+", "__", self.spec.strip("/"))
        return s[:120]

    @property
    def display(self) -> str:
        return self.spec


def parse_source(spec: str) -> Source:
    """Accepts owner/repo, owner/repo/subdir, owner/repo@ref, a git URL, or a local dir."""
    spec = spec.strip()
    expanded = Path(os.path.expanduser(spec))
    if expanded.is_dir():
        return Source(spec, None, expanded.resolve(), None, "")
    if spec.startswith(("https://", "http://", "git@", "ssh://", "file://")):
        url, _, ref = spec.partition("#")   # https://host/repo.git#branch
        return Source(spec, url, None, ref or None, "")
    m = _GH_SHORT.match(spec)
    if not m:
        raise SourceError(f"Don't understand source {spec!r}. Use owner/repo, a git URL, or a local folder.")
    url = f"https://github.com/{m['owner']}/{m['repo']}.git"
    return Source(spec, url, None, m["ref"], (m["sub"] or "").strip("/"))


def _git(*args: str, cwd: Path | None = None) -> str:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_LFS_SKIP_SMUDGE="1")
    try:
        out = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=600)
    except FileNotFoundError as e:
        raise SourceError("git is not installed (sudo apt install git)") from e
    if out.returncode != 0:
        raise SourceError(f"git {' '.join(args[:2])} failed: {out.stderr.strip()[:400]}")
    return out.stdout


def sync(src: Source, update: bool = False) -> Path:
    """Make sure the source is available locally; return its root directory."""
    if src.local is not None:
        root = src.local
    else:
        root = config.repos_dir() / src.slug
        if not (root / ".git").exists():
            if root.exists():
                shutil.rmtree(root)
            root.parent.mkdir(parents=True, exist_ok=True)
            args = ["clone", "--depth", "1", "--quiet"]
            if src.ref:
                args += ["--branch", src.ref]
            _git(*args, src.url, str(root))
        elif update:
            ref = src.ref or "HEAD"
            _git("fetch", "--depth", "1", "--quiet", "origin", ref, cwd=root)
            _git("reset", "--hard", "--quiet", "FETCH_HEAD", cwd=root)
    base = (root / src.subdir).resolve() if src.subdir else root
    if not base.is_dir():
        raise SourceError(f"{src.spec}: path {src.subdir!r} not found in repo")
    return base
