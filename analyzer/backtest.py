"""Backtest réaliste des signaux : spread, sortie partielle à TP1, stop au BE, stop temporel."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .strategy import Analyzer


@dataclass
class Trade:
    time: pd.Timestamp
    side: str
    score: float
    pattern: str
    result_r: float
    exit: str


def run_backtest(df: pd.DataFrame, cfg, spread_pips: float = 0.8, max_bars: int = 48) -> tuple[pd.DataFrame, dict]:
    an = Analyzer(df, cfg)
    h, l, c, n = an.h, an.l, an.c, len(an.c)
    spread = spread_pips * cfg.pip
    trades: list[Trade] = []
    busy_until, last_sig = -1, {1: -10**9, -1: -10**9}

    for i in range(an.warmup, n - 1):
        if i <= busy_until:
            continue
        sig = an.evaluate(i)
        if sig is None or i - last_sig[sig.direction] < cfg.strategy.cooldown_bars:
            continue
        last_sig[sig.direction] = i
        d = sig.direction
        entry = sig.entry + d * spread          # on paie le spread à l'entrée
        risk = abs(entry - sig.sl)
        sl, half_done, r_total, exit_reason = sig.sl, False, 0.0, "temps"
        j = i + 1
        for j in range(i + 1, min(n, i + 1 + max_bars)):
            hit_sl = (l[j] <= sl) if d == 1 else (h[j] >= sl)
            hit_tp1 = (h[j] >= sig.tp1) if d == 1 else (l[j] <= sig.tp1)
            hit_tp2 = (h[j] >= sig.tp2) if d == 1 else (l[j] <= sig.tp2)
            if hit_sl:  # hypothèse prudente : le SL passe avant le TP dans la même bougie
                r_total += (0.5 if half_done else 1.0) * (sl - entry) * d / risk
                exit_reason = "BE" if half_done else "SL"
                break
            if not half_done and hit_tp1:
                r_total += 0.5 * (sig.tp1 - entry) * d / risk
                half_done, sl = True, entry
            if half_done and hit_tp2:
                r_total += 0.5 * (sig.tp2 - entry) * d / risk
                exit_reason = "TP2"
                break
        else:
            rest = 0.5 if half_done else 1.0
            r_total += rest * (c[j] - entry) * d / risk
        busy_until = j
        trades.append(Trade(sig.time, sig.side, sig.score, sig.pattern, round(r_total, 3), exit_reason))

    tdf = pd.DataFrame([t.__dict__ for t in trades])
    return tdf, summarize(tdf)


def summarize(tdf: pd.DataFrame) -> dict:
    if tdf.empty:
        return {"trades": 0}
    r = tdf["result_r"]
    eq = r.cumsum()
    wins, losses = r[r > 0], r[r <= 0]
    return {
        "trades": len(r),
        "win_rate_%": round(100 * len(wins) / len(r), 1),
        "total_R": round(r.sum(), 2),
        "expectancy_R": round(r.mean(), 3),
        "profit_factor": round(wins.sum() / abs(losses.sum()), 2) if losses.sum() else np.inf,
        "max_drawdown_R": round((eq.cummax() - eq).max(), 2),
        "by_exit": tdf["exit"].value_counts().to_dict(),
    }
