#!/usr/bin/env python3
"""EURUSD M5 Analyzer — espace d'analyse des chandeliers japonais.

  python main.py                 lance l'espace d'analyse (navigateur + terminal)
  python main.py watch           surveillance dans le terminal uniquement
  python main.py scan            une analyse de la dernière bougie, puis quitte
  python main.py backtest        backtest dans le terminal

Options : --demo (marché simulé), --source mt5|yfinance|csv, --csv FICHIER,
          --port 8000, --no-browser, --no-bell
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
import webbrowser

from analyzer.config import load_config
from analyzer.data import SOURCE_LABELS
from analyzer.terminal import TerminalNotifier


def _utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def cmd_start(cfg, args, term: TerminalNotifier) -> None:
    import threading

    import uvicorn

    from analyzer.server import create_app

    url = f"http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}"
    term.banner(url, SOURCE_LABELS.get(cfg.source, "auto (MetaTrader 5, sinon Yahoo Finance)"))
    app = create_app(cfg, args.config, terminal=term)
    if not args.no_browser:
        threading.Timer(2.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


def cmd_watch(cfg, term: TerminalNotifier, once: bool = False) -> None:
    from analyzer.server import seconds_to_next_close
    from analyzer.service import AnalysisService

    svc = AnalysisService(cfg)
    svc.listeners.append(lambda ev: term.signal(ev["signal"]) if ev["type"] == "signal"
                         else term.error(ev["message"]) if ev["type"] == "error" else None)
    if not once:
        term.banner("(mode terminal — pas d'interface web)", SOURCE_LABELS.get(cfg.source, "auto"))
    while True:
        svc.refresh()
        term.market(svc.snapshot())
        if once:
            radar = (svc.snapshot() or {}).get("radar")
            if radar and not radar["blocked"]:
                term.signal(radar)
            return
        time.sleep(seconds_to_next_close())


def cmd_backtest(cfg) -> None:
    from analyzer.backtest import run_backtest
    from analyzer.data import load_data

    df, src = load_data(cfg)
    print(f"Données {SOURCE_LABELS.get(src, src)} : {len(df)} bougies M5 "
          f"du {df.index[0]:%d/%m/%Y} au {df.index[-1]:%d/%m/%Y}\n")
    res = run_backtest(df, cfg)
    st = res["stats"]
    if not st.get("trades"):
        print("Aucun trade sur la période.")
        return
    labels = {"trades": "Trades", "win_rate": "Réussite %", "total_r": "Total (R)",
              "expectancy_r": "Espérance (R/trade)", "profit_factor": "Profit factor",
              "max_drawdown_r": "Drawdown max (R)", "max_losing_streak": "Pertes d'affilée max",
              "exits": "Sorties"}
    for k, lab in labels.items():
        print(f"  {lab:<22} {st.get(k)}")
    print("\n  Par figure :")
    for g in res["by_pattern"]:
        print(f"    {g['key']:<38} {g['trades']:>4} trades  {g['win_rate']:>5.1f} %  {g['total_r']:>+7.2f} R")


def main() -> None:
    _utf8_console()
    ap = argparse.ArgumentParser(description="EURUSD M5 Analyzer")
    ap.add_argument("command", nargs="?", default="start", choices=["start", "watch", "scan", "backtest"])
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--source", choices=["auto", "mt5", "yfinance", "csv", "demo"])
    ap.add_argument("--demo", action="store_true", help="marché simulé (pour découvrir l'outil)")
    ap.add_argument("--csv", help="fichier CSV de bougies M5 (heure UTC)")
    ap.add_argument("--bars", type=int, help="nombre de bougies à charger")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--no-bell", action="store_true", help="pas de bip à chaque signal")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config(a.config)
    if a.source:
        cfg.source = a.source
    if a.demo:
        cfg.source = "demo"
    if a.csv:
        cfg.source, cfg.csv_path = "csv", a.csv
    if a.bars:
        cfg.bars = a.bars
    term = TerminalNotifier(cfg.symbol, bell=not a.no_bell)

    if a.command == "start":
        cmd_start(cfg, a, term)
    elif a.command == "watch":
        try:
            cmd_watch(cfg, term)
        except KeyboardInterrupt:
            print("\nArrêt.")
    elif a.command == "scan":
        cmd_watch(cfg, term, once=True)
    elif a.command == "backtest":
        cmd_backtest(cfg)


if __name__ == "__main__":
    main()
