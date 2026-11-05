"""Sources de données M5 : MetaTrader 5 (temps réel), Yahoo Finance (gratuit), CSV.

Toutes les fonctions renvoient un DataFrame indexé en UTC avec les colonnes
open, high, low, close, volume — uniquement des bougies CLÔTURÉES.
"""
from __future__ import annotations

import logging

import pandas as pd

from .config import Config

log = logging.getLogger(__name__)
COLS = ["open", "high", "low", "close", "volume"]


def _drop_open_candle(df: pd.DataFrame, minutes: int = 5) -> pd.DataFrame:
    """Retire la dernière bougie si elle n'est pas encore fermée."""
    if df.empty:
        return df
    now = pd.Timestamp.now(tz="UTC")
    if df.index[-1] + pd.Timedelta(minutes=minutes) > now:
        return df.iloc[:-1]
    return df


def from_mt5(cfg: Config) -> pd.DataFrame:
    import MetaTrader5 as mt5  # Windows uniquement

    if not mt5.initialize():
        raise RuntimeError(f"MT5 initialize() a échoué : {mt5.last_error()}")
    try:
        mt5.symbol_select(cfg.symbol, True)
        rates = mt5.copy_rates_from_pos(cfg.symbol, mt5.TIMEFRAME_M5, 0, cfg.bars)
        if rates is None or len(rates) == 0:
            raise RuntimeError(f"Aucune donnée MT5 pour {cfg.symbol} : {mt5.last_error()}")
    finally:
        mt5.shutdown()
    df = pd.DataFrame(rates)
    idx = pd.to_datetime(df["time"], unit="s") - pd.Timedelta(hours=cfg.broker_utc_offset)
    df.index = idx.dt.tz_localize("UTC")
    df = df.rename(columns={"tick_volume": "volume"})[COLS]
    return _drop_open_candle(df.astype(float))


def from_yfinance(cfg: Config) -> pd.DataFrame:
    import yfinance as yf

    ticker = f"{cfg.symbol}=X"
    period = "60d" if cfg.bars > 1400 else "5d"
    df = yf.download(ticker, period=period, interval="5m", progress=False, auto_adjust=False)
    if df is None or df.empty:
        raise RuntimeError(f"Yahoo Finance n'a renvoyé aucune donnée pour {ticker}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)[COLS]
    df.index = pd.to_datetime(df.index)
    df.index = df.index.tz_convert("UTC") if df.index.tz else df.index.tz_localize("UTC")
    df = df.dropna().tail(cfg.bars)
    return _drop_open_candle(df.astype(float))


def from_csv(path: str) -> pd.DataFrame:
    """CSV avec colonnes time/datetime, open, high, low, close[, volume] (heure UTC)."""
    df = pd.read_csv(path)
    df.columns = [c.lower().strip() for c in df.columns]
    tcol = next(c for c in ("time", "datetime", "date", "timestamp") if c in df.columns)
    df.index = pd.to_datetime(df[tcol], utc=True)
    if "volume" not in df.columns:
        df["volume"] = 0.0
    return df[COLS].astype(float).sort_index()


def load_data(cfg: Config) -> pd.DataFrame:
    if cfg.source == "csv":
        return from_csv(cfg.csv_path)
    if cfg.source == "mt5":
        return from_mt5(cfg)
    if cfg.source == "yfinance":
        return from_yfinance(cfg)
    # auto : MT5 si disponible (meilleure qualité), sinon Yahoo
    try:
        return from_mt5(cfg)
    except Exception as e:  # noqa: BLE001
        log.info("MT5 indisponible (%s) -> Yahoo Finance", e)
        return from_yfinance(cfg)
