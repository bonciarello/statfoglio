"""StatFoglio — Analizzatore interattivo di fogli di calcolo con statistiche descrittive e grafici."""

from __future__ import annotations

import base64
import io
import json
import os
import hashlib
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")  # no GUI backend
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from flask import Flask, jsonify, render_template, request, send_file

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

STATIC = Path(__file__).parent / "static"
CHARTS_DIR = STATIC / "charts"
CHARTS_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)

# Matplotlib style — clean, modern
plt.rcParams.update(
    {
        "figure.facecolor": "#F8F6F0",
        "axes.facecolor": "#F8F6F0",
        "axes.edgecolor": "#CBD5E1",
        "axes.grid": True,
        "grid.alpha": 0.25,
        "grid.color": "#94A3B8",
        "font.family": "sans-serif",
        "font.size": 11,
        "axes.titlesize": 15,
        "axes.titleweight": "bold",
        "axes.labelcolor": "#334155",
        "xtick.color": "#475569",
        "ytick.color": "#475569",
        "text.color": "#1E293B",
    }
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

COLORS = ["#2563EB", "#059669", "#D97706", "#DC2626", "#7C3AED", "#0891B2", "#BE185D", "#65A30D"]


def _chart_hash(prefix: str, data: str) -> str:
    h = hashlib.sha256((prefix + data).encode()).hexdigest()[:12]
    return f"{prefix}_{h}.png"


def _read_dataframe(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """Parse uploaded bytes into a DataFrame."""
    name_lower = filename.lower()
    if name_lower.endswith(".csv"):
        return pd.read_csv(io.BytesIO(file_bytes))
    if name_lower.endswith((".tsv", ".tab")):
        return pd.read_csv(io.BytesIO(file_bytes), sep="\t")
    if name_lower.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(file_bytes))
    # fallback: try CSV
    try:
        return pd.read_csv(io.BytesIO(file_bytes))
    except Exception:
        return pd.read_csv(io.BytesIO(file_bytes), sep="\t")


def _read_from_text(text: str, sep: str) -> pd.DataFrame:
    """Parse pasted text into a DataFrame."""
    return pd.read_csv(io.StringIO(text), sep=sep)


def _describe_column(series: pd.Series) -> dict[str, Any]:
    """Return descriptive stats for a single column."""
    stats: dict[str, Any] = {"name": str(series.name), "dtype": str(series.dtype), "count": int(series.count())}

    if pd.api.types.is_numeric_dtype(series):
        s = series.dropna()
        stats.update(
            {
                "mean": round(float(s.mean()), 4),
                "median": round(float(s.median()), 4),
                "std": round(float(s.std()), 4),
                "min": round(float(s.min()), 4),
                "max": round(float(s.max()), 4),
                "unique": int(s.nunique()),
                "missing": int(series.isna().sum()),
            }
        )
    else:
        s = series.dropna()
        stats.update(
            {
                "unique": int(s.nunique()),
                "missing": int(series.isna().sum()),
                "most_common": str(s.mode().iloc[0]) if not s.mode().empty else "",
                "top_freq": int(s.value_counts().iloc[0]) if len(s.value_counts()) > 0 else 0,
            }
        )

    return stats


def _bar_chart(series: pd.Series, filepath: str) -> str:
    """Generate a bar chart for a numeric column. Returns the filename."""
    s = series.dropna()
    if len(s) == 0:
        return ""

    # Bin numeric data for distribution
    bins = min(20, max(5, int(np.sqrt(len(s)))))
    counts, edges = np.histogram(s, bins=bins)
    bin_labels = [f"{edges[i]:.1f}–{edges[i+1]:.1f}" for i in range(len(edges) - 1)]

    fig, ax = plt.subplots(figsize=(9, 4.5))
    bars = ax.bar(range(len(counts)), counts, color=COLORS[0], edgecolor="white", linewidth=0.8, width=0.75)
    ax.set_xticks(range(len(counts)))
    ax.set_xticklabels(bin_labels, rotation=40, ha="right", fontsize=8)
    ax.set_title(f"Distribuzione: {series.name}", fontsize=14, pad=12)
    ax.set_ylabel("Frequenza")
    ax.set_xlabel("Intervallo")
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))

    # Add count labels on bars
    for bar, count in zip(bars, counts):
        if count > 0:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(counts) * 0.02,
                    str(count), ha="center", va="bottom", fontsize=9, color="#475569")

    fig.tight_layout()
    fig.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return os.path.basename(filepath)


