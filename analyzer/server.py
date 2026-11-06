"""Serveur de l'espace d'analyse (FastAPI) : API JSON + flux temps réel + interface web."""
from __future__ import annotations

import asyncio
import io
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import Config, save_config, update_config
from .service import AnalysisService
from .terminal import TerminalNotifier

log = logging.getLogger(__name__)
STATIC = Path(__file__).resolve().parent.parent / "web"
SCAN_DELAY_S = 8  # laisse le temps au courtier de publier la bougie clôturée


def seconds_to_next_close(now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    s = (now.minute % 5) * 60 + now.second + now.microsecond / 1e6
    return SCAN_DELAY_S - s if s < SCAN_DELAY_S else 300 - s + SCAN_DELAY_S


def create_app(cfg: Config, config_path: str = "config.yaml",
               terminal: TerminalNotifier | None = None, autostart: bool = True) -> FastAPI:
    service = AnalysisService(cfg)
    queues: set[asyncio.Queue] = set()
    state = {"loop": None, "backtest": None, "next_scan": None}

    def on_event(ev: dict) -> None:
        loop = state["loop"]
        if loop is None:
            return
        for q in list(queues):
            loop.call_soon_threadsafe(q.put_nowait, ev)

    service.listeners.append(on_event)
    if terminal:
        service.listeners.append(
            lambda ev: terminal.signal(ev["signal"]) if ev["type"] == "signal"
            else terminal.error(ev["message"]) if ev["type"] == "error" else None)

    async def run_refresh() -> None:
        await asyncio.to_thread(service.refresh)
        if terminal:
            terminal.market(service.snapshot())

    async def scheduler() -> None:
        while True:
            wait = seconds_to_next_close()
            state["next_scan"] = datetime.now(timezone.utc).timestamp() + wait
            await asyncio.sleep(wait)
            try:
                await run_refresh()
            except Exception as e:  # noqa: BLE001 — la boucle ne doit jamais s'arrêter
                log.exception("Analyse impossible : %s", e)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        state["loop"] = asyncio.get_running_loop()
        task = None
        if autostart:
            await run_refresh()
            task = asyncio.create_task(scheduler())
        yield
        if task:
            task.cancel()
        service.journal.close()

    app = FastAPI(title="EURUSD M5 Analyzer", lifespan=lifespan, docs_url="/api/docs")
    app.state.service = service

    # ------------------------------------------------------------- API
    @app.get("/api/state")
    def get_state():
        snap = service.snapshot()
        snap["next_scan"] = state["next_scan"]
        return snap

    @app.post("/api/scan")
    async def scan_now():
        await run_refresh()
        return {"ok": service.error is None, "error": service.error}

    @app.get("/api/journal")
    def journal(limit: int = 500):
        return {"signals": service.journal.list(limit), "stats": service.journal.stats()}

    @app.put("/api/journal/{key}/note")
    def note(key: str, payload: dict = Body(...)):
        service.journal.set_note(key, str(payload.get("note", "")))
        return {"ok": True}

    @app.get("/api/journal.csv")
    def journal_csv():
        import csv
        rows = service.journal.list(100_000)
        buf = io.StringIO()
        cols = ["time", "side", "pattern", "score", "quality", "entry", "sl", "tp1", "tp2",
                "risk_pips", "status", "result_r", "exit_time", "origin", "note"]
        w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
        return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename=journal_eurusd_m5.csv"})

    @app.get("/api/meta")
    def meta():
        from .patterns import PATTERN_NAMES
        return {"patterns": PATTERN_NAMES, "sources": ["auto", "mt5", "yfinance", "csv", "demo"]}

    @app.get("/api/settings")
    def get_settings():
        return service.cfg.to_dict()

    @app.put("/api/settings")
    async def put_settings(changes: dict = Body(...)):
        try:
            new = update_config(service.cfg, changes)
        except (ValueError, TypeError) as e:
            raise HTTPException(400, str(e)) from e
        service.set_config(new)
        save_config(new, config_path)
        await run_refresh()
        return new.to_dict()

    @app.post("/api/backtest")
    async def backtest(payload: dict = Body(default={})):
        from .backtest import run_backtest
        from .data import load_data

        bars = int(payload.get("bars") or service.cfg.bars)
        changes = {"bars": max(300, min(bars, 100_000)),
                   "strategy": payload.get("strategy", {})}
        try:
            cfg_bt = update_config(service.cfg, changes)
            df, src = await asyncio.to_thread(load_data, cfg_bt)
            result = await asyncio.to_thread(run_backtest, df, cfg_bt)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, f"Backtest impossible : {e}") from e
        result["source"] = src
        state["backtest"] = result
        return result

    @app.get("/api/backtest/last")
    def last_backtest():
        return state["backtest"] or {}

    @app.get("/api/stream")
    async def stream():
        q: asyncio.Queue = asyncio.Queue()
        queues.add(q)

        async def gen():
            try:
                yield "retry: 3000\n\n"
                while True:
                    try:
                        ev = await asyncio.wait_for(q.get(), timeout=20)
                        yield f"data: {json.dumps(ev)}\n\n"
                    except asyncio.TimeoutError:
                        yield ": ping\n\n"
            finally:
                queues.discard(q)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ------------------------------------------------------------- interface
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    return app
