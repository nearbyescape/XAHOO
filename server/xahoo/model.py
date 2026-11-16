"""Model artifacts and prediction.

models/
  manifest.json            version, feature list, per-horizon files, calibration maps, skill table
  {family}_dir_{h}.txt     direction classifier (LightGBM), family = coin | metal
  {family}_q68_{h}.txt     68% quantile of |move| in volatility units
  {family}_q95_{h}.txt     95% quantile

A forecast for one market and horizon:
  p_up       calibrated probability that the mark price is higher at the end of the horizon
  band68/95  expected move size as a fraction of price (symmetric band)
  layers     how much each input layer pushes the probability up (+) or down (-), in log-odds
"""
from __future__ import annotations

import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from .features import HORIZONS

LAYERS = {"a": "trend", "b": "flow", "c": "positioning", "d": "leader", "e": "market"}
LAYER_OF = {"x": "a", "r": "a"}          # EMA structure and market state count towards the trend layer


def binned_isotonic(raw: np.ndarray, y: np.ndarray, bins: int = 30) -> dict:
    """Calibration map: equal-count bins of the raw score -> observed up-rate, made monotone. Binning keeps the
    ends of the map honest (each point is backed by thousands of samples)."""
    order = np.argsort(raw)
    xs, ys = [], []
    for chunk in np.array_split(order, bins):
        if len(chunk):
            xs.append(float(raw[chunk].mean()))
            ys.append(float(y[chunk].mean()))
    ys = np.array(ys)
    # pool adjacent violators
    w = np.ones(len(ys))
    i = 0
    xs_a, ys_a = list(xs), list(ys)
    w = list(w)
    while i < len(ys_a) - 1:
        if ys_a[i] > ys_a[i + 1] + 1e-12:
            tot = w[i] + w[i + 1]
            ys_a[i] = (ys_a[i] * w[i] + ys_a[i + 1] * w[i + 1]) / tot
            xs_a[i] = (xs_a[i] * w[i] + xs_a[i + 1] * w[i + 1]) / tot
            w[i] = tot
            del ys_a[i + 1], xs_a[i + 1], w[i + 1]
            i = max(i - 1, 0)
        else:
            i += 1
    return {"x": [round(v, 6) for v in xs_a], "y": [round(v, 5) for v in ys_a]}


def apply_cal(cal: dict, raw: np.ndarray) -> np.ndarray:
    return np.interp(raw, cal["x"], cal["y"])


def steady(prev: int, p: float, enter: float = 0.02, leave: float = 0.02) -> int:
    """Direction label with hysteresis: +1 UP / -1 DOWN / 0 NEUTRAL. A side starts when the probability is at least
    `enter` from 50% and is kept until it falls back within `leave`, so it doesn't flicker on tiny changes.
    The probability itself is never changed. research/headline_eval.py measures the bands."""
    d = p - 0.5
    if prev == 1:
        return -1 if d <= -enter else 1 if d >= leave else 0
    if prev == -1:
        return 1 if d >= enter else -1 if d <= -leave else 0
    return 1 if d >= enter else -1 if d <= -enter else 0


def headline(spec: dict | None, fc: dict) -> dict | None:
    """One overall direction: the equal-weight average of the listed timeframes' log-odds, calibrated to the outcome
    named in the spec (research/headline_eval.py). None unless every listed timeframe has a shown forecast."""
    if not spec or not all(fc.get(h, {}).get("show") for h in spec["horizons"]):
        return None
    ps = [min(max(fc[h]["p"], 1e-4), 1 - 1e-4) for h in spec["horizons"]]
    z = float(np.mean([np.log(p / (1 - p)) for p in ps]))
    p = float(np.clip(apply_cal(spec["calibration"], np.array([1 / (1 + np.exp(-z))]))[0], 0.01, 0.99))
    agree = sum(1 for q in ps if (q > 0.5) == (p > 0.5))
    return {"p": round(p, 4), "agree": agree, "of": len(ps), "target": spec.get("target", "1h"),
            "parts": {h: round(fc[h]["p"], 4) for h in spec["horizons"]}}


