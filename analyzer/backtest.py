"""Simulation des trades (backtest et suivi en direct des signaux).

Règles : spread payé à l'entrée, 50 % fermé à TP1 puis stop au point d'entrée,
reste à TP2, sortie forcée après `max_hold_bars`. Si SL et TP sont touchés dans
la même bougie, on compte le SL (hypothèse prudente).
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .strategy import Analyzer, Signal


@dataclass
class Outcome:
    status: str          # "en cours" | "TP2" | "SL" | "BE" | "temps"
    result_r: float      # résultat en R (réalisé + latent si en cours)
    tp1_hit: bool
    exit_index: int | None
    exit_price: float | None


def simulate(an: Analyzer, sig: Signal, spread_pips: float, max_bars: int) -> Outcome:
    h, l, c, n = an.h, an.l, an.c, len(an.c)
    d = sig.direction
    entry = sig.entry + d * spread_pips * an.cfg.pip
    risk = max(abs(entry - sig.sl), 1e-9)
    sl, half, r = sig.sl, False, 0.0
    last = min(n, sig.index + 1 + max_bars)
    for j in range(sig.index + 1, last):
        if (l[j] <= sl) if d == 1 else (h[j] >= sl):
            r += (0.5 if half else 1.0) * (sl - entry) * d / risk
            return Outcome("BE" if half else "SL", round(r, 3), half, j, sl)
        if not half and ((h[j] >= sig.tp1) if d == 1 else (l[j] <= sig.tp1)):
            r += 0.5 * (sig.tp1 - entry) * d / risk
            half, sl = True, entry
        if half and ((h[j] >= sig.tp2) if d == 1 else (l[j] <= sig.tp2)):
            r += 0.5 * (sig.tp2 - entry) * d / risk
            return Outcome("TP2", round(r, 3), True, j, sig.tp2)
    j = last - 1
    rest = (0.5 if half else 1.0) * (c[j] - entry) * d / risk if j > sig.index else 0.0
    if last - sig.index - 1 >= max_bars:
        return Outcome("temps", round(r + rest, 3), half, j, float(c[j]))
    return Outcome("en cours", round(r + rest, 3), half, None, None)


def run_backtest(df: pd.DataFrame, cfg) -> dict:
    """Backtest complet : un seul trade à la fois, délai entre signaux respecté."""
    an = Analyzer(df, cfg)
    s = cfg.strategy
    rows, busy_until = [], -1
    for sig in an.scan():
        if sig.index <= busy_until:
            continue
        out = simulate(an, sig, s.spread_pips, s.max_hold_bars)
        if out.status == "en cours":
            break
        busy_until = out.exit_index
        rows.append({
            "time": sig.close_time.isoformat(), "side": sig.side, "pattern": sig.pattern,
            "score": sig.score, "quality": sig.quality, "entry": sig.entry, "sl": sig.sl,
            "tp1": sig.tp1, "tp2": sig.tp2, "exit": out.status, "result_r": out.result_r,
            "hour": sig.close_time.hour,
        })
    trades = pd.DataFrame(rows)
    return {
        "period": {"start": df.index[0].isoformat(), "end": df.index[-1].isoformat(), "bars": len(df)},
        "stats": summarize(trades),
        "equity": _equity(trades),
        "by_pattern": _group(trades, "pattern"),
        "by_quality": _group(trades, "quality"),
        "by_hour": _group(trades, "hour"),
        "trades": rows[::-1],
    }


def summarize(t: pd.DataFrame) -> dict:
    if t.empty:
        return {"trades": 0}
    r = t["result_r"]
    eq = r.cumsum()
    wins, losses = r[r > 0], r[r <= 0]
    streak = max_streak = 0
    for v in r:
        streak = streak + 1 if v < 0 else 0
        max_streak = max(max_streak, streak)
    return {
        "trades": int(len(r)),
        "win_rate": round(100 * len(wins) / len(r), 1),
        "total_r": round(float(r.sum()), 2),
        "expectancy_r": round(float(r.mean()), 3),
        "profit_factor": round(float(wins.sum() / abs(losses.sum())), 2) if losses.sum() else None,
        "max_drawdown_r": round(float((eq.cummax() - eq).max()), 2),
        "avg_win_r": round(float(wins.mean()), 2) if len(wins) else 0,
        "avg_loss_r": round(float(losses.mean()), 2) if len(losses) else 0,
        "max_losing_streak": int(max_streak),
        "exits": {k: int(v) for k, v in t["exit"].value_counts().items()},
    }


def _equity(t: pd.DataFrame) -> list[dict]:
    if t.empty:
        return []
    eq = t["result_r"].cumsum().round(3)
    return [{"time": tm, "value": float(v)} for tm, v in zip(t["time"], eq)]


def _group(t: pd.DataFrame, col: str) -> list[dict]:
    if t.empty:
        return []
    g = t.groupby(col)["result_r"]
    out = pd.DataFrame({
        "trades": g.size(), "win_rate": g.apply(lambda x: 100 * (x > 0).mean()),
        "expectancy_r": g.mean(), "total_r": g.sum(),
    }).round(2).reset_index().rename(columns={col: "key"})
    out["key"] = out["key"].astype(str)
    return out.sort_values("total_r", ascending=False).to_dict("records")
