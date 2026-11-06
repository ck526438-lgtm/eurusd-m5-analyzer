import numpy as np
import pandas as pd
import pytest

from analyzer import patterns
from analyzer.backtest import run_backtest
from analyzer.config import Config, update_config
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
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close) + wick[0],
                         "low": np.minimum(open_, close) - wick[1], "close": close,
                         "volume": 100.0}, index=idx)


def test_bullish_engulfing():
    o = np.array([1.1, 1.1, 1.1010, 1.1000])
    c = np.array([1.1, 1.1, 1.1000, 1.1015])
    h, l = np.maximum(o, c) + 0.0001, np.minimum(o, c) - 0.0001
    assert "Avalement haussier" in [p.name for p in patterns.detect(o, h, l, c, 3, atr=0.0010)]


def test_hammer():
    o = np.array([1.1, 1.1, 1.1, 1.10100])
    c = np.array([1.1, 1.1, 1.1, 1.10110])
    h = np.array([1.1, 1.1, 1.1, 1.10115])
    l = np.array([1.1, 1.1, 1.1, 1.10000])
    found = patterns.detect(o, h, l, c, 3, atr=0.0008)
    assert any(p.direction == 1 and "marteau" in p.name for p in found)


def test_pattern_names_complete():
    assert len(set(patterns.PATTERN_NAMES)) == 12


def test_no_lookahead():
    """Un signal à la bougie i ne doit pas changer si on ajoute des bougies futures."""
    df, cfg = synthetic(), Config()
    full = Analyzer(df, cfg)
    for i in range(1000, 5800, 37):
        a, b = full.inspect(i), Analyzer(df.iloc[: i + 1], cfg).inspect(i)
        assert (a is None) == (b is None), i
        if a:
            assert (a.entry, a.sl, a.score, a.blocked) == (b.entry, b.sl, b.score, b.blocked)


def test_signal_risk_rules():
    cfg = Config()
    sigs = Analyzer(synthetic(), cfg).scan()
    assert sigs, "aucun signal sur 6000 bougies"
    for s in sigs:
        assert s.blocked is None and s.score >= cfg.strategy.min_score
        assert cfg.strategy.min_sl_pips - 0.01 <= s.risk_pips <= cfg.strategy.max_sl_pips
        if s.direction == 1:
            assert s.sl < s.entry < s.tp1 <= s.tp2
        else:
            assert s.sl > s.entry > s.tp1 >= s.tp2
        assert sum(f.points for f in s.factors) == pytest.approx(s.score, abs=0.01) or s.score in (0, 10)


def test_disabled_patterns():
    cfg = Config()
    an = Analyzer(synthetic(), cfg)
    first = an.scan()[0].pattern
    cfg.strategy.disabled_patterns = [first]
    assert all(s.pattern != first for s in Analyzer(synthetic(), cfg).scan())


def test_backtest():
    res = run_backtest(synthetic(), Config())
    st = res["stats"]
    assert st["trades"] > 0 and len(res["equity"]) == st["trades"]
    assert set(st["exits"]) <= {"SL", "BE", "TP2", "temps"}
    assert sum(g["trades"] for g in res["by_pattern"]) == st["trades"]


def test_settings_validation():
    cfg = Config()
    assert update_config(cfg, {"strategy": {"min_score": "7.5"}}).strategy.min_score == 7.5
    assert cfg.strategy.min_score == 6.0  # l'original n'est pas modifié
    with pytest.raises(ValueError):
        update_config(cfg, {"strategy": {"rr_tp1": 3, "rr_tp2": 2}})
    with pytest.raises(ValueError):
        update_config(cfg, {"source": "inconnue"})
