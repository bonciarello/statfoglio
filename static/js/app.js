/**
 * StatFoglio — Frontend logic
 * Handles file upload, paste, API calls, and result rendering.
 */

(function () {
  "use strict";

  // ── DOM refs ──────────────────────────────────────────────────────────
  const ribbon = document.getElementById("ribbon");
  const dropZone = document.getElementById("drop-zone");
  const fileInput = document.getElementById("file-input");
  const fileNameDisplay = document.getElementById("file-name-display");
  const btnUpload = document.getElementById("btn-upload");
  const btnPaste = document.getElementById("btn-paste");
  const pasteText = document.getElementById("paste-text");
  const sepSelect = document.getElementById("sep-select");
  const loading = document.getElementById("loading");
  const errorBox = document.getElementById("error-box");
  const errorMsg = document.getElementById("error-msg");
  const results = document.getElementById("results");

  // ── Tabs ──────────────────────────────────────────────────────────────
  const tabs = document.querySelectorAll(".tab-btn");
  const panels = document.querySelectorAll(".input-panel");

  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      tabs.forEach(function (t) {
        t.classList.remove("active");
        t.setAttribute("aria-selected", "false");
      });
      tab.classList.add("active");
      tab.setAttribute("aria-selected", "true");

      panels.forEach(function (p) { p.hidden = true; });
      var panelId = tab.getAttribute("aria-controls");
      var panel = document.getElementById(panelId);
      if (panel) panel.hidden = false;
    });
  });

  // ── File handling ─────────────────────────────────────────────────────
  var selectedFile = null;

  fileInput.addEventListener("change", function () {
    if (fileInput.files.length > 0) {
      selectedFile = fileInput.files[0];
      fileNameDisplay.textContent = "File: " + selectedFile.name;
      btnUpload.disabled = false;
    }
  });

  // Drag & drop
  dropZone.addEventListener("dragover", function (e) {
    e.preventDefault();
    dropZone.classList.add("drag-over");
  });

  dropZone.addEventListener("dragleave", function () {
    dropZone.classList.remove("drag-over");
  });

  dropZone.addEventListener("drop", function (e) {
    e.preventDefault();
    dropZone.classList.remove("drag-over");
    if (e.dataTransfer.files.length > 0) {
      selectedFile = e.dataTransfer.files[0];
      fileNameDisplay.textContent = "File: " + selectedFile.name;
      btnUpload.disabled = false;
    }
  });

  // Upload button
  btnUpload.addEventListener("click", function () {
    if (!selectedFile) return;
    var formData = new FormData();
    formData.append("file", selectedFile);
    uploadData(formData);
  });

  // Paste button
  btnPaste.addEventListener("click", function () {
    var text = pasteText.value.trim();
    if (!text) {
      showError("Incolla dei dati prima di analizzare.");
      return;
    }
    analyzePasted(text, sepSelect.value);
  });

  // ── API calls ─────────────────────────────────────────────────────────
  function uploadData(formData) {
    setLoading(true);
    hideError();
    hideResults();

    fetch("api/upload", { method: "POST", body: formData })
      .then(handleResponse)
      .then(renderResults)
      .catch(handleFetchError);
  }

  function analyzePasted(text, sep) {
    setLoading(true);
    hideError();
    hideResults();

    fetch("api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text, sep: sep }),
    })
      .then(handleResponse)
      .then(renderResults)
      .catch(handleFetchError);
  }

  function handleResponse(res) {
    if (!res.ok) {
      return res.json().then(function (data) {
        throw new Error(data.error || "Errore del server (" + res.status + ")");
      });
    }
    return res.json();
  }

  function handleFetchError(err) {
    setLoading(false);
    showError(err.message || "Errore di rete. Riprova.");
  }

  // ── Render results ────────────────────────────────────────────────────
  function renderResults(data) {
    setLoading(false);

    if (data.error) {
      showError(data.error);
      return;
    }

    // Summary badges
    var summaryBadges = document.getElementById("summary-badges");
    summaryBadges.innerHTML =
      '<span class="badge">Righe: ' + data.shape.rows + "</span>" +
      '<span class="badge">Colonne: ' + data.shape.columns + "</span>";

    // Stats table
    renderStatsTable(data.columns);

    // Charts
    renderCharts(data.charts);

    // Preview
    renderPreview(data.preview_columns, data.preview);

    results.hidden = false;
    results.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderStatsTable(columns) {
    var thead = document.querySelector("#stats-table thead");
    var tbody = document.querySelector("#stats-table tbody");

    // Determine which stats to show
    var numericCols = columns.filter(function (c) { return c.dtype && c.dtype.includes("float") || c.dtype && c.dtype.includes("int"); });
    var textCols = columns.filter(function (c) { return !(c.dtype && c.dtype.includes("float")) && !(c.dtype && c.dtype.includes("int")); });

    // Headers: Colonna | Tipo | Statistiche...
    var headers = ["Colonna", "Tipo"];

    if (numericCols.length > 0) {
      headers.push("Media", "Mediana", "Dev. Std", "Min", "Max", "Valori", "Unici", "Missing");
    }
    if (textCols.length > 0) {
      // We use the same table but show different stats for text cols
    }

    // Unified headers
    var allHeaders = ["Colonna", "Tipo", "Media", "Mediana", "Dev. Std", "Min", "Max", "Conteggio", "Unici", "Missing", "Più frequente"];

    thead.innerHTML = "<tr>" + allHeaders.map(function (h) { return "<th>" + h + "</th>"; }).join("") + "</tr>";

    var rows = columns.map(function (c) {
      var isNum = c.dtype && (c.dtype.includes("float") || c.dtype.includes("int"));
      return "<tr>" +
        "<td>" + escHtml(c.name) + "</td>" +
        "<td>" + escHtml(c.dtype) + "</td>" +
        (isNum
          ? "<td class='num'>" + fmtNum(c.mean) + "</td>" +
            "<td class='num'>" + fmtNum(c.median) + "</td>" +
            "<td class='num'>" + fmtNum(c.std) + "</td>" +
            "<td class='num'>" + fmtNum(c.min) + "</td>" +
            "<td class='num'>" + fmtNum(c.max) + "</td>" +
            "<td class='num'>" + c.count + "</td>" +
            "<td class='num'>" + c.unique + "</td>" +
            "<td class='num'>" + c.missing + "</td>" +
            "<td>—</td>"
          : "<td>—</td><td>—</td><td>—</td><td>—</td><td>—</td>" +
            "<td class='num'>" + c.count + "</td>" +
            "<td class='num'>" + c.unique + "</td>" +
            "<td class='num'>" + c.missing + "</td>" +
            "<td>" + escHtml(c.most_common || "—") + (c.top_freq ? " (" + c.top_freq + ")" : "") + "</td>") +
        "</tr>";
    });

    tbody.innerHTML = rows.join("");
  }

  function renderCharts(charts) {
    var grid = document.getElementById("charts-grid");
    if (!charts || charts.length === 0) {
      grid.innerHTML = "<p style='color:var(--color-text-muted);font-size:0.875rem'>Nessun grafico generato.</p>";
      return;
    }

    grid.innerHTML = charts.map(function (ch) {
      var badgeClass = ch.type === "bar" ? "bar" : "pie";
      var badgeLabel = ch.type === "bar" ? "Barre" : "Torta";
      return '<div class="chart-card" tabindex="0" role="button" aria-label="Scarica grafico ' + escAttr(ch.column) + ' come PNG" data-filename="' + escAttr(ch.filename) + '">' +
        '<div class="chart-card-header">' +
          '<span class="chart-card-title">' + escHtml(ch.column) + '</span>' +
          '<span class="chart-card-badge ' + badgeClass + '">' + badgeLabel + '</span>' +
        '</div>' +
        '<img class="chart-card-img" src="' + escAttr(ch.data) + '" alt="Grafico di ' + escAttr(ch.column) + '" loading="lazy" width="640" height="360">' +
      '</div>';
    }).join("");

    // Click to download
    grid.querySelectorAll(".chart-card").forEach(function (card) {
      card.addEventListener("click", function () {
        var filename = card.getAttribute("data-filename");
        if (filename) downloadChart(filename);
      });
      card.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          var filename = card.getAttribute("data-filename");
          if (filename) downloadChart(filename);
        }
      });
    });
  }

  function downloadChart(filename) {
    var a = document.createElement("a");
    a.href = "api/chart/" + encodeURIComponent(filename);
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  function renderPreview(columns, rows) {
    var thead = document.querySelector("#preview-table thead");
    var tbody = document.querySelector("#preview-table tbody");

    thead.innerHTML = "<tr>" + columns.map(function (c) { return "<th>" + escHtml(String(c)) + "</th>"; }).join("") + "</tr>";

    tbody.innerHTML = rows.map(function (row) {
      return "<tr>" + columns.map(function (c) {
        return "<td>" + escHtml(String(row[c] !== undefined ? row[c] : "")) + "</td>";
      }).join("") + "</tr>";
    }).join("");
  }

  // ── UI helpers ────────────────────────────────────────────────────────
  function setLoading(show) {
    loading.hidden = !show;
    if (show) {
      ribbon.classList.add("active");
    } else {
      ribbon.classList.remove("active");
    }
  }

  function showError(msg) {
    errorMsg.textContent = msg;
    errorBox.hidden = false;
  }

  function hideError() {
    errorBox.hidden = true;
  }

  function hideResults() {
    results.hidden = true;
  }

  function escHtml(str) {
    if (str === null || str === undefined) return "—";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function escAttr(str) {
    if (str === null || str === undefined) return "";
    return String(str).replace(/"/g, "&quot;").replace(/&/g, "&amp;");
  }

  function fmtNum(val) {
    if (val === undefined || val === null) return "—";
    var n = Number(val);
    if (isNaN(n)) return "—";
    if (Number.isInteger(n)) return n.toString();
    return n.toFixed(4);
  }
})();
