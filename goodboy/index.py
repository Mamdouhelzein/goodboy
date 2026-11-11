"""Discover SKILL.md folders, index their frontmatter, and search them."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path

import yaml

from . import config
from .repos import Source, SourceError, parse_source, sync

BODY_CHARS = 20_000
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}


@dataclass
class Skill:
    name: str
    description: str
    source: str     # source spec, e.g. "anthropics/skills"
    path: str       # absolute path of the skill folder in the local clone
    body: str = ""  # SKILL.md instructions (truncated), used by the router

    @property
    def id(self) -> str:
        return f"{self.source}:{self.name}"


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split a SKILL.md into (frontmatter dict, markdown body)."""
    if not text.startswith("---"):
        return {}, text
    m = re.match(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", text, re.S)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        meta = None
    if not isinstance(meta, dict):
        # Lenient fallback: many hand-written SKILL.md files have unquoted colons
        # in the description, which is invalid YAML. Read "key: value" lines directly.
        meta = {}
        for line in m.group(1).splitlines():
            k, sep, v = line.partition(":")
            if sep and k.strip() and not line.startswith((" ", "\t")):
                meta[k.strip()] = v.strip().strip("'\"")
    return meta, text[m.end():]


def _find_skill_files(base: Path):
    for p in base.rglob("*"):
        if any(part in SKIP_DIRS for part in p.relative_to(base).parts):
            continue
        if p.name.lower() == "skill.md" and p.is_file() and not p.is_symlink():
            yield p


def scan_source(src: Source, update: bool = False) -> list[Skill]:
    base = sync(src, update=update)
    skills = []
    for f in _find_skill_files(base):
        try:
            meta, body = parse_frontmatter(f.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        name = str(meta.get("name") or f.parent.name).strip()
        desc = " ".join(str(meta.get("description") or "").split())
        if name.lower() in {"template", "template-skill", "skill-name", "my-skill"} or desc.lower().startswith("replace with"):
            continue
        skills.append(Skill(name=name, description=desc, source=src.spec, path=str(f.parent),
                            body=body[:BODY_CHARS]))
    return skills


def build_index(sources: list[str], update: bool = False, log=print) -> list[Skill]:
    skills: list[Skill] = []
    for spec in sources:
        try:
            found = scan_source(parse_source(spec), update=update)
            log(f"  {spec}: {len(found)} skills")
            skills.extend(found)
        except SourceError as e:
            log(f"  {spec}: skipped ({e})")
    p = config.index_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"built": time.time(), "sources": sources,
                             "skills": [asdict(s) for s in skills]}, indent=1))
    return skills


def load_index(cfg: config.Config, refresh: bool = False, log=print) -> list[Skill]:
    p = config.index_path()
    if not refresh and p.exists():
        data = json.loads(p.read_text())
        fresh = time.time() - data.get("built", 0) < cfg.index_ttl_hours * 3600
        if fresh and data.get("sources") == cfg.sources:
            if all("body" in s for s in data["skills"]):
                return [Skill(**s) for s in data["skills"]]
    log("Indexing skill sources...")
    return build_index(cfg.sources, update=True, log=log)


# ---------------------------------------------------------------- search

def search(skills: list[Skill], query: str, k: int = 5) -> list[tuple[float, Skill]]:
    """Rank skills for a request with the trained router."""
    from .router import Router
    return Router(skills).rank(query, k=k)


def keyword_search(skills: list[Skill], query: str, k: int = 5) -> list[tuple[float, Skill]]:
    """v0.1 hand-written scorer, kept as the baseline the model is compared against."""
    from .text import tokens
    q = set(tokens(query))
    scored = []
    for s in skills:
        name_t = set(tokens(s.name.replace("-", " ")))
        desc_t = tokens(s.description)
        score = sum(4 * (t in name_t) + (t in desc_t) for t in q) + 3 * (s.name.lower() in query.lower())
        if score:
            scored.append((float(score), s))
    scored.sort(key=lambda x: (-x[0], x[1].name))
    return scored[:k]


def resolve(skills: list[Skill], name: str) -> Skill | None:
    """Find a skill by id ("source:name") or bare name."""
    name = name.strip()
    for s in skills:
        if s.id == name:
            return s
    matches = [s for s in skills if s.name.lower() == name.lower()]
    return matches[0] if matches else None
