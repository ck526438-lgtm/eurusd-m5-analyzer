#!/usr/bin/env python3
"""EURUSD M5 Analyzer — détection d'opportunités par chandeliers + confluences.

Commandes :
  python main.py scan            analyse la dernière bougie clôturée
  python main.py live            surveille en continu (toutes les 5 min) et envoie les alertes
  python main.py backtest        teste la stratégie sur l'historique disponible
  python main.py telegram-test   vérifie la configuration Telegram
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from analyzer.chart import plot_signal
from analyzer.config import load_config
from analyzer.data import from_csv, load_data
from analyzer.notifier import Notifier
from analyzer.strategy import Analyzer

STATE = Path("signals/state.json")
log = logging.getLogger("eurusd")


def market_context(an: Analyzer, i: int) -> str:
    bias = {1: "HAUSSIÈRE 📈", -1: "BAISSIÈRE 📉", 0: "NEUTRE ↔"}[int(an.bias[i])]
    zones = sorted(an.zones(i), key=lambda z: abs(z.price - an.c[i]))[:4]
    zt = ", ".join(f"{z.kind[0].upper()} {z.price:.5f}×{z.touches}" for z in zones) or "—"
    return (f"[{an.idx[i] + pd.Timedelta(minutes=5):%H:%M} UTC] {an.cfg.symbol} {an.c[i]:.5f} | "
            f"H1 {bias} | RSI {an.rsi[i]:.0f} | ADX {an.adx[i]:.0f} | "
            f"ATR {an.atr[i] / an.cfg.pip:.1f} pips | Zones : {zt}")


def scan_once(cfg, notifier: Notifier, state: dict) -> None:
    df = load_data(cfg)
    an = Analyzer(df, cfg)
    i = len(df) - 1
    print(market_context(an, i))
    sig = an.evaluate(i)
    if sig is None:
        return
    key = str(sig.time)
    if state.get("last_time") == key:
        return  # déjà envoyé
    last = state.get(f"last_{sig.direction}")
    if last and (sig.time - pd.Timestamp(last)) < pd.Timedelta(minutes=5 * cfg.strategy.cooldown_bars):
        log.info("Signal ignoré (cooldown)")
        return
    chart = plot_signal(an, i, sig, path=f"signals/{sig.time:%Y%m%d_%H%M}_{sig.side}.png")
    notifier.send(sig, chart)
    state.update({"last_time": key, f"last_{sig.direction}": key})
    STATE.write_text(json.dumps(state))


def cmd_live(cfg) -> None:
    notifier = Notifier(cfg)
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    print(f"▶ Surveillance {cfg.symbol} M5 — score mini {cfg.strategy.min_score}/10. Ctrl+C pour arrêter.")
    while True:
        try:
            scan_once(cfg, notifier, state)
        except Exception as e:  # noqa: BLE001 — la boucle ne doit jamais mourir
            log.error("Erreur pendant l'analyse : %s", e)
        # Attente jusqu'à la prochaine clôture M5 (+8 s pour laisser le courtier publier)
        now = datetime.now(timezone.utc)
        wait = 300 - (now.minute % 5) * 60 - now.second + 8
        time.sleep(wait if wait > 0 else 300)


def cmd_backtest(cfg, csv_path: str | None) -> None:
    from analyzer.backtest import run_backtest

    df = from_csv(csv_path) if csv_path else load_data(cfg)
    print(f"Données : {len(df)} bougies M5 du {df.index[0]:%d/%m/%Y} au {df.index[-1]:%d/%m/%Y}")
    trades, stats = run_backtest(df, cfg)
    for k, v in stats.items():
        print(f"  {k:<16} {v}")
    if not trades.empty:
        out = Path("signals/backtest_trades.csv")
        trades.to_csv(out, index=False)
        print(f"\nDétail par figure :\n{trades.groupby('pattern')['result_r'].agg(['count', 'mean', 'sum']).round(2)}")
        print(f"\nTrades enregistrés dans {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Analyseur EURUSD M5")
    ap.add_argument("command", choices=["scan", "live", "backtest", "telegram-test"])
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--csv", help="fichier CSV de bougies M5 (heure UTC)")
    ap.add_argument("--source", choices=["auto", "mt5", "yfinance", "csv"])
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config(a.config)
    if a.source:
        cfg.source = a.source
    if a.csv:
        cfg.source, cfg.csv_path = "csv", a.csv
    Path("signals").mkdir(exist_ok=True)

    if a.command == "scan":
        state = json.loads(STATE.read_text()) if STATE.exists() else {}
        scan_once(cfg, Notifier(cfg), state)
    elif a.command == "live":
        cmd_live(cfg)
    elif a.command == "backtest":
        cmd_backtest(cfg, a.csv)
    elif a.command == "telegram-test":
        if not (cfg.telegram_token and cfg.telegram_chat_id):
            print("❌ TELEGRAM_TOKEN et TELEGRAM_CHAT_ID manquants dans le fichier .env")
            return
        ok = Notifier(cfg).telegram("✅ <b>EURUSD M5 Analyzer</b> est connecté. Les alertes arriveront ici.")
        print("✅ Message envoyé" if ok else "❌ Échec — vérifie le token et le chat_id")


if __name__ == "__main__":
    main()