def _pie_chart(series: pd.Series, filepath: str, max_slices: int = 10) -> str:
    """Generate a pie chart for a categorical column. Returns the filename."""
    s = series.dropna().astype(str)
    if len(s) == 0:
        return ""

    vc = s.value_counts()
    if len(vc) > max_slices:
        top = vc.nlargest(max_slices - 1)
        others = vc.iloc[max_slices - 1:].sum()
        top["Altro"] = others
        vc = top

    fig, ax = plt.subplots(figsize=(7, 5))
    wedges, texts, autotexts = ax.pie(
        vc.values,
        labels=vc.index,
        autopct="%1.1f%%",
        colors=COLORS[: len(vc)],
        startangle=140,
        pctdistance=0.78,
        textprops={"fontsize": 9, "color": "#334155"},
    )
    for at in autotexts:
        at.set_fontsize(8)
        at.set_color("#1E293B")
        at.set_weight("bold")

    ax.set_title(f"Frequenza: {series.name}", fontsize=14, pad=12)

    fig.tight_layout()
    fig.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return os.path.basename(filepath)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index() -> str:
    return render_template("index.html")


@app.route("/api/upload", methods=["POST"])
def api_upload() -> tuple:
    """Handle file upload."""
    if "file" not in request.files:
        return jsonify({"error": "Nessun file caricato."}), 400

    f = request.files["file"]
    if f.filename == "":
        return jsonify({"error": "Nome file vuoto."}), 400

    try:
        file_bytes = f.read()
        df = _read_dataframe(file_bytes, f.filename or "data.csv")
    except Exception as e:
        return jsonify({"error": f"Impossibile leggere il file: {str(e)}"}), 400

    return _analyze_and_respond(df)


@app.route("/api/analyze", methods=["POST"])
def api_analyze() -> tuple:
    """Handle pasted text data."""
    body = request.get_json(silent=True) or {}
    text = body.get("text", "").strip()
    sep = body.get("sep", ",")

    if not text:
        return jsonify({"error": "Nessun dato incollato."}), 400

    # Map common separator names
    sep_map = {",": ",", "tab": "\t", ";": ";", "|": "|"}
    sep = sep_map.get(sep, ",")

    try:
        df = _read_from_text(text, sep)
    except Exception as e:
        return jsonify({"error": f"Impossibile analizzare il testo: {str(e)}"}), 400

    return _analyze_and_respond(df)


def _analyze_and_respond(df: pd.DataFrame) -> tuple:
    """Run descriptive analysis and generate charts."""
    if df.empty:
        return jsonify({"error": "Il dataset è vuoto."}), 400

    # Limit to reasonable size
    if len(df) > 100_000:
        df = df.sample(100_000, random_state=42)

    # Compute stats
    columns_stats = [_describe_column(df[col]) for col in df.columns]

    # Generate charts
    charts: list[dict[str, str]] = []
    for col in df.columns:
        series = df[col]
        if pd.api.types.is_numeric_dtype(series):
            filename = _chart_hash("bar", f"{col}_{series.to_json()}")
            filepath = CHARTS_DIR / filename
            if not os.path.exists(filepath):
                _bar_chart(series, str(filepath))
            if os.path.exists(filepath):
                # read as base64 inline
                with open(filepath, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                charts.append({"column": str(col), "type": "bar", "filename": filename, "data": f"data:image/png;base64,{b64}"})
        else:
            filename = _chart_hash("pie", f"{col}_{series.to_json()}")
            filepath = CHARTS_DIR / filename
            if not os.path.exists(filepath):
                _pie_chart(series, str(filepath))
            if os.path.exists(filepath):
                with open(filepath, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                charts.append({"column": str(col), "type": "pie", "filename": filename, "data": f"data:image/png;base64,{b64}"})

    return jsonify(
        {
            "shape": {"rows": len(df), "columns": len(df.columns)},
            "columns": columns_stats,
            "charts": charts,
            "preview": df.head(20).fillna("").to_dict(orient="records"),
            "preview_columns": list(df.columns),
        }
    )


@app.route("/api/chart/<filename>")
def api_chart(filename: str) -> Any:
    """Serve a saved chart PNG for download."""
    filepath = CHARTS_DIR / filename
    if not filepath.exists():
        return jsonify({"error": "Grafico non trovato."}), 404
    return send_file(str(filepath), mimetype="image/png", as_attachment=True, download_name=filename)


@app.route("/robots.txt")
def robots() -> Any:
    return send_file(STATIC / "robots.txt", mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap() -> Any:
    return send_file(STATIC / "sitemap.xml", mimetype="application/xml")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 4599))
    app.run(host="0.0.0.0", port=port, debug=False)
