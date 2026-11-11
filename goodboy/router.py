"""goodboy's trained skill router.

For a request q and every indexed skill s, we compute a feature vector
f(q, s) (lexical matches between the request and the skill's name,
description and instructions). A small neural network trained on labelled
requests (see training/) turns f(q, s) into P(skill s is the one needed).

Because the network scores *how well a request matches a skill*, not
*which of N fixed skills*, it works on skills it never saw in training:
add any GitHub repo and it routes to those skills too.

Inference is plain numpy; weights live in router.json (no pickles).
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import numpy as np

from .text import BM25, TfIdf, char_grams, tokens

FEATURES = [
    "bm25_name", "bm25_desc", "bm25_body",
    "cos_name", "cos_desc", "cos_body",
    "ccos_name", "ccos_desc",
    "cov_name", "cov_desc", "cov_body",
    "name_in_query", "name_tok_frac",
    "rel_bm25_name", "rel_bm25_desc", "rel_bm25_body", "rel_cos_desc", "rel_cos_body", "rel_ccos_desc",
    "query_len",
    # query-level: how well does the request match *anything*? lets the model abstain
    "q_vocab_cov", "q_max_bm25_desc", "q_max_cov_desc", "gap_bm25_desc", "gap_cos_desc",
]


def _name_text(name: str) -> str:
    return re.sub(r"[-_]+", " ", name)


class FeatureIndex:
    """Pre-computes per-skill statistics so scoring a query is fast."""

    def __init__(self, skills):
        self.skills = list(skills)
        names = [tokens(_name_text(s.name), keep_stop=True) for s in self.skills]
        descs = [tokens(s.description) for s in self.skills]
        bodies = [tokens(getattr(s, "body", "") or "") for s in self.skills]
        self.name_sets = [set(t) for t in names]
        self.desc_sets = [set(t) for t in descs]
        self.body_sets = [set(t) for t in bodies]
        self.name_phrases = [_name_text(s.name).lower() for s in self.skills]
        self.bm_name, self.bm_desc, self.bm_body = BM25(names), BM25(descs), BM25(bodies)
        self.tf_name, self.tf_desc, self.tf_body = TfIdf(names), TfIdf(descs), TfIdf(bodies)
        self.ch_name = TfIdf([char_grams(t) for t in names])
        self.ch_desc = TfIdf([char_grams(t) for t in descs])
        self.vocab = set().union(*self.name_sets, *self.desc_sets) if self.skills else set()

    def features(self, query: str) -> np.ndarray:
        """Returns an (n_skills, n_features) matrix for this query."""
        q = tokens(query)
        qs = set(q)
        n = len(self.skills)
        if n == 0:
            return np.zeros((0, len(FEATURES)))
        cols = {
            "bm25_name": self.bm_name.scores(q), "bm25_desc": self.bm_desc.scores(q),
            "bm25_body": self.bm_body.scores(q),
            "cos_name": self.tf_name.cosines(q), "cos_desc": self.tf_desc.cosines(q),
            "cos_body": self.tf_body.cosines(q),
            "ccos_name": self.ch_name.cosines(char_grams(q)), "ccos_desc": self.ch_desc.cosines(char_grams(q)),
        }
        denom = max(len(qs), 1)
        cols["cov_name"] = [len(qs & s) / denom for s in self.name_sets]
        cols["cov_desc"] = [len(qs & s) / denom for s in self.desc_sets]
        cols["cov_body"] = [len(qs & s) / denom for s in self.body_sets]
        ql = " " + re.sub(r"[-_]+", " ", query.lower()) + " "
        cols["name_in_query"] = [float(f" {p} " in ql) for p in self.name_phrases]
        cols["name_tok_frac"] = [len(qs & s) / max(len(s), 1) for s in self.name_sets]
        for k in ("bm25_name", "bm25_desc", "bm25_body", "cos_desc", "cos_body", "ccos_desc"):
            m = max(cols[k]) or 1.0
            cols["rel_" + k] = [x / m for x in cols[k]]
        cols["query_len"] = [math.log1p(len(q))] * n
        cols["q_vocab_cov"] = [len(qs & self.vocab) / denom] * n
        cols["q_max_bm25_desc"] = [math.log1p(max(cols["bm25_desc"]))] * n
        cols["q_max_cov_desc"] = [max(cols["cov_desc"])] * n
        for k in ("bm25_desc", "cos_desc"):
            v = np.array(cols[k])
            srt = np.sort(v)[::-1]
            other = np.where(v == srt[0], srt[1] if n > 1 else 0.0, srt[0])
            cols["gap_" + k] = list(v - other)
        return np.array([cols[f] for f in FEATURES], dtype=float).T


@dataclass
class Model:
    mean: np.ndarray
    std: np.ndarray
    layers: list[tuple[np.ndarray, np.ndarray]]
    threshold: float
    meta: dict

    @classmethod
    def from_dict(cls, d: dict) -> "Model":
        if d.get("features") != FEATURES:
            raise ValueError("router.json was trained with different features; retrain it")
        layers = [(np.array(l["W"]), np.array(l["b"])) for l in d["layers"]]
        return cls(np.array(d["mean"]), np.array(d["std"]), layers, float(d["threshold"]), d.get("meta", {}))

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Model":
        if path:
            return cls.from_dict(json.loads(Path(path).read_text()))
        text = resources.files("goodboy").joinpath("router.json").read_text()
        return cls.from_dict(json.loads(text))

    def predict(self, X: np.ndarray) -> np.ndarray:
        h = (X - self.mean) / self.std
        for i, (W, b) in enumerate(self.layers):
            h = h @ W + b
            if i < len(self.layers) - 1:
                h = np.maximum(h, 0)
        return 1 / (1 + np.exp(-h[:, 0]))


class Router:
    def __init__(self, skills, model: Model | None = None):
        self.fx = FeatureIndex(skills)
        self.model = model or Model.load()

    def rank(self, query: str, k: int = 5):
        """[(probability, skill), ...] best first."""
        if not self.fx.skills or not tokens(query):
            return []
        p = self.model.predict(self.fx.features(query))
        order = np.argsort(-p)[:k]
        return [(float(p[i]), self.fx.skills[i]) for i in order]

    def route(self, query: str):
        """Best skill if the model is confident, else None."""
        ranked = self.rank(query, k=1)
        if ranked and ranked[0][0] >= self.model.threshold:
            return ranked[0]
        return None


# ---------------------------------------------------------------- sections

_HEAD = re.compile(r"^(#{1,4})\s+(.+?)\s*#*\s*$", re.M)


def split_sections(body: str) -> list[tuple[str, str]]:
    """[(heading, text)] for a markdown body; text before the first heading is 'Overview'."""
    parts, last, title = [], 0, "Overview"
    in_code = False
    for m in _HEAD.finditer(body):
        # skip '#' lines inside fenced code blocks
        in_code = body[:m.start()].count("```") % 2 == 1
        if in_code:
            continue
        parts.append((title, body[last:m.start()].strip()))
        title, last = m.group(2), m.end()
    parts.append((title, body[last:].strip()))
    return [(t, x) for t, x in parts if x]


def best_sections(body: str, query: str, k: int = 2) -> list[tuple[str, str]]:
    secs = split_sections(body)
    if len(secs) <= k:
        return secs
    q = tokens(query)
    bm = BM25([tokens(t + " " + t + " " + x) for t, x in secs])  # headings count double
    scores = bm.scores(q)
    top = sorted(range(len(secs)), key=lambda i: -scores[i])[:k]
    if not any(scores[i] > 0 for i in top):
        top = list(range(k))
    return [secs[i] for i in sorted(top)]
