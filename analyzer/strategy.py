"""Moteur de décision : combine chandeliers + tendance + zones + momentum en un score /10."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import patterns as pat
from .structure import Zone, nearest, zones_at


@dataclass
class Signal:
    time: pd.Timestamp
    direction: int                 # +1 ACHAT, -1 VENTE
    entry: float
    sl: float
    tp1: float
    tp2: float
    score: float
    pattern: str
    reasons: list[str] = field(default_factory=list)
    risk_pips: float = 0.0

    @property
    def side(self) -> str:
        return "ACHAT" if self.direction == 1 else "VENTE"

    @property
    def quality(self) -> str:
        if self.score >= 8:
            return "A+"
        if self.score >= 7:
            return "A"
        return "B"


def in_session(ts: pd.Timestamp, sessions: list) -> bool:
    hour = ts.hour + ts.minute / 60
    return any(a <= hour < b for a, b in sessions)


class Analyzer:
    """Pré-calcule ce qui est coûteux, puis évalue n'importe quelle bougie i."""

    def __init__(self, df: pd.DataFrame, cfg):
        from .indicators import add_indicators
        from .structure import swing_points

        self.cfg = cfg
        self.s = cfg.strategy
        self.df = add_indicators(df, self.s)
        a = self.df
        self.o, self.h, self.l, self.c = (a[x].to_numpy() for x in ("open", "high", "low", "close"))
        self.atr = a["atr"].to_numpy()
        self.rsi = a["rsi"].to_numpy()
        self.adx = a["adx"].to_numpy()
        self.ef, self.em, self.es = (a[x].to_numpy() for x in ("ema_fast", "ema_mid", "ema_slow"))
        self.bias = a["htf_bias"].to_numpy()
        self.idx = a.index
        self.sw_hi, self.sw_lo = swing_points(self.h, self.l)

    @property
    def warmup(self) -> int:
        return max(self.s.ema_slow, 60)

    def zones(self, i: int) -> list[Zone]:
        return zones_at(i, self.h, self.l, self.sw_hi, self.sw_lo, self.c[i], self.atr[i],
                        self.s.swing_lookback, self.s.zone_atr_mult)

    # ------------------------------------------------------------------ #
    def evaluate(self, i: int) -> Signal | None:
        s, pip = self.s, self.cfg.pip
        if i < self.warmup:
            return None
        atr = self.atr[i]
        ts = self.idx[i]
        # La bougie i se ferme 5 min après son ouverture
        if s.use_sessions and not in_session(ts + pd.Timedelta(minutes=5), s.sessions_utc):
            return None

        found = pat.detect(self.o, self.h, self.l, self.c, i, atr)
        if not found:
            return None
        dirs = {p.direction for p in found}
        if len(dirs) > 1:          # figures contradictoires -> on s'abstient
            return None
        d = dirs.pop()
        best = max(found, key=lambda p: p.strength)
        names = " + ".join(sorted({p.name for p in found}))

        score, why = 0.0, []
        strength = min(3, best.strength + (1 if len(found) > 1 else 0))
        score += strength
        why.append(f"Figure : {names} (force {strength}/3)")

        # 1) Tendance de fond H1
        if self.bias[i] == d:
            score += 2; why.append("Dans le sens de la tendance H1")
        elif self.bias[i] == -d:
            score -= 2; why.append("⚠ Contre la tendance H1")
        else:
            why.append("Tendance H1 neutre")

        # 2) Alignement des moyennes mobiles M5
        c = self.c[i]
        if (d == 1 and c > self.em[i] and self.ef[i] > self.em[i]) or \
           (d == -1 and c < self.em[i] and self.ef[i] < self.em[i]):
            score += 1; why.append("EMA 20/50 M5 alignées")
        if (d == 1 and c > self.es[i]) or (d == -1 and c < self.es[i]):
            score += 0.5; why.append("Prix du bon côté de l'EMA 200")

        # 3) Réaction sur une zone clé (S/R) ou sur l'EMA dynamique
        zones = self.zones(i)
        own_kind = "support" if d == 1 else "resistance"
        z = nearest(zones, best.extreme, own_kind)
        on_zone = z is not None and abs(best.extreme - z.price) <= 0.5 * atr
        if on_zone:
            pts = 2 if z.strong else 1
            score += pts
            label = "support" if d == 1 else "résistance"
            why.append(f"Rejet de la zone de {label} {z.price:.5f} "
                       f"({z.touches} touche{'s' if z.touches > 1 else ''})")
        else:
            lo, hi = sorted((self.ef[i], self.em[i]))
            touched = (d == 1 and self.l[i] <= hi + 0.2 * atr and c > lo) or \
                      (d == -1 and self.h[i] >= lo - 0.2 * atr and c < hi)
            if touched:
                score += 1; why.append("Rebond sur la zone EMA 20/50")

        # 4) Momentum RSI
        r, r1 = self.rsi[i], self.rsi[i - 1]
        if d == 1:
            if r > r1 and r < 70:
                score += 1; why.append(f"RSI remonte ({r:.0f})")
            if r >= 75:
                score -= 1; why.append(f"⚠ RSI suracheté ({r:.0f})")
        else:
            if r < r1 and r > 30:
                score += 1; why.append(f"RSI redescend ({r:.0f})")
            if r <= 25:
                score -= 1; why.append(f"⚠ RSI survendu ({r:.0f})")

        # 5) Force du marché
        if self.adx[i] >= s.adx_min:
            score += 1; why.append(f"Marché directionnel (ADX {self.adx[i]:.0f})")
        else:
            score -= 1; why.append(f"⚠ Marché mou (ADX {self.adx[i]:.0f})")

        if s.use_sessions:
            score += 0.5; why.append("Session Londres / New York")

        score = float(np.clip(score, 0, 10))
        if score < s.min_score:
            return None

        # ---- Gestion du risque : SL / TP ----
        entry = c
        sl = best.extreme - d * s.sl_atr_buffer * atr
        risk = abs(entry - sl)
        if risk < s.min_sl_pips * pip:
            risk = s.min_sl_pips * pip
            sl = entry - d * risk
        if risk > s.max_sl_pips * pip:
            return None  # stop trop large pour du M5
        tp1 = entry + d * s.rr_tp1 * risk
        tp2 = entry + d * s.rr_tp2 * risk

        opp = nearest([z for z in zones if (z.price - entry) * d > 0], entry,
                      "resistance" if d == 1 else "support")
        if opp is not None:
            room = abs(opp.price - entry)
            if room < s.min_room_r * risk:
                return None  # obstacle trop proche
            if room < s.rr_tp2 * risk:
                tp2 = opp.price - d * 0.1 * atr
                if abs(tp2 - entry) < abs(tp1 - entry):
                    tp1 = tp2  # zone avant TP1 : objectif unique
                why.append(f"Objectif placé avant la zone {opp.price:.5f}")

        return Signal(ts, d, round(entry, 5), round(sl, 5), round(tp1, 5), round(tp2, 5),
                      round(score, 1), best.name, why, round(risk / pip, 1))
