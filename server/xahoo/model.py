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

LAYERS = {"a": "trend", "b": "flow", "c": "positioning", "d": "leader"}


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


class Models:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.manifest = json.loads((self.path / "manifest.json").read_text())
        self.features: list[str] = self.manifest["features"]
        self.boosters: dict[str, lgb.Booster] = {}
        for fam, hz in self.manifest["families"].items():
            for h, files in hz.items():
                for kind, fn in files["files"].items():
                    self.boosters[f"{fam}/{h}/{kind}"] = lgb.Booster(model_file=str(self.path / fn))
        self._layer_idx = {g: [i for i, c in enumerate(self.features) if c.startswith(g + "_")] for g in LAYERS}

    @property
    def version(self) -> str:
        return self.manifest["version"]

    def skill(self, family: str, h: str) -> dict:
        return self.manifest["families"][family][h].get("skill", {})

    def predict(self, feats: pd.DataFrame, families: list[str]) -> list[dict]:
        """feats: one row per market (columns = self.features). families: 'coin' or 'metal' per row.
        Returns, per row, {horizon: {p, raw, band68, band95, layers}}."""
        X = feats[self.features].to_numpy(dtype=np.float64)
        out = [dict() for _ in range(len(X))]
        for fam in set(families):
            rows = [i for i, f in enumerate(families) if f == fam]
            if not rows:
                continue
            Xf = X[rows]
            for h in HORIZONS:
                spec = self.manifest["families"][fam].get(h)
                if not spec:
                    continue
                b = self.boosters[f"{fam}/{h}/dir"]
                raw = b.predict(Xf)
                p = apply_cal(spec["calibration"], raw)
                contrib = b.predict(Xf, pred_contrib=True)          # per-feature log-odds contributions (+ bias)
                q68 = np.maximum(self.boosters[f"{fam}/{h}/q68"].predict(Xf), 1e-6) * spec["q68_scale"]
                q95 = np.maximum(self.boosters[f"{fam}/{h}/q95"].predict(Xf), 1e-6) * spec["q95_scale"]
                q95 = np.maximum(q95, q68 * 1.2)
                for j, i in enumerate(rows):
                    out[i][h] = {
                        "p": float(np.clip(p[j], 0.01, 0.99)), "raw": float(raw[j]),
                        "u68": float(q68[j]), "u95": float(q95[j]),
                        "layers": {LAYERS[g]: float(contrib[j, idx].sum()) for g, idx in self._layer_idx.items()},
                    }
        return out
