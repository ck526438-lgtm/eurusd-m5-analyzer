"""Chargement de la configuration (config.yaml + variables d'environnement / .env)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv est optionnel
    pass


@dataclass
class StrategyConfig:
    min_score: float = 6.0          # score minimum pour envoyer une alerte (sur 10)
    ema_fast: int = 20
    ema_mid: int = 50
    ema_slow: int = 200
    rsi_period: int = 14
    atr_period: int = 14
    adx_period: int = 14
    adx_min: float = 18.0           # en dessous : marché sans direction
    swing_lookback: int = 300       # bougies utilisées pour les zones S/R
    zone_atr_mult: float = 0.6      # largeur de fusion des niveaux en ATR
    sl_atr_buffer: float = 0.25     # marge sous/sur la mèche en ATR
    min_sl_pips: float = 4.0
    max_sl_pips: float = 18.0
    rr_tp1: float = 1.5
    rr_tp2: float = 2.5
    min_room_r: float = 1.2         # espace minimum (en R) avant la zone opposée
    cooldown_bars: int = 6          # pas deux alertes même sens en < 30 min
    use_sessions: bool = True       # Londres + New York seulement
    sessions_utc: list = field(default_factory=lambda: [[7, 11], [12, 17]])


@dataclass
class Config:
    symbol: str = "EURUSD"
    source: str = "auto"            # auto | mt5 | yfinance | csv
    csv_path: str = ""
    bars: int = 1500
    broker_utc_offset: int = 0      # décalage heure serveur MT5 -> UTC (ex. 2 ou 3)
    pip: float = 0.0001
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    telegram_token: str = ""
    telegram_chat_id: str = ""
    discord_webhook: str = ""
    desktop_notifications: bool = True
    send_chart: bool = True
    journal_path: str = "signals/journal.csv"


def load_config(path: str | os.PathLike = "config.yaml") -> Config:
    cfg = Config()
    p = Path(path)
    if p.exists():
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        strat = raw.pop("strategy", {}) or {}
        for k, v in raw.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        for k, v in strat.items():
            if hasattr(cfg.strategy, k):
                setattr(cfg.strategy, k, v)
    # Les secrets viennent de l'environnement (.env), jamais du dépôt
    cfg.telegram_token = os.getenv("TELEGRAM_TOKEN", cfg.telegram_token)
    cfg.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", cfg.telegram_chat_id)
    cfg.discord_webhook = os.getenv("DISCORD_WEBHOOK", cfg.discord_webhook)
    return cfg
