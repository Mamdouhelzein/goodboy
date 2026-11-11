"""Small, dependency-free text tools: tokenizer, BM25 and TF-IDF.

Used identically at training time and at runtime, so the trained model
always sees features computed the same way.
"""
from __future__ import annotations

import math
import re
from collections import Counter

STOP = set("""a an and are as at be by can could do does for from get got help how i i'm im in into is
it its me my of on or our please some that the their them then there these this those to us use using
want wanna what when where which who why will with would you your need needs just like make some
any all also than so if not no yes hey hi ok okay""".split())

_WORD = re.compile(r"[a-z0-9]+(?:\+\+|#)?")


def stem(w: str) -> str:
    for suf in ("ization", "ations", "ation", "ings", "ing", "ers", "ies", "es", "ed", "er", "s"):
        if len(w) > len(suf) + 2 and w.endswith(suf):
            return w[: -len(suf)] + ("y" if suf == "ies" else "")
    return w


def tokens(text: str, keep_stop: bool = False) -> list[str]:
    out = []
    for w in _WORD.findall(text.lower()):
        if not keep_stop and w in STOP:
            continue
        out.append(stem(w))
    return out


def char_grams(toks: list[str], n: int = 3) -> list[str]:
    grams = []
    for t in toks:
        t = f"#{t}#"
        grams.extend(t[i:i + n] for i in range(max(1, len(t) - n + 1)))
    return grams


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.4, b: float = 0.75):
        self.k1, self.b = k1, b
        self.tf = [Counter(d) for d in docs]
        self.len = [len(d) for d in docs]
        self.avg = (sum(self.len) / len(docs)) if docs and sum(self.len) else 1.0
        n = len(docs)
        df = Counter(t for d in self.tf for t in d)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, q: list[str]) -> list[float]:
        q = set(q)
        out = []
        for tf, ln in zip(self.tf, self.len):
            s = 0.0
            norm = self.k1 * (1 - self.b + self.b * ln / self.avg)
            for t in q:
                f = tf.get(t)
                if f:
                    s += self.idf[t] * f * (self.k1 + 1) / (f + norm)
            out.append(s)
        return out


class TfIdf:
    """Sparse TF-IDF vectors (dicts) with cosine similarity."""

    def __init__(self, docs: list[list[str]]):
        n = len(docs)
        df = Counter(t for d in docs for t in set(d))
        self.idf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items()}
        self.default_idf = math.log(1 + n) + 1
        self.vecs = [self.vec(d) for d in docs]

    def vec(self, toks: list[str]) -> dict[str, float]:
        tf = Counter(toks)
        v = {t: (1 + math.log(c)) * self.idf.get(t, self.default_idf) for t, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norm for t, x in v.items()}

    def cosines(self, q: list[str]) -> list[float]:
        qv = self.vec(q)
        return [sum(w * d.get(t, 0.0) for t, w in qv.items()) for d in self.vecs]
