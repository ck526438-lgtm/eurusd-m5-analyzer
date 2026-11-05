"""Envoi des alertes : Telegram (texte + graphique), Discord, notification bureau, console."""
from __future__ import annotations

import csv
import logging
from pathlib import Path

import pandas as pd
import requests

log = logging.getLogger(__name__)


def format_message(sig, symbol: str = "EURUSD") -> str:
    arrow = "🟢" if sig.direction == 1 else "🔴"
    close_t = sig.time + pd.Timedelta(minutes=5)
    risk = max(abs(sig.entry - sig.sl), 1e-9)
    if abs(sig.tp2 - sig.tp1) < 1e-5:
        tps = [f"TP     : <code>{sig.tp1:.5f}</code>  (1:{abs(sig.tp1 - sig.entry) / risk:.1f})"]
    else:
        tps = [f"TP1    : <code>{sig.tp1:.5f}</code>  (1:{abs(sig.tp1 - sig.entry) / risk:.1f})",
               f"TP2    : <code>{sig.tp2:.5f}</code>  (1:{abs(sig.tp2 - sig.entry) / risk:.1f})"]
    lines = [
        f"{arrow} <b>{sig.side} {symbol}</b> — M5 — qualité <b>{sig.quality}</b> ({sig.score}/10)",
        f"🕐 Bougie clôturée {close_t:%d/%m %H:%M} UTC",
        f"📐 {sig.pattern}",
        "",
        f"Entrée : <code>{sig.entry:.5f}</code>",
        f"Stop   : <code>{sig.sl:.5f}</code>  ({sig.risk_pips} pips)",
        *tps,
        "",
        "<b>Pourquoi :</b>",
        *[f"• {r}" for r in sig.reasons],
        "",
        "<i>Conseil : 50 % à TP1 puis stop au point d'entrée. Max 1 % du capital par trade.</i>",
    ]
    return "\n".join(lines)


class Notifier:
    def __init__(self, cfg):
        self.cfg = cfg

    def send(self, sig, chart_path: str | None = None) -> None:
        msg = format_message(sig, self.cfg.symbol)
        print("\n" + _strip_html(msg) + "\n")
        self._journal(sig)
        if self.cfg.telegram_token and self.cfg.telegram_chat_id:
            self.telegram(msg, chart_path if self.cfg.send_chart else None)
        if self.cfg.discord_webhook:
            self.discord(_strip_html(msg))
        if self.cfg.desktop_notifications:
            self.desktop(f"{sig.side} {self.cfg.symbol} ({sig.quality})",
                         f"Entrée {sig.entry:.5f} | SL {sig.sl:.5f} | TP {sig.tp1:.5f}")

    # ---------------------------------------------------------------- #
    def telegram(self, text: str, photo: str | None = None) -> bool:
        base = f"https://api.telegram.org/bot{self.cfg.telegram_token}"
        try:
            if photo and Path(photo).exists() and len(text) <= 1024:
                with open(photo, "rb") as f:
                    r = requests.post(f"{base}/sendPhoto", timeout=20,
                                      data={"chat_id": self.cfg.telegram_chat_id,
                                            "caption": text, "parse_mode": "HTML"},
                                      files={"photo": f})
            else:
                if photo and Path(photo).exists():
                    with open(photo, "rb") as f:
                        requests.post(f"{base}/sendPhoto", timeout=20,
                                      data={"chat_id": self.cfg.telegram_chat_id}, files={"photo": f})
                r = requests.post(f"{base}/sendMessage", timeout=20,
                                  data={"chat_id": self.cfg.telegram_chat_id, "text": text,
                                        "parse_mode": "HTML"})
            if not r.ok:
                log.error("Telegram : %s %s", r.status_code, r.text[:200])
            return r.ok
        except requests.RequestException as e:
            log.error("Telegram injoignable : %s", e)
            return False

    def discord(self, text: str) -> None:
        try:
            requests.post(self.cfg.discord_webhook, json={"content": text[:1900]}, timeout=15)
        except requests.RequestException as e:
            log.error("Discord : %s", e)

    @staticmethod
    def desktop(title: str, body: str) -> None:
        try:
            from plyer import notification
            notification.notify(title=title, message=body, app_name="EURUSD M5", timeout=15)
        except Exception:  # noqa: BLE001 — plyer optionnel
            pass

    def _journal(self, sig) -> None:
        p = Path(self.cfg.journal_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        new = not p.exists()
        with p.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["time_utc", "side", "entry", "sl", "tp1", "tp2", "score", "pattern"])
            w.writerow([sig.time, sig.side, sig.entry, sig.sl, sig.tp1, sig.tp2, sig.score, sig.pattern])


def _strip_html(s: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", s)
