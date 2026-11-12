"""Find skills on GitHub for a request: the top-starred repos that actually ship skills.

1. Turn the request into keywords and search GitHub for "<keywords> skill", sorted by stars.
2. Walk the results in star order. For each repo, do a *tree-only* clone (file names, no
   file contents) and check for SKILL.md files. Keep the first N repos that have them.
3. Pull only the SKILL.md files of those repos, so the router can rank them.
4. When a skill is picked, check out only that skill's folder.

GitHub search allows ~10 unauthenticated requests a minute; set GITHUB_TOKEN to raise
that. Results are cached for a day.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

from . import config
from .index import BODY_CHARS, Skill, parse_frontmatter
from .repos import SourceError, _git
from .text import STOP, tokens

API = "https://api.github.com/search/repositories"
CACHE_TTL = 24 * 3600
MAX_SKILLS_PER_REPO = 300
LAZY_MARKER = ".goodboy-lazy"

# words that say what you want done, not what it's about
GENERIC = set("""make create build write add do fix improve help want give show find set setup
up new my me code app file files project thing something tool tools skill skills agent claude
please better good best really way ways stuff analyze analyse review check explain run understand learn use""".split())


class DiscoveryError(RuntimeError):
    pass


@dataclass
class Repo:
    full_name: str
    stars: int
    description: str


def keywords(request: str, k: int = 3) -> list[str]:
    seen, out = set(), []
    for w in re.findall(r"[a-z0-9][a-z0-9+#.-]*", request.lower()):
        w = w.strip(".-")
        if len(w) < 2 or w in STOP or w in GENERIC or w in seen:
            continue
        seen.add(w)
        out.append(w)
    return out[:k]


# ---------------------------------------------------------------- GitHub search

def _cache_file() -> Path:
    return config.home_dir() / "discover-cache.json"


def _load_cache() -> dict:
    try:
        return json.loads(_cache_file().read_text())
    except (OSError, ValueError):
        return {}


def _save_cache(cache: dict) -> None:
    p = _cache_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cache))


def search_repos(query: str, per_page: int = 15) -> list[Repo]:
    cache = _load_cache()
    hit = cache.get("search:" + query)
    if hit and time.time() - hit["t"] < CACHE_TTL:
        return [Repo(**r) for r in hit["repos"]]
    url = API + "?" + urllib.parse.urlencode({"q": query, "sort": "stars", "order": "desc", "per_page": per_page})
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "goodboy"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            raise DiscoveryError("GitHub search rate limit hit. Wait a minute, or set GITHUB_TOKEN.") from e
        raise DiscoveryError(f"GitHub search failed: HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise DiscoveryError(f"Can't reach GitHub: {e.reason}") from e
    repos = [Repo(i["full_name"], int(i["stargazers_count"]), (i.get("description") or "")[:200])
             for i in data.get("items", []) if not i.get("archived")]
    cache["search:" + query] = {"t": time.time(), "repos": [asdict(r) for r in repos]}
    _save_cache(cache)
    return repos


def candidate_repos(request: str) -> tuple[list[str], list[Repo]]:
    """Candidate repos, most stars first: searches all keywords together, then each alone."""
    kws = keywords(request)
    if not kws:
        return kws, []
    queries = [" ".join(kws) + " skill"] + ([k + " skill" for k in kws] if len(kws) > 1 else [])
    seen, repos = set(), []
    for q in queries:
        for r in search_repos(q):
            if r.full_name not in seen:
                seen.add(r.full_name)
                repos.append(r)
    repos.sort(key=lambda r: -r.stars)
    return kws, repos


# ---------------------------------------------------------------- lazy clones

def clone_url(full_name: str) -> str:
    return f"https://github.com/{full_name}.git"


def _repo_dir(full_name: str) -> Path:
    return config.repos_dir() / ("gh__" + full_name.replace("/", "__"))


def _lazy_clone(full_name: str) -> Path:
    """Shallow, blob-less, no-checkout clone: only the file tree is downloaded."""
    root = _repo_dir(full_name)
    if (root / LAZY_MARKER).exists():
        return root
    if root.exists():
        import shutil
        shutil.rmtree(root)
    root.parent.mkdir(parents=True, exist_ok=True)
    _git("clone", "--depth", "1", "--filter=blob:none", "--no-checkout", "--quiet",
         clone_url(full_name), str(root))
    (root / LAZY_MARKER).write_text(full_name)
    return root


def _skill_paths(root: Path) -> list[str]:
    files = _git("ls-tree", "-r", "--name-only", "HEAD", cwd=root).splitlines()
    return [f for f in files if f.rsplit("/", 1)[-1].lower() == "skill.md"][:MAX_SKILLS_PER_REPO]


def scan_repo(repo: Repo) -> list[Skill]:
    """Skills in a repo (cached). Downloads only the SKILL.md files."""
    cache = _load_cache()
    hit = cache.get("repo:" + repo.full_name)
    if hit and time.time() - hit["t"] < CACHE_TTL and (_repo_dir(repo.full_name) / LAZY_MARKER).exists():
        return [Skill(**s) for s in hit["skills"]]
    root = _lazy_clone(repo.full_name)
    paths = _skill_paths(root)
    skills = []
    if paths:
        _git("checkout", "--quiet", "HEAD", "--", *paths, cwd=root)
        for rel in paths:
            f = root / rel
            if f.is_symlink() or not f.is_file():
                continue
            meta, body = parse_frontmatter(f.read_text(encoding="utf-8", errors="replace"))
            name = str(meta.get("name") or f.parent.name).strip()
            desc = " ".join(str(meta.get("description") or "").split())
            if not desc or desc.lower().startswith("replace with") or name.lower() in {"template", "template-skill"}:
                continue
            if any(x.name == name for x in skills):
                continue  # same skill vendored in several folders
            skills.append(Skill(name=name, description=desc, source=repo.full_name,
                                path=str(f.parent), body=body[:BODY_CHARS]))
    cache = _load_cache()
    cache["repo:" + repo.full_name] = {"t": time.time(), "skills": [asdict(s) for s in skills]}
    _save_cache(cache)
    return skills


def materialize(skill: Skill) -> None:
    """Check out the rest of a lazily-cloned skill's folder (scripts, references)."""
    folder = Path(skill.path)
    root = next((p for p in [folder, *folder.parents] if (p / LAZY_MARKER).exists()), None)
    if root is None:
        return
    rel = folder.relative_to(root).as_posix()
    _git("checkout", "--quiet", "HEAD", "--", rel if rel != "." else ".", cwd=root)


