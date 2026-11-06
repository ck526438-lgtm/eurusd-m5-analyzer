from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from analyzer.config import Config
from analyzer.server import create_app, seconds_to_next_close


@pytest.fixture()
def client(tmp_path):
    cfg = Config(source="demo", data_dir=str(tmp_path / "data"))
    app = create_app(cfg, str(tmp_path / "config.yaml"))
    with TestClient(app) as c:
        yield c


def test_state(client):
    s = client.get("/api/state").json()
    assert s["ready"] and s["source"] == "demo"
    assert len(s["chart"]["candles"]) == 600
    assert {"h1_bias", "rsi", "adx", "atr_pips"} <= set(s["context"])


def test_journal_filled_and_tracked(client):
    j = client.get("/api/journal").json()
    assert j["signals"], "le journal doit contenir les signaux de l'historique"
    assert {r["status"] for r in j["signals"]} <= {"en cours", "TP2", "BE", "SL", "temps"}
    key = j["signals"][0]["key"]
    assert client.put(f"/api/journal/{key}/note", json={"note": "pris"}).status_code == 200
    assert client.get("/api/journal").json()["signals"][0]["note"] == "pris"
    assert client.get("/api/journal.csv").text.startswith("time,side")


def test_settings_roundtrip(client, tmp_path):
    r = client.put("/api/settings", json={"strategy": {"min_score": 7}})
    assert r.status_code == 200 and r.json()["strategy"]["min_score"] == 7
    assert (tmp_path / "config.yaml").exists()
    assert client.put("/api/settings", json={"strategy": {"min_sl_pips": 30}}).status_code == 400


def test_backtest_endpoint(client):
    r = client.post("/api/backtest", json={"bars": 3000}).json()
    assert r["period"]["bars"] == 3000 and "stats" in r


def test_index_served(client):
    assert "Espace d'analyse" in client.get("/").text
    assert client.get("/static/vendor/lightweight-charts.standalone.production.js").status_code == 200


def test_next_close():
    t = datetime(2026, 1, 1, 10, 4, 0, tzinfo=timezone.utc)
    assert seconds_to_next_close(t) == pytest.approx(68)
    t = datetime(2026, 1, 1, 10, 5, 3, tzinfo=timezone.utc)
    assert seconds_to_next_close(t) == pytest.approx(5)
