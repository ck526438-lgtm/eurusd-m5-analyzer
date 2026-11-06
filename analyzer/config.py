"""Configuration : config.yaml, modifiable aussi depuis l'onglet Réglages."""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml


@dataclass
class StrategyConfig:
    min_score: float = 6.0          # score minimum d'un signal (sur 10)
    ema_fast: int = 20
    ema_mid: int = 50
    ema_slow: int = 200
    rsi_period: int = 14
    atr_period: int = 14
    adx_period: int = 14
    adx_min: float = 18.0
    swing_lookback: int = 300
    zone_atr_mult: float = 0.6
    sl_atr_buffer: float = 0.25
    min_sl_pips: float = 4.0
    max_sl_pips: float = 18.0
    rr_tp1: float = 1.5
    rr_tp2: float = 2.5
    min_room_r: float = 1.2
    cooldown_bars: int = 6
    use_sessions: bool = True
    sessions_utc: list = field(default_factory=lambda: [[7, 11], [12, 17]])
    spread_pips: float = 0.8        # coût simulé (backtest + suivi des signaux)
    max_hold_bars: int = 48         # sortie forcée après 4 h
    disabled_patterns: list = field(default_factory=list)  # figures ignorées


@dataclass
class Config:
    symbol: str = "EURUSD"
    source: str = "auto"            # auto | mt5 | yfinance | csv | demo
    csv_path: str = ""
    bars: int = 1500
    broker_utc_offset: int = 0
    pip: float = 0.0001
    desktop_notifications: bool = False
    data_dir: str = "data"
    strategy: StrategyConfig = field(default_factory=StrategyConfig)

    def to_dict(self) -> dict:
        return asdict(self)


EDITABLE_ROOT = {"symbol", "source", "csv_path", "bars", "broker_utc_offset", "desktop_notifications"}


def _apply(cfg: Config, raw: dict) -> Config:
    raw = dict(raw or {})
    strat = raw.pop("strategy", {}) or {}
    for k, v in raw.items():
        if hasattr(cfg, k) and k != "strategy":
            setattr(cfg, k, _cast(getattr(cfg, k), v))
    for k, v in strat.items():
        if hasattr(cfg.strategy, k):
            setattr(cfg.strategy, k, _cast(getattr(cfg.strategy, k), v))
    return cfg


def _cast(current, value):
    if isinstance(current, bool):
        return value if isinstance(value, bool) else str(value).lower() in ("1", "true", "oui", "on")
    if isinstance(current, int) and not isinstance(value, bool):
        return int(float(value))
    if isinstance(current, float):
        return float(value)
    return value


def load_config(path: str | os.PathLike = "config.yaml") -> Config:
    p = Path(path)
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
    return _apply(Config(), raw or {})


def update_config(cfg: Config, changes: dict) -> Config:
    """Applique des changements venant de l'interface (valeurs validées)."""
    root = {k: v for k, v in changes.items() if k in EDITABLE_ROOT}
    strat = changes.get("strategy", {}) or {}
    new = _apply(Config(**{**asdict(cfg), "strategy": StrategyConfig(**asdict(cfg.strategy))}),
                 {**root, "strategy": strat})
    validate(new)
    return new


def validate(cfg: Config) -> None:
    s = cfg.strategy
    if cfg.source not in ("auto", "mt5", "yfinance", "csv", "demo"):
        raise ValueError("Source inconnue")
    if not 0 <= s.min_score <= 10:
        raise ValueError("Le score minimum doit être entre 0 et 10")
    if not 0 < s.min_sl_pips < s.max_sl_pips:
        raise ValueError("Stop mini doit être > 0 et < stop maxi")
    if not 0 < s.rr_tp1 <= s.rr_tp2:
        raise ValueError("TP1 doit être > 0 et ≤ TP2")
    if not 300 <= cfg.bars <= 100_000:
        raise ValueError("Le nombre de bougies doit être entre 300 et 100 000")
    for a, b in s.sessions_utc:
        if not 0 <= a < b <= 24:
            raise ValueError("Sessions : heures invalides")


def save_config(cfg: Config, path: str | os.PathLike = "config.yaml") -> None:
    d = cfg.to_dict()
    d.pop("pip", None)
    d.pop("data_dir", None)
    header = "# EURUSD M5 Analyzer — configuration (modifiable aussi dans l'onglet Réglages)\n"
    Path(path).write_text(header + yaml.safe_dump(d, sort_keys=False, allow_unicode=True),
                          encoding="utf-8")