def discover(request: str, top: int = 3, max_checks: int = 12, min_coverage: float = 0.5, log=print):
    """Top-`top` repos by stars among those that actually have a skill relevant to the request.

    Returns (keywords, [(Repo, skills, best_probability)]).
    """
    from .router import Router

    kws, repos = candidate_repos(request)
    scanned = []
    for repo in repos[:max_checks]:
        try:
            skills = scan_repo(repo)
        except SourceError:
            continue  # empty or broken repo
        if skills:
            scanned.append((repo, skills))
    if not scanned:
        return kws, []
    # Rank every scanned skill together (the setting the model was trained for). A repo
    # "provides the skill" if one of its skills is in the overall top 10 AND either the model
    # is confident about it or its name + description cover half the request's keywords.
    # (The model is great at picking *the* winner but squashes runner-ups, so its probability
    # alone can't say "this is also relevant".)
    router = Router([s for _, sk in scanned for s in sk])
    q = set(tokens(request))
    best: dict[str, float] = {}
    for p, s in router.rank(request, k=10):
        cover = len(q & set(tokens(s.name.replace("-", " ") + " " + s.description))) / max(len(q), 1)
        if p >= 0.5 or cover >= min_coverage:
            best[s.source] = max(best.get(s.source, 0.0), p)
    relevant = [(r, sk, best[r.full_name]) for r, sk in scanned if r.full_name in best]
    relevant.sort(key=lambda x: -x[0].stars)
    chosen = relevant[:top]
    # The repo holding the single best match always gets a slot, so popularity can't
    # push the right skill out; the remaining slots go to the most-starred matches.
    winner = max(relevant, key=lambda x: x[2], default=None)
    if winner and winner[2] >= 0.5 and winner not in chosen:
        chosen = sorted(chosen[: top - 1] + [winner], key=lambda x: -x[0].stars)
    return kws, chosen


def get_remote(skill_id: str) -> Skill | None:
    """Look up 'owner/repo:skill-name' directly on GitHub."""
    full_name, _, name = skill_id.partition(":")
    if full_name.count("/") != 1 or not name:
        return None
    skills = scan_repo(Repo(full_name, 0, ""))
    return next((s for s in skills if s.name == name), None) or \
        next((s for s in skills if s.name.lower() == name.lower()), None)
