"""Tests for StatFoglio backend."""

from __future__ import annotations

import io
import json
import os
import sys

import pytest

# Ensure app is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


# ── Test data generators ────────────────────────────────────────────────────

def _csv_content() -> bytes:
    return b"Nome,Eta,Citta,Reddito\nMario,34,Roma,32000\nAnna,28,Milano,45000\nLuca,45,Napoli,38000\nSofia,31,Roma,51000\nMarco,39,Milano,29000\n"


def _tsv_content() -> bytes:
    return b"Nome\tEta\tCitta\tReddito\nMario\t34\tRoma\t32000\nAnna\t28\tMilano\t45000\nLuca\t45\tNapoli\t38000\n"


def _xlsx_content() -> bytes:
    import pandas as pd

    df = pd.DataFrame(
        {
            "Nome": ["Mario", "Anna", "Luca", "Sofia", "Marco"],
            "Età": [34, 28, 45, 31, 39],
            "Città": ["Roma", "Milano", "Napoli", "Roma", "Milano"],
            "Reddito": [32000, 45000, 38000, 51000, 29000],
        }
    )
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    return buf.read()


# ── Tests ───────────────────────────────────────────────────────────────────


def test_index_returns_html(client):
    rv = client.get("/")
    assert rv.status_code == 200
    assert b"<!DOCTYPE html>" in rv.data or b"<html" in rv.data


def test_robots_txt(client):
    rv = client.get("/robots.txt")
    assert rv.status_code == 200
    assert b"User-agent" in rv.data


def test_sitemap_xml(client):
    rv = client.get("/sitemap.xml")
    assert rv.status_code == 200
    assert b"urlset" in rv.data


def test_upload_csv(client):
    rv = client.post(
        "/api/upload",
        data={"file": (io.BytesIO(_csv_content()), "test.csv")},
        content_type="multipart/form-data",
    )
    assert rv.status_code == 200
    data = json.loads(rv.data)
    assert data["shape"]["rows"] == 5
    assert data["shape"]["columns"] == 4
    assert len(data["columns"]) == 4
    assert len(data["charts"]) >= 1  # at least one chart
    assert len(data["preview"]) == 5


def test_upload_tsv(client):
    rv = client.post(
        "/api/upload",
        data={"file": (io.BytesIO(_tsv_content()), "test.tsv")},
        content_type="multipart/form-data",
    )
    assert rv.status_code == 200
    data = json.loads(rv.data)
    assert data["shape"]["rows"] == 3
    assert data["shape"]["columns"] == 4


def test_upload_xlsx(client):
    rv = client.post(
        "/api/upload",
        data={"file": (io.BytesIO(_xlsx_content()), "test.xlsx")},
        content_type="multipart/form-data",
    )
    assert rv.status_code == 200
    data = json.loads(rv.data)
    assert data["shape"]["rows"] == 5
    assert data["shape"]["columns"] == 4


def test_paste_csv(client):
    text = "Nome,Età,Città,Reddito\nMario,34,Roma,32000\nAnna,28,Milano,45000\n"
    rv = client.post(
        "/api/analyze",
        data=json.dumps({"text": text, "sep": ","}),
        content_type="application/json",
    )
    assert rv.status_code == 200
    data = json.loads(rv.data)
    assert data["shape"]["rows"] == 2
    assert data["shape"]["columns"] == 4


def test_paste_tab(client):
    text = "Nome\tEtà\tCittà\nMario\t34\tRoma\nAnna\t28\tMilano\n"
    rv = client.post(
        "/api/analyze",
        data=json.dumps({"text": text, "sep": "tab"}),
        content_type="application/json",
    )
    assert rv.status_code == 200
    data = json.loads(rv.data)
    assert data["shape"]["rows"] == 2
    assert data["shape"]["columns"] == 3


def test_upload_no_file(client):
    rv = client.post("/api/upload", data={}, content_type="multipart/form-data")
    assert rv.status_code == 400
    data = json.loads(rv.data)
    assert "error" in data


def test_upload_empty_filename(client):
    rv = client.post(
        "/api/upload",
        data={"file": (io.BytesIO(b""), "")},
        content_type="multipart/form-data",
    )
    assert rv.status_code == 400


def test_paste_empty_text(client):
    rv = client.post(
        "/api/analyze",
        data=json.dumps({"text": "", "sep": ","}),
        content_type="application/json",
    )
    assert rv.status_code == 400


def test_paste_invalid_text(client):
    rv = client.post(
        "/api/analyze",
        data=json.dumps({"text": "garbage,,,data\n\n\n", "sep": ","}),
        content_type="application/json",
    )
    # Should either parse or return 400 — but won't crash
    assert rv.status_code in (200, 400)


def test_stats_numeric_columns(client):
    """Verify that numeric columns return mean, median, std, min, max."""
    rv = client.post(
        "/api/upload",
        data={"file": (io.BytesIO(_csv_content()), "test.csv")},
        content_type="multipart/form-data",
    )
    data = json.loads(rv.data)
    # Find "Eta" column
    eta = next(c for c in data["columns"] if c["name"] == "Eta")
    assert "mean" in eta
    assert "median" in eta
    assert "std" in eta
    assert "min" in eta
    assert "max" in eta
    assert eta["count"] == 5


def test_stats_text_columns(client):
    """Verify text columns return unique count and most_common."""
    rv = client.post(
        "/api/upload",
        data={"file": (io.BytesIO(_csv_content()), "test.csv")},
        content_type="multipart/form-data",
    )
    data = json.loads(rv.data)
    citta = next(c for c in data["columns"] if c["name"] == "Citta")
    assert "unique" in citta
    assert "most_common" in citta
    assert "mean" not in citta  # not numeric


def test_chart_endpoint_404(client):
    rv = client.get("/api/chart/nonexistent.png")
    assert rv.status_code == 404


def test_chart_download(client):
    """Generate a chart via upload, then download it."""
    rv = client.post(
        "/api/upload",
        data={"file": (io.BytesIO(_csv_content()), "test.csv")},
        content_type="multipart/form-data",
    )
    data = json.loads(rv.data)
    if data["charts"]:
        filename = data["charts"][0]["filename"]
        rv2 = client.get(f"/api/chart/{filename}")
        assert rv2.status_code == 200
        assert rv2.mimetype == "image/png"
