import numpy as np
import pandas as pd
import pytest

from analyzer import patterns
from analyzer.backtest import run_backtest
from analyzer.config import Config
from analyzer.strategy import Analyzer


def synthetic(n=6000, seed=1):
    """Série EURUSD M5 simulée : tendances alternées + volatilité intrajournalière."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-06-01", periods=n, freq="5min", tz="UTC")
    hours = idx.hour.to_numpy()
    vol = np.where((hours >= 7) & (hours < 17), 0.00022, 0.0001)
    drift = np.repeat(rng.choice([-1, 1], n // 400 + 1), 400)[:n] * 0.00003
    close = 1.08 + np.cumsum(drift + rng.normal(0, 1, n) * vol)
    open_ = np.r_[close[0], close[:-1]]
    wick = np.abs(rng.normal(0, 1, (2, n))) * vol
    high = np.maximum(open_, close) + wick[0]
    low = np.minimum(open_, close) - wick[1]
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                         "volume": 100.0}, index=idx)


def test_bullish_engulfing():
    o = np.array([1.1, 1.1, 1.1010, 1.1000])
    c = np.array([1.1, 1.1, 1.1000, 1.1015])
    h = np.maximum(o, c) + 0.0001
    l = np.minimum(o, c) - 0.0001
    names = [p.name for p in patterns.detect(o, h, l, c, 3, atr=0.0010)]
    assert "Avalement haussier" in names


def test_hammer():
    o = np.array([1.1, 1.1, 1.1, 1.10100])
    c = np.array([1.1, 1.1, 1.1, 1.10110])
    h = np.array([1.1, 1.1, 1.1, 1.10115])
    l = np.array([1.1, 1.1, 1.1, 1.10000])
    found = patterns.detect(o, h, l, c, 3, atr=0.0008)
    assert any(p.direction == 1 and "marteau" in p.name for p in found)


def test_no_lookahead():
    """Un signal à la bougie i ne doit pas changer si on ajoute des bougies futures."""
    df = synthetic()
    cfg = Config()
    full = Analyzer(df, cfg)
    for i in range(1000, 5800, 37):
        part = Analyzer(df.iloc[: i + 1], cfg)
        a, b = full.evaluate(i), part.evaluate(i)
        assert (a is None) == (b is None), i
        if a:
            assert a.entry == b.entry and a.sl == b.sl and a.score == b.score


def test_signal_risk_rules():
    df = synthetic()
    cfg = Config()
    an = Analyzer(df, cfg)
    sigs = [s for s in (an.evaluate(i) for i in range(an.warmup, len(df))) if s]
    assert sigs, "aucun signal sur 6000 bougies"
    for s in sigs:
        assert s.score >= cfg.strategy.min_score
        assert cfg.strategy.min_sl_pips - 0.01 <= s.risk_pips <= cfg.strategy.max_sl_pips
        if s.direction == 1:
            assert s.sl < s.entry < s.tp1 <= s.tp2
        else:
            assert s.sl > s.entry > s.tp1 >= s.tp2


def test_backtest_runs():
    trades, stats = run_backtest(synthetic(), Config())
    assert stats["trades"] > 0
    assert set(trades["exit"]) <= {"SL", "BE", "TP2", "temps"}