class Models:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.manifest = json.loads((self.path / "manifest.json").read_text())
        self.features: list[str] = self.manifest["features"]
        self.boosters: dict[str, lgb.Booster] = {}
        for fam, hz in self.manifest["families"].items():
            for h, files in hz.items():
                for kind, fn in files["files"].items():
                    if isinstance(fn, list):        # several models averaged (bagging)
                        self.boosters[f"{fam}/{h}/{kind}"] = [lgb.Booster(model_file=str(self.path / f)) for f in fn]
                    else:
                        self.boosters[f"{fam}/{h}/{kind}"] = lgb.Booster(model_file=str(self.path / fn))

    @property
    def all_features(self) -> list[str]:
        """Every input any model reads: the shared list plus horizon-specific extras (EMA / market state)."""
        cols = list(self.features)
        for hz in self.manifest["families"].values():
            for spec in hz.values():
                cols += [c for c in spec.get("features_dir") or [] if c not in cols]
        return cols

    @property
    def version(self) -> str:
        return self.manifest["version"]

    def skill(self, sym: str, h: str) -> dict:
        return self.manifest["skill"].get(sym, {}).get(h, {})

    def predict(self, feats: pd.DataFrame, families: list[str], syms: list[str] | None = None) -> list[dict]:
        """feats: one row per market (columns include self.features). families: 'coin' or 'metal' per row.
        Returns, per row, {horizon: {p, u68, u95, layers, has_dir}}. Without a direction model p is 0.5."""
        out = [dict() for _ in range(len(feats))]
        for fam in set(families):
            rows = [i for i, f in enumerate(families) if f == fam]
            sub = feats.iloc[rows]
            X = sub[self.features].to_numpy(dtype=np.float64)
            for h in HORIZONS:
                spec = self.manifest["families"][fam].get(h)
                if not spec:
                    continue
                q68 = np.maximum(self.boosters[f"{fam}/{h}/q68"].predict(X), 1e-6) * spec["q68_scale"]
                q95 = np.maximum(self.boosters[f"{fam}/{h}/q95"].predict(X), 1e-6) * spec["q95_scale"]
                q95 = np.maximum(q95, q68 * 1.2)
                b = self.boosters.get(f"{fam}/{h}/dir")
                if b is not None:
                    fcols = spec.get("features_dir") or self.features
                    Xd = sub[fcols].to_numpy(dtype=np.float64)
                    bs = b if isinstance(b, list) else [b]
                    raw = np.mean([x.predict(Xd) for x in bs], axis=0)
                    p = apply_cal(spec["calibration"], raw)
                    mc = spec.get("market_cal")
                    if mc and syms is not None:                     # per-market correction: sigmoid(a + b * logit(p))
                        for j, i in enumerate(rows):
                            if syms[i] in mc:
                                a, bb = mc[syms[i]]
                                q = min(max(p[j], 1e-4), 1 - 1e-4)
                                p[j] = 1 / (1 + np.exp(-(a + bb * np.log(q / (1 - q)))))
                    # per-feature log-odds contributions (+ bias), averaged over the models
                    contrib = np.mean([x.predict(Xd, pred_contrib=True) for x in bs], axis=0)
                    lidx = {g: [i for i, c in enumerate(fcols) if LAYER_OF.get(c[0], c[0]) == g and c[1] == "_"] for g in LAYERS}
                for j, i in enumerate(rows):
                    d = {"p": 0.5, "u68": float(q68[j]), "u95": float(q95[j]), "layers": {}, "top": [], "has_dir": b is not None}
                    if b is not None:
                        d["p"] = float(np.clip(p[j], 0.01, 0.99))
                        d["layers"] = {LAYERS[g]: float(contrib[j, idx].sum()) for g, idx in lidx.items() if idx}
                        cj = contrib[j, :-1]                            # last column is the bias
                        order = np.argsort(-np.abs(cj))[:10]
                        d["top"] = [(fcols[k], float(cj[k])) for k in order]
                    out[i][h] = d
        return out
