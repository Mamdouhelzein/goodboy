"""Copy a skill folder out of its repo into the local skills directory."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from . import config
from .index import Skill, parse_frontmatter

MAX_FILE_BYTES = 2_000_000
MAX_TOTAL_BYTES = 30_000_000


def install_dir_for(skill: Skill) -> Path:
    src = re.sub(r"[^\w.-]+", "__", skill.source.strip("/"))
    name = re.sub(r"[^\w.-]+", "-", skill.name)
    return config.installed_dir() / src / name


def install(skill: Skill) -> Path:
    """Copy regular files only: symlinks are skipped so a malicious repo can't
    point a 'skill file' at ~/.ssh or anything else outside the skill."""
    src = Path(skill.path).resolve()
    dest = install_dir_for(skill)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    total = 0
    for f in sorted(src.rglob("*")):
        rel = f.relative_to(src)
        if f.is_symlink() or ".git" in rel.parts or not f.is_file():
            continue
        if not f.resolve().is_relative_to(src):
            continue
        size = f.stat().st_size
        if size > MAX_FILE_BYTES or total + size > MAX_TOTAL_BYTES:
            continue
        total += size
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, out)
    return dest


def list_files(folder: Path) -> list[str]:
    return sorted(str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file())


def skill_body(folder: Path) -> str:
    for cand in ("SKILL.md", "skill.md", "Skill.md"):
        p = folder / cand
        if p.exists():
            return parse_frontmatter(p.read_text(encoding="utf-8", errors="replace"))[1].strip()
    return ""


def read_file(folder: Path, rel: str, limit: int = 12_000) -> str:
    target = (folder / rel).resolve()
    if not target.is_relative_to(folder.resolve()) or not target.is_file():
        raise FileNotFoundError(rel)
    data = target.read_bytes()
    if b"\0" in data[:4096]:
        return f"[binary file, {len(data)} bytes]"
    text = data.decode("utf-8", errors="replace")
    return text if len(text) <= limit else text[:limit] + f"\n... [truncated, {len(text)} chars total]"


def installed() -> list[Path]:
    root = config.installed_dir()
    return sorted(p.parent for p in root.glob("*/*/SKILL.md")) if root.exists() else []
