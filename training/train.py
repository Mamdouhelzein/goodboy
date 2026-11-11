"""Train goodboy's skill router.

    pip install -e '.[train]'
    python training/train.py            # evaluates, then writes goodboy/router.json

The model scores (request, skill) pairs, so we evaluate it the honest way:
GroupKFold over *skills*. In every fold the test requests belong to skills
whose requests were never seen in training, which is exactly the situation
when you add a new GitHub repo of skills.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import yaml
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GOODBOY_HOME", str(HERE / ".cache"))

from goodboy import index as idx  # noqa: E402
from goodboy.repos import parse_source  # noqa: E402
from goodboy.router import FEATURES, FeatureIndex  # noqa: E402

SOURCES = ["anthropics/skills", str(ROOT / "skills")]  # local copy of our own skills
POS_WEIGHT = 15  # each request has 1 right skill and ~38 wrong ones
SEED = 7


def load_skills():
    skills = []
    for spec in SOURCES:
        found = idx.scan_source(parse_source(spec))
        print(f"  {spec}: {len(found)} skills")
        skills += found
    return skills


def load_queries(names):
    data = yaml.safe_load((HERE / "data" / "queries.yaml").read_text())
    pairs = []
    for label, qs in data.items():
        if label != "_none" and label not in names:
            raise SystemExit(f"queries.yaml: unknown skill {label!r}")
        pairs += [(q, None if label == "_none" else label) for q in qs]
    return pairs


def make_xy(fx, names, pairs):
    Xs, ys, groups = [], [], []
    for qi, (q, label) in enumerate(pairs):
        X = fx.features(q)
        y = np.array([n == label for n in names], dtype=int)
        Xs.append(X), ys.append(y), groups.append(np.full(len(names), qi))
    return Xs, ys


class Scaler:
    def fit(self, X):
        self.mean, self.std = X.mean(0), X.std(0) + 1e-6
        return self

    def __call__(self, X):
        return (X - self.mean) / self.std


def fit_model(kind, X, y):
    sc = Scaler().fit(X)
    w = np.where(y == 1, POS_WEIGHT, 1.0)
    if kind == "logreg":
        m = LogisticRegression(C=1.0, max_iter=2000)
        m.fit(sc(X), y, sample_weight=w)
    else:
        rep = np.concatenate([np.arange(len(y))] + [np.where(y == 1)[0]] * (POS_WEIGHT - 1))
        m = MLPClassifier(hidden_layer_sizes=(32, 16), alpha=1e-3, max_iter=600,
                          early_stopping=False, random_state=SEED)
        m.fit(sc(X[rep]), y[rep])
    return sc, m


def predict(sc, m, X):
    return m.predict_proba(sc(X))[:, 1]


def rank_metrics(scores_per_query, pairs, names):
    """top1/top3/MRR on requests that need a skill."""
    t1 = t3 = rr = n = 0
    for s, (_, label) in zip(scores_per_query, pairs):
        if label is None:
            continue
        order = list(np.argsort(-s))
        r = order.index(names.index(label)) + 1
        n += 1
        t1 += r == 1
        t3 += r <= 3
        rr += 1 / r
    return {"top1": t1 / n, "top3": t3 / n, "mrr": rr / n, "n": n}


def best_threshold(scores_per_query, pairs, names):
    """Pick the cut-off that maximises routing accuracy (right skill, or abstain on _none)."""
    best = (0.0, 0.5)
    for th in np.linspace(0.05, 0.95, 91):
        ok = 0
        for s, (_, label) in zip(scores_per_query, pairs):
            top = int(np.argmax(s))
            if label is None:
                ok += s[top] < th
            else:
                ok += s[top] >= th and names[top] == label
        acc = ok / len(pairs)
        if acc > best[0]:
            best = (acc, float(th))
    return best


def skill_folds(names, k=5):
    rng = np.random.default_rng(SEED)
    order = rng.permutation(len(names))
    return {names[i]: j % k for j, i in enumerate(order)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "goodboy" / "router.json"))
    ap.add_argument("--folds", type=int, default=5)
    args = ap.parse_args()

    print("Loading skills")
    skills = load_skills()
    names = [s.name for s in skills]
    pairs = load_queries(set(names))
    print(f"  {len(skills)} skills, {len(pairs)} labelled requests "
          f"({sum(l is None for _, l in pairs)} need no skill)")

    fx = FeatureIndex(skills)
    Xs, ys = make_xy(fx, names, pairs)

    # ---- cross-validation over held-out skills
    fold_of_skill = skill_folds(names, args.folds)
    none_i = 0
    qfold = []
    for _, label in pairs:
        if label is None:
            qfold.append(none_i % args.folds)
            none_i += 1
        else:
            qfold.append(fold_of_skill[label])
    qfold = np.array(qfold)

    results = {}
    oof = {}
    for kind in ("logreg", "mlp"):
        scores = [None] * len(pairs)
        for f in range(args.folds):
            tr = [i for i in range(len(pairs)) if qfold[i] != f]
            te = [i for i in range(len(pairs)) if qfold[i] == f]
            sc, m = fit_model(kind, np.vstack([Xs[i] for i in tr]), np.concatenate([ys[i] for i in tr]))
            for i in te:
                scores[i] = predict(sc, m, Xs[i])
        oof[kind] = scores
        results[kind] = rank_metrics(scores, pairs, names)

    # baselines: v0.1 keyword scorer and plain BM25 on descriptions
    by_name = {s.name: s for s in skills}
    kw = []
    for q, _ in pairs:
        hits = {s.name: sc for sc, s in idx.keyword_search(skills, q, k=len(skills))}
        kw.append(np.array([hits.get(n, 0.0) + 1e-9 * -i for i, n in enumerate(names)]))
    results["baseline_keyword_v0.1"] = rank_metrics(kw, pairs, names)
    bm = [X[:, FEATURES.index("bm25_desc")] + 1e-9 * -np.arange(len(names)) for X in Xs]
    results["baseline_bm25"] = rank_metrics(bm, pairs, names)

    print("\nHeld-out-skill evaluation (5-fold, skills unseen in training):")
    print(f"  {'model':24} {'top-1':>7} {'top-3':>7} {'MRR':>7}")
    for k, r in results.items():
        print(f"  {k:24} {r['top1']:7.1%} {r['top3']:7.1%} {r['mrr']:7.3f}")

    kind = max(("logreg", "mlp"), key=lambda k: (results[k]["top1"], results[k]["mrr"]))
    route_acc, th = best_threshold(oof[kind], pairs, names)
    print(f"\nChosen: {kind}. Confidence threshold {th:.2f} -> routing accuracy {route_acc:.1%} "
          f"(right skill, or 'no skill' for chit-chat)")

    # ---- final model on everything
    sc, m = fit_model(kind, np.vstack(Xs), np.concatenate(ys))
    if kind == "logreg":
        layers = [{"W": m.coef_.T.tolist(), "b": m.intercept_.tolist()}]
    else:
        layers = [{"W": W.tolist(), "b": b.tolist()} for W, b in zip(m.coefs_, m.intercepts_)]
    out = {
        "features": FEATURES, "mean": sc.mean.tolist(), "std": sc.std.tolist(),
        "layers": layers, "threshold": th,
        "meta": {"model": kind, "trained": time.strftime("%Y-%m-%d"), "skills": len(skills),
                 "requests": len(pairs), "cv": results, "routing_accuracy": route_acc},
    }
    Path(args.out).write_text(json.dumps(out, separators=(",", ":")))
    print(f"Wrote {args.out} ({Path(args.out).stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
