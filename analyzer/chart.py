"""Graphique en chandeliers avec le signal (entrée, SL, TP) et les zones S/R."""
from __future__ import annotations

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

BG, FG, GRID = "#0f1115", "#d7dbe0", "#232833"
UP, DOWN = "#26a69a", "#ef5350"


def plot_signal(an, i: int, signal=None, bars: int = 90, path: str = "signals/chart.png") -> str:
    df = an.df.iloc[max(0, i - bars + 1): i + 1]
    fig, ax = plt.subplots(figsize=(12, 6.5), dpi=110)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    xs = mdates.date2num(df.index.tz_convert(None).to_pydatetime())
    w = (5 / 1440) * 0.7

    for x, (o, h, l, c) in zip(xs, df[["open", "high", "low", "close"]].to_numpy()):
        col = UP if c >= o else DOWN
        ax.vlines(x, l, h, color=col, linewidth=1)
        ax.add_patch(Rectangle((x - w / 2, min(o, c)), w, max(abs(c - o), 1e-6), color=col))

    ax.plot(xs, df["ema_fast"], color="#ffca28", lw=1, label="EMA 20")
    ax.plot(xs, df["ema_mid"], color="#42a5f5", lw=1, label="EMA 50")
    ax.plot(xs, df["ema_slow"], color="#ab47bc", lw=1, label="EMA 200")

    lo, hi = df["low"].min(), df["high"].max()
    pad = (hi - lo) * 0.15
    near = sorted(an.zones(i), key=lambda z: abs(z.price - an.c[i]))[:6]
    for z in near:
        if lo - pad <= z.price <= hi + pad:
            ax.axhline(z.price, color="#78909c", lw=0.8 + 0.6 * min(z.touches, 3),
                       alpha=0.35, ls="--")

    title = f"{an.cfg.symbol} M5 — clôture {df.index[-1] + pd.Timedelta(minutes=5):%d/%m %H:%M} UTC"
    if signal is not None:
        x0, x1 = xs[-1], xs[-1] + 12 * 5 / 1440
        levels = [(signal.entry, FG, "Entrée"), (signal.sl, DOWN, "SL")]
        if abs(signal.tp2 - signal.tp1) < 1e-5:
            levels.append((signal.tp1, UP, "TP"))
        else:
            levels += [(signal.tp1, UP, "TP1"), (signal.tp2, UP, "TP2")]
        for y, col, lab in levels:
            ax.hlines(y, xs[0], x1, color=col, lw=1.2, ls="-" if lab == "Entrée" else ":")
            ax.text(x1, y, f" {lab} {y:.5f}", color=col, va="center", fontsize=9)
        ax.annotate("▲" if signal.direction == 1 else "▼", (x0, signal.entry),
                    color=UP if signal.direction == 1 else DOWN, fontsize=18, ha="center",
                    va="top" if signal.direction == 1 else "bottom")
        lo, hi = min(lo, signal.sl, signal.tp2), max(hi, signal.sl, signal.tp2)
        title += f"  |  {signal.side} {signal.quality} — score {signal.score}/10 — {signal.pattern}"
        ax.set_xlim(xs[0] - w, x1 + 10 * 5 / 1440)

    ax.set_ylim(lo - pad, hi + pad)
    ax.set_title(title, color=FG, fontsize=11, loc="left")
    ax.tick_params(colors=FG, labelsize=8)
    ax.grid(color=GRID, lw=0.5)
    for sp in ax.spines.values():
        sp.set_color(GRID)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.yaxis.set_major_formatter(plt.FormatStrFormatter("%.5f"))
    ax.legend(loc="upper left", fontsize=8, facecolor=BG, labelcolor=FG, edgecolor=GRID)
    fig.tight_layout()
    fig.savefig(path, facecolor=BG)
    plt.close(fig)
    return path
