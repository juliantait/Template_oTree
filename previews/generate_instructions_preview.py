#!/usr/bin/env python3
"""
generate_instructions_preview.py
================================

Generate self-contained preview outputs for the Instructions section of this
oTree experiment template.

Outputs (in previews/):
    - instructions_preview_long.html         all blocks stacked vertically
    - instructions_preview_interactive.html  one block at a time with nav
    - instructions_preview.pdf               long view, variables as literals

Usage:
    python3 generate_instructions_preview.py                    # opens tkinter popup
    python3 generate_instructions_preview.py --no-popup         # write template JSON
    python3 generate_instructions_preview.py --config FILE.json # read values from JSON

Fallback behaviour: if tkinter cannot be imported, --no-popup is passed, or DISPLAY
is empty, the script either (a) reuses .preview_state.json if it already contains
treatment data, or (b) writes a starter template to .preview_state.json and prints
instructions to edit it and re-run.

Dependencies:
    pip install jinja2 playwright
    playwright install chromium
"""

from __future__ import annotations

import argparse
import ast
import html as html_module
import importlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INSTRUCTIONS_HTML = PROJECT_ROOT / "intro" / "instructions_text.html"
PREQUIZ_HTML = PROJECT_ROOT / "intro" / "prequiz_text.html"
STYLE_CSS = PROJECT_ROOT / "_static" / "global" / "style.css"
QUIZ_ITEMS_FILE = PROJECT_ROOT / "intro" / "quiz_items.py"
SETTINGS_FILE = PROJECT_ROOT / "settings.py"
STATE_FILE = PROJECT_ROOT / ".preview_state.json"
OUT_DIR = PROJECT_ROOT / "previews"

LONG_HTML_NAME = "instructions_preview_long.html"
INTERACTIVE_HTML_NAME = "instructions_preview_interactive.html"
PDF_NAME = "instructions_preview.pdf"


# ---------------------------------------------------------------------------
# Dependency check
# ---------------------------------------------------------------------------

def check_dependencies() -> None:
    missing = []
    for pkg in ("jinja2", "playwright"):
        try:
            importlib.import_module(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        sys.stderr.write(
            "ERROR: missing Python packages: " + ", ".join(missing) + "\n"
            "Install with:\n"
            "    pip install " + " ".join(missing) + "\n"
            "Then install the headless browser:\n"
            "    playwright install chromium\n"
        )
        sys.exit(1)


def check_chromium() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.stderr.write("ERROR: playwright not importable.\n")
        sys.exit(1)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            browser.close()
    except Exception as exc:
        sys.stderr.write(
            "ERROR: could not launch headless Chromium: "
            f"{exc}\n"
            "Run: playwright install chromium\n"
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# CSS inlining
# ---------------------------------------------------------------------------

def inline_css() -> str:
    if not STYLE_CSS.exists():
        return ""
    base = STYLE_CSS.parent
    text = STYLE_CSS.read_text(encoding="utf-8")
    out = []
    for line in text.splitlines():
        m = re.match(r"\s*@import\s+url\(['\"]?(.+?)['\"]?\)\s*;", line)
        if m:
            sub = base / m.group(1)
            if sub.exists():
                out.append(
                    f"/* === {sub.name} === */\n"
                    + sub.read_text(encoding="utf-8")
                )
            continue
        out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Block parsing
# ---------------------------------------------------------------------------

def _find_balanced_div_end(text: str, after: int) -> int:
    pos = after
    depth = 1
    while depth > 0:
        next_open = text.find("<div", pos)
        next_close = text.find("</div>", pos)
        if next_close == -1:
            return -1
        if next_open != -1 and next_open < next_close:
            depth += 1
            pos = next_open + 4
        else:
            depth -= 1
            pos = next_close + len("</div>")
    return pos


def parse_div_blocks(text: str) -> list[dict]:
    blocks: list[dict] = []
    pattern = re.compile(
        r'<div\s+class="([^"]*\binstruction-block\b[^"]*)"[^>]*>',
        re.IGNORECASE,
    )
    for m in pattern.finditer(text):
        end = _find_balanced_div_end(text, m.end())
        if end == -1:
            continue
        inner = text[m.end():end - len("</div>")]
        blocks.append(
            dict(
                classes=m.group(1),
                inner=inner,
                kind="div",
                is_prequiz="prequiz-block" in m.group(1),
            )
        )
    return blocks


def parse_part_blocks(text: str) -> list[dict]:
    pattern = re.compile(
        r"\{\{\s*block\s+(\w+)\s*\}\}(.*?)\{\{\s*endblock\s*\}\}",
        re.DOTALL,
    )
    return [
        dict(
            classes="instruction-block",
            inner=m.group(2),
            kind="part",
            is_prequiz=False,
            name=m.group(1),
        )
        for m in pattern.finditer(text)
    ]


def _strip_html_comments(text: str) -> str:
    """Remove <!-- ... --> comments so block markers inside them don't match."""
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def parse_blocks(path: Path) -> list[dict]:
    if not path.exists():
        return []
    text = _strip_html_comments(path.read_text(encoding="utf-8"))
    div_blocks = parse_div_blocks(text)
    if div_blocks:
        return div_blocks
    return parse_part_blocks(text)


# ---------------------------------------------------------------------------
# Variable / conditional extraction
# ---------------------------------------------------------------------------

_RESERVED = {
    "block", "endblock", "if", "elif", "else", "endif", "for", "endfor",
    "in", "and", "or", "not", "is", "True", "False", "None",
}


def extract_variables(text: str) -> set[str]:
    found: set[str] = set()
    for m in re.finditer(r"\{\{\s*([^\}]+?)\s*\}\}", text):
        expr = m.group(1).strip()
        first = re.split(r"[\s|()\[\],]", expr, maxsplit=1)[0]
        if first in _RESERVED:
            continue
        if re.match(r"^[a-zA-Z_][a-zA-Z0-9_\.]*$", first):
            found.add(first)
    for m in re.finditer(
        r"\{\%\s*(?:if|elif)\s+([a-zA-Z_][a-zA-Z0-9_\.]*)\s*==", text
    ):
        found.add(m.group(1))
    return found


# ---------------------------------------------------------------------------
# Settings defaults / quiz items
# ---------------------------------------------------------------------------

def load_session_defaults() -> dict:
    if not SETTINGS_FILE.exists():
        return {}
    text = SETTINGS_FILE.read_text(encoding="utf-8")
    m = re.search(
        r"SESSION_CONFIG_DEFAULTS\s*=\s*dict\s*\((.*?)\n\)", text, re.DOTALL
    )
    if not m:
        return {}
    body = m.group(1)
    out: dict = {}
    for raw_line in body.split("\n"):
        line = raw_line.strip().rstrip(",")
        if not line or line.startswith("#"):
            continue
        mm = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+?)\s*,?$", line)
        if mm:
            try:
                out[mm.group(1)] = ast.literal_eval(mm.group(2))
            except Exception:
                out[mm.group(1)] = mm.group(2)
    return out


def load_quiz_items() -> list[dict]:
    if not QUIZ_ITEMS_FILE.exists():
        return []
    spec = importlib.util.spec_from_file_location(
        "_preview_quiz_items", QUIZ_ITEMS_FILE
    )
    if spec is None or spec.loader is None:
        return []
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return list(getattr(mod, "QUIZ_ITEMS", []))


# ---------------------------------------------------------------------------
# State load / save
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Tkinter popup
# ---------------------------------------------------------------------------

def run_tkinter_ui(
    detected_vars: list[str], defaults: dict, state: dict
) -> dict | None:
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception:
        return None

    treatments: list[str] = list(
        state.get("treatments") or ["Treatment 1", "Treatment 2"]
    )
    saved_values: dict = dict(state.get("values") or {})
    pdf_treatment = state.get("pdf_treatment") or (
        treatments[0] if treatments else "Treatment 1"
    )

    variables: list[str] = []
    for v in list(detected_vars) + list(saved_values.keys()):
        if v not in variables:
            variables.append(v)

    result: dict | None = None
    root = tk.Tk()
    root.title("Instructions preview — matrix setup")
    root.geometry("960x620")
    # Bring window to front on macOS (where Tk windows otherwise open behind Terminal).
    try:
        root.lift()
        root.attributes("-topmost", True)
        root.after(200, lambda: root.attributes("-topmost", False))
        root.focus_force()
    except Exception:
        pass

    container = ttk.Frame(root, padding=12)
    container.pack(fill="both", expand=True)

    ttk.Label(
        container,
        text=(
            "Set variable values per treatment column. "
            "Header cells are editable treatment names."
        ),
        wraplength=920,
    ).pack(anchor="w", pady=(0, 8))

    canvas = tk.Canvas(container, borderwidth=0, highlightthickness=0)
    grid_frame = ttk.Frame(canvas)
    vsb = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vsb.set)
    vsb.pack(side="right", fill="y")
    canvas.pack(side="top", fill="both", expand=True)
    canvas.create_window((0, 0), window=grid_frame, anchor="nw")
    grid_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
    )

    header_vars: list[tk.StringVar] = []
    row_name_vars: list[tk.StringVar] = []
    cell_vars: list[list[tk.StringVar]] = []

    def initial_for(var: str, col: int) -> str:
        sv = saved_values.get(var)
        if isinstance(sv, list) and col < len(sv) and sv[col] is not None:
            return str(sv[col])
        if var in defaults and col == 0:
            return str(defaults[var])
        return ""

    def render_grid() -> None:
        for c in grid_frame.winfo_children():
            c.destroy()
        header_vars.clear()
        row_name_vars.clear()
        cell_vars.clear()

        ttk.Label(
            grid_frame,
            text="Variable",
            font=("TkDefaultFont", 10, "bold"),
        ).grid(row=0, column=0, padx=4, pady=4, sticky="w")
        for col, name in enumerate(treatments):
            sv = tk.StringVar(value=name)
            header_vars.append(sv)
            ttk.Entry(grid_frame, textvariable=sv, width=18).grid(
                row=0, column=col + 1, padx=4, pady=4, sticky="ew"
            )

        for i, var in enumerate(variables):
            name_sv = tk.StringVar(value=var)
            row_name_vars.append(name_sv)
            ttk.Entry(grid_frame, textvariable=name_sv, width=22).grid(
                row=i + 1, column=0, padx=4, pady=2, sticky="ew"
            )
            row_cells: list[tk.StringVar] = []
            for col in range(len(treatments)):
                cv = tk.StringVar(value=initial_for(var, col))
                row_cells.append(cv)
                ttk.Entry(grid_frame, textvariable=cv, width=18).grid(
                    row=i + 1, column=col + 1, padx=4, pady=2, sticky="ew"
                )
            cell_vars.append(row_cells)

        canvas.configure(scrollregion=canvas.bbox("all"))

    def snapshot() -> dict:
        cur_treatments = [
            (hv.get().strip() or f"Treatment {i+1}")
            for i, hv in enumerate(header_vars)
        ]
        cur_values: dict = {}
        for i, sv in enumerate(row_name_vars):
            name = sv.get().strip()
            if not name:
                continue
            cur_values[name] = [cv.get() for cv in cell_vars[i]]
        return dict(treatments=cur_treatments, values=cur_values)

    def add_treatment() -> None:
        nonlocal treatments
        cur = snapshot()
        treatments = cur["treatments"] + [f"Treatment {len(cur['treatments'])+1}"]
        for k in cur["values"]:
            cur["values"][k] = cur["values"][k] + [""]
        saved_values.clear()
        saved_values.update(cur["values"])
        nonlocal_replace_variables(cur)
        render_grid()
        refresh_pdf_dropdown()

    def add_variable() -> None:
        cur = snapshot()
        saved_values.clear()
        saved_values.update(cur["values"])
        i = 1
        existing = set(cur["values"].keys())
        while f"var{i}" in existing:
            i += 1
        new_name = f"var{i}"
        saved_values[new_name] = [""] * len(treatments)
        nonlocal_replace_variables(snapshot_from_saved(cur["treatments"]))
        render_grid()

    def snapshot_from_saved(cur_treatments: list[str]) -> dict:
        return dict(treatments=cur_treatments, values=dict(saved_values))

    def nonlocal_replace_variables(cur: dict) -> None:
        nonlocal variables
        variables = list(cur["values"].keys())

    pdf_var = tk.StringVar(value=pdf_treatment)

    btn_row = ttk.Frame(container)
    btn_row.pack(fill="x", pady=(8, 0))
    ttk.Button(
        btn_row, text="Add treatment column", command=add_treatment
    ).pack(side="left", padx=(0, 6))
    ttk.Button(
        btn_row, text="Add variable row", command=add_variable
    ).pack(side="left", padx=(0, 6))
    ttk.Label(btn_row, text="PDF treatment:").pack(side="left", padx=(20, 4))
    pdf_dropdown = ttk.Combobox(
        btn_row, textvariable=pdf_var, state="readonly", width=22
    )
    pdf_dropdown.pack(side="left")

    def refresh_pdf_dropdown() -> None:
        cur = [
            (hv.get().strip() or f"Treatment {i+1}")
            for i, hv in enumerate(header_vars)
        ]
        pdf_dropdown["values"] = cur
        if pdf_var.get() not in cur and cur:
            pdf_var.set(cur[0])

    def on_generate() -> None:
        nonlocal result
        cur = snapshot()
        cur["pdf_treatment"] = pdf_var.get()
        result = cur
        root.destroy()

    ttk.Button(btn_row, text="Generate", command=on_generate).pack(side="right")

    render_grid()
    refresh_pdf_dropdown()
    root.mainloop()
    return result


# ---------------------------------------------------------------------------
# Browser-based matrix UI (fallback when tkinter is unavailable)
# ---------------------------------------------------------------------------

_WEB_FORM_TEMPLATE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<title>Instructions preview — matrix setup</title>
<style>
  :root {
    --border: #d0d7de;
    --bg: #f6f8fa;
    --primary: #0969da;
    --primary-hover: #0860c7;
    --muted: #57606a;
  }
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif;
    margin: 0; padding: 24px 28px; background: #fff; color: #1f2328;
    font-size: 14px;
  }
  h1 { margin: 0 0 4px; font-size: 22px; }
  p.lede { margin: 0 0 18px; color: var(--muted); }
  table.matrix { border-collapse: collapse; margin-bottom: 16px; }
  table.matrix th, table.matrix td {
    border: 1px solid var(--border); padding: 4px;
  }
  table.matrix th { background: var(--bg); font-weight: 600; }
  table.matrix input {
    border: none; background: transparent; padding: 6px 8px;
    font: inherit; width: 100%; min-width: 90px;
  }
  table.matrix input:focus { outline: 2px solid var(--primary); border-radius: 3px; }
  table.matrix th input { font-weight: 600; }
  table.matrix th.var-name input { font-weight: 500; }
  .row-actions { white-space: nowrap; }
  .row-actions button {
    background: transparent; border: none; color: var(--muted);
    cursor: pointer; padding: 4px 6px; font-size: 16px;
  }
  .row-actions button:hover { color: #cf222e; }
  .controls { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .controls label { display: flex; align-items: center; gap: 6px; }
  button.btn {
    padding: 6px 12px; border: 1px solid var(--border); background: #fff;
    border-radius: 6px; cursor: pointer; font: inherit;
  }
  button.btn:hover { background: var(--bg); }
  button.btn.primary {
    background: var(--primary); color: #fff; border-color: var(--primary);
    margin-left: auto;
  }
  button.btn.primary:hover { background: var(--primary-hover); }
  select { padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px; font: inherit; }
  .footer { margin-top: 14px; color: var(--muted); font-size: 12px; }
  #done-banner {
    display: none; padding: 16px; background: #dafbe1; border: 1px solid #2da44e;
    border-radius: 8px; margin-top: 14px;
  }
</style>
</head><body>
  <h1>Matrix setup</h1>
  <p class="lede">
    Set variable values per treatment column. Headers and variable names are editable.
    Click <strong>Generate</strong> when done; this tab will close itself.
  </p>
  <div id="matrix-wrap"></div>
  <div class="controls">
    <button id="add-treatment" type="button" class="btn">+ Treatment</button>
    <button id="add-variable"  type="button" class="btn">+ Variable</button>
    <label>PDF treatment <select id="pdf-treatment"></select></label>
    <button id="generate" type="button" class="btn primary">Generate</button>
  </div>
  <div id="done-banner">✓ Submitted. You can close this tab — previews are being written.</div>
  <p class="footer">Detected variables come from <code>intro/instructions_text.html</code> and <code>intro/prequiz_text.html</code>.</p>
<script>
  const INITIAL = __INITIAL_JSON__;
  const state = {
    treatments: INITIAL.treatments.slice(),
    values: {},
    pdf_treatment: INITIAL.pdf_treatment,
  };
  // Preserve insertion order of variables
  const varOrder = Object.keys(INITIAL.values);
  varOrder.forEach(v => {
    state.values[v] = INITIAL.values[v].slice();
    while (state.values[v].length < state.treatments.length) state.values[v].push("");
  });

  function render() {
    const wrap = document.getElementById('matrix-wrap');
    const treatments = state.treatments;
    const vars = Object.keys(state.values);

    let html = '<table class="matrix"><thead><tr><th>Variable</th>';
    treatments.forEach((t, i) => {
      html += `<th><input data-kind="treatment" data-i="${i}" value="${escapeHtml(t)}"></th>`;
    });
    html += '<th></th></tr></thead><tbody>';
    vars.forEach((v, vi) => {
      html += `<tr><th class="var-name"><input data-kind="varname" data-v="${escapeHtml(v)}" value="${escapeHtml(v)}"></th>`;
      treatments.forEach((_, ci) => {
        const val = (state.values[v][ci] === undefined || state.values[v][ci] === null) ? '' : state.values[v][ci];
        html += `<td><input data-kind="cell" data-v="${escapeHtml(v)}" data-c="${ci}" value="${escapeHtml(String(val))}"></td>`;
      });
      html += `<td class="row-actions"><button type="button" data-del-var="${escapeHtml(v)}" title="Delete this variable">✕</button></td>`;
      html += '</tr>';
    });
    html += '</tbody></table>';
    wrap.innerHTML = html;

    // PDF treatment dropdown
    const sel = document.getElementById('pdf-treatment');
    sel.innerHTML = treatments
      .map(t => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`)
      .join('');
    if (treatments.includes(state.pdf_treatment)) sel.value = state.pdf_treatment;
    else { state.pdf_treatment = treatments[0] || ''; sel.value = state.pdf_treatment; }

    bindHandlers();
  }

  function bindHandlers() {
    document.querySelectorAll('input[data-kind="treatment"]').forEach(el => {
      el.addEventListener('input', e => {
        const i = Number(el.dataset.i);
        state.treatments[i] = el.value;
        const sel = document.getElementById('pdf-treatment');
        const prev = sel.value;
        sel.innerHTML = state.treatments
          .map(t => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`)
          .join('');
        if (state.treatments.includes(prev)) sel.value = prev;
      });
    });
    document.querySelectorAll('input[data-kind="varname"]').forEach(el => {
      el.addEventListener('change', e => {
        const oldName = el.dataset.v;
        const newName = el.value.trim();
        if (!newName || newName === oldName) { render(); return; }
        if (state.values[newName] !== undefined) { alert(`Variable "${newName}" already exists.`); render(); return; }
        const newValues = {};
        Object.keys(state.values).forEach(k => {
          newValues[k === oldName ? newName : k] = state.values[k];
        });
        state.values = newValues;
        render();
      });
    });
    document.querySelectorAll('input[data-kind="cell"]').forEach(el => {
      el.addEventListener('input', e => {
        const v = el.dataset.v;
        const c = Number(el.dataset.c);
        state.values[v][c] = el.value;
      });
    });
    document.querySelectorAll('button[data-del-var]').forEach(btn => {
      btn.addEventListener('click', () => {
        delete state.values[btn.dataset.delVar];
        render();
      });
    });
    document.getElementById('pdf-treatment').addEventListener('change', e => {
      state.pdf_treatment = e.target.value;
    });
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c =>
      ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  document.getElementById('add-treatment').addEventListener('click', () => {
    const n = state.treatments.length + 1;
    state.treatments.push(`Treatment ${n}`);
    Object.keys(state.values).forEach(v => state.values[v].push(''));
    render();
  });

  document.getElementById('add-variable').addEventListener('click', () => {
    let i = 1;
    while (state.values[`var${i}`] !== undefined) i++;
    state.values[`var${i}`] = new Array(state.treatments.length).fill('');
    render();
  });

  document.getElementById('generate').addEventListener('click', async () => {
    document.getElementById('generate').disabled = true;
    try {
      const resp = await fetch('/submit', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(state),
      });
      if (resp.ok) {
        document.getElementById('done-banner').style.display = 'block';
        setTimeout(() => window.close(), 600);
      } else {
        alert('Submit failed: ' + (await resp.text()));
        document.getElementById('generate').disabled = false;
      }
    } catch (err) {
      alert('Submit error: ' + err);
      document.getElementById('generate').disabled = false;
    }
  });

  render();
</script>
</body></html>
"""


def _build_web_initial_state(
    detected_vars: list[str], defaults: dict, saved_state: dict
) -> dict:
    treatments = list(
        saved_state.get("treatments") or ["Treatment 1", "Treatment 2"]
    )
    saved_values: dict = dict(saved_state.get("values") or {})
    values: dict = {}
    for v in detected_vars:
        if v in saved_values:
            row = list(saved_values[v])
            while len(row) < len(treatments):
                row.append("")
            values[v] = row
        else:
            seed = ""
            if v in defaults:
                seed = str(defaults[v])
            values[v] = [seed] + [""] * (len(treatments) - 1)
    for v, row in saved_values.items():
        if v not in values:
            row = list(row)
            while len(row) < len(treatments):
                row.append("")
            values[v] = row
    return dict(
        treatments=treatments,
        values=values,
        pdf_treatment=saved_state.get("pdf_treatment") or treatments[0],
    )


def run_web_ui(
    detected_vars: list[str], defaults: dict, saved_state: dict,
    *, open_browser: bool = True
) -> dict | None:
    """Spin up a local HTTP server with the matrix form. Blocks until the
    user clicks Generate (POSTs JSON) or closes the tab. Returns the same
    dict shape as run_tkinter_ui, or None if no submission was made."""
    import http.server
    import json as _json
    import socket
    import threading
    import webbrowser

    initial = _build_web_initial_state(detected_vars, defaults, saved_state)
    initial_json = _json.dumps(initial, ensure_ascii=False)
    form_html = _WEB_FORM_TEMPLATE.replace("__INITIAL_JSON__", initial_json)

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    result: dict = {"state": None}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in ("/", "/index.html"):
                body = form_html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            if self.path == "/submit":
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length).decode("utf-8")
                try:
                    parsed = _json.loads(raw)
                except Exception as exc:
                    self.send_response(400)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(f"bad JSON: {exc}".encode())
                    return
                result["state"] = parsed
                body = (
                    b"<!doctype html><meta charset='utf-8'>"
                    b"<body style='font-family:system-ui;padding:40px;text-align:center'>"
                    b"<h2>\xe2\x9c\x93 Submitted</h2>"
                    b"<p>You can close this tab.</p></body>"
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                threading.Thread(target=httpd.shutdown, daemon=True).start()
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args, **kwargs):
            pass  # silence default access logging

    httpd = http.server.HTTPServer(("127.0.0.1", port), Handler)
    url = f"http://localhost:{port}/"
    sys.stderr.write(f"Opening matrix popup in your browser: {url}\n")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
    return result["state"]


# ---------------------------------------------------------------------------
# Substitution helpers
# ---------------------------------------------------------------------------

def _coerce_value(raw):
    if raw is None or raw == "":
        return ""
    try:
        return int(raw)
    except (ValueError, TypeError):
        pass
    try:
        return float(raw)
    except (ValueError, TypeError):
        pass
    return raw


def build_context(state: dict, col: int) -> dict:
    ctx: dict = {}
    for var, row in state.get("values", {}).items():
        if col >= len(row):
            continue
        value = _coerce_value(row[col])
        parts = var.split(".")
        cur = ctx
        for i, p in enumerate(parts):
            if i == len(parts) - 1:
                cur[p] = value
            else:
                if p not in cur or not isinstance(cur[p], dict):
                    cur[p] = {}
                cur = cur[p]
    return ctx


def transform_variables_only(text: str) -> str:
    def repl(m: re.Match) -> str:
        expr = m.group(1).strip()
        if re.match(r"^(block|endblock)\b", expr):
            return ""
        first = re.split(r"[\s|()\[\],]", expr, maxsplit=1)[0]
        if first in _RESERVED:
            return m.group(0)
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_\.]*$", first):
            return m.group(0)
        esc = html_module.escape(first)
        return (
            f'<span class="preview-var" data-var="{esc}">'
            f"‹{esc}›</span>"
        )
    return re.sub(r"\{\{\s*([^\}]+?)\s*\}\}", repl, text)


def transform_for_client(text: str) -> str:
    cond_pattern = re.compile(
        r"\{\%\s*if\s+([a-zA-Z_][a-zA-Z0-9_\.]*)\s*==\s*([^\%]+?)\s*\%\}"
        r"(.*?)"
        r"\{\%\s*endif\s*\%\}",
        re.DOTALL,
    )

    def repl_cond(m: re.Match) -> str:
        var = m.group(1)
        first_val = m.group(2).strip().strip("\"'")
        inner = m.group(3)
        elif_re = re.compile(
            r"\{\%\s*elif\s+" + re.escape(var) + r"\s*==\s*([^\%]+?)\s*\%\}"
        )
        branches: list[tuple[str, str]] = []
        cur_val = first_val
        last = 0
        for em in elif_re.finditer(inner):
            branches.append((cur_val, inner[last:em.start()]))
            cur_val = em.group(1).strip().strip("\"'")
            last = em.end()
        branches.append((cur_val, inner[last:]))

        out = [f'<span class="preview-cond" data-cond-var="{html_module.escape(var)}">']
        for val, content in branches:
            content_t = transform_variables_only(content)
            out.append(
                f'<span class="preview-cond-branch" '
                f'data-cond-val="{html_module.escape(val)}">{content_t}</span>'
            )
        out.append("</span>")
        return "".join(out)

    text = cond_pattern.sub(repl_cond, text)
    text = transform_variables_only(text)
    return text


def render_for_pdf(text: str, context: dict) -> str:
    """Replace {{var}} with literal '‹var›' then evaluate {% if %} via Jinja2."""
    def repl_var(m: re.Match) -> str:
        expr = m.group(1).strip()
        if re.match(r"^(block|endblock)\b", expr):
            return ""
        first = re.split(r"[\s|()\[\],]", expr, maxsplit=1)[0]
        if first in _RESERVED:
            return m.group(0)
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_\.]*$", first):
            return m.group(0)
        return f"‹{html_module.escape(first)}›"

    text = re.sub(r"\{\{\s*([^\}]+?)\s*\}\}", repl_var, text)

    from jinja2 import Environment, BaseLoader, Undefined

    env = Environment(
        loader=BaseLoader(),
        autoescape=False,
        undefined=Undefined,
    )
    try:
        return env.from_string(text).render(**context)
    except Exception as exc:
        return (
            f"<!-- preview generator: jinja error: "
            f"{html_module.escape(str(exc))} -->\n{text}"
        )


# ---------------------------------------------------------------------------
# HTML composition
# ---------------------------------------------------------------------------

def matrix_table_html(state: dict, table_id: str = "preview-matrix-table") -> str:
    treatments = state.get("treatments", [])
    values = state.get("values", {})
    headers = "".join(
        f"<th>{html_module.escape(t)}</th>" for t in treatments
    )
    rows = []
    for var, row in values.items():
        cells = "".join(
            f"<td>{html_module.escape(str(row[i]) if i < len(row) else '')}</td>"
            for i in range(len(treatments))
        )
        rows.append(f"<tr><th>{html_module.escape(var)}</th>{cells}</tr>")
    if not values:
        rows = [
            f'<tr><td colspan="{len(treatments)+1}" '
            f'style="text-align:center;color:#888">(no variables defined)</td></tr>'
        ]
    return (
        f'<table id="{table_id}" class="preview-matrix-table">'
        f"<thead><tr><th>Variable</th>{headers}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )


def wrap_card(
    inner_html: str,
    header: str | None = "Instructions",
    *,
    show_controls: bool = True,
    extra_class: str = "",
    extra_attrs: str = "",
    header_text: str = "",
) -> str:
    controls = ""
    if show_controls:
        controls = (
            '<div class="instruction-controls">'
            '<button type="button" class="next-button preview-nav-prev">Back</button>'
            '<button type="button" class="next-button preview-nav-next">Next</button>'
            "</div>"
        )
    # header=None mirrors the live instructing.html: no fixed page title —
    # each instruction block's own <h2> is the step title.
    header_html = ""
    if header is not None:
        header_html = (
            '<div class="experimental-header">'
            f'<h2 class="header-title">{html_module.escape(header)}</h2>'
            f'<p class="header-text">{header_text}</p>'
            '</div>'
        )
    cls = "experimental-screen preview-screen " + extra_class
    return (
        f'<section class="{cls.strip()}" {extra_attrs}>'
        '<div class="screen-card">'
        f'{header_html}'
        '<div class="experimental-content">'
        '<div class="instructions">'
        '<div class="instruction-wrapper">'
        f"{inner_html}"
        "</div>"
        f"{controls}"
        "</div>"
        "</div>"
        "</div>"
        "</section>"
    )


def quiz_inner_html(quiz_items: list[dict]) -> str:
    if not quiz_items:
        return '<p style="color:#888">(No quiz items defined in intro/quiz_items.py)</p>'
    parts = []
    for item in quiz_items:
        field = html_module.escape(item["field"])
        prompt = html_module.escape(item["prompt"])
        options = "".join(
            f'<div class="form-check">'
            f'<input type="radio" name="{field}" value="{html_module.escape(c)}" disabled>'
            f'<label>{html_module.escape(c)}</label>'
            f"</div>"
            for c in item["choices"]
        )
        parts.append(f"<p>{prompt}</p><div>{options}</div>")
    return (
        '<div class="quiz-block">'
        '<div class="stacked-form">'
        + "".join(parts)
        + "</div>"
        "</div>"
        '<div class="button-row">'
        '<input type="submit" value="Next" class="next-button" disabled>'
        "</div>"
    )


# ---------------------------------------------------------------------------
# Preview CSS / JS (shared)
# ---------------------------------------------------------------------------

PREVIEW_EXTRA_CSS = r"""
/* ---- preview-only styles ---- */
body.preview-long .instruction-block,
body.preview-pdf .instruction-block {
    display: block !important;
}
body.preview-long .preview-screen,
body.preview-pdf .preview-screen {
    margin-bottom: 24px;
}

/* matrix panel */
.preview-matrix-wrap {
    max-width: 1100px;
    margin: 24px auto 8px;
    padding: 16px 20px;
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    box-shadow: 0 8px 16px rgba(0,0,0,0.05);
}
.preview-matrix-wrap h3 {
    margin: 0 0 10px;
    font-size: 18px;
    color: #333;
}
.preview-matrix-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
    color: #333;
}
.preview-matrix-table th,
.preview-matrix-table td {
    border: 1px solid #e5e7eb;
    padding: 6px 10px;
    text-align: left;
}
.preview-matrix-table thead th {
    background: #f5f7fa;
}
.preview-matrix-table tbody th {
    background: #fafafa;
    font-weight: 600;
}

/* treatment dropdown (long view) */
.preview-treatment-bar {
    max-width: 1100px;
    margin: 12px auto 24px;
    padding: 10px 16px;
    display: flex;
    align-items: center;
    gap: 12px;
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
}
.preview-treatment-bar label {
    font-weight: 600;
    color: #333;
}
.preview-treatment-bar select {
    padding: 6px 10px;
    border: 1px solid #ccc;
    border-radius: 6px;
    font-size: 15px;
}

/* placeholder pill for unfilled variables */
.preview-var {
    display: inline-block;
    color: #006080;
    background: rgba(0, 140, 186, 0.08);
    padding: 0 4px;
    border-radius: 4px;
    font-feature-settings: "tnum";
}

/* floating switcher (interactive) */
.preview-switcher {
    position: fixed;
    top: 16px;
    right: 16px;
    z-index: 1000;
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 10px 12px;
    background: rgba(255,255,255,0.94);
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    box-shadow: 0 6px 14px rgba(0,0,0,0.08);
    backdrop-filter: blur(4px);
    font-size: 14px;
    max-width: 240px;
}
.preview-switcher .preview-switcher-title {
    font-size: 12px;
    font-weight: 600;
    color: #555;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-bottom: 2px;
}
.preview-switcher button {
    padding: 6px 10px;
    border: 1px solid #ccc;
    border-radius: 6px;
    background: #fff;
    cursor: pointer;
    text-align: left;
    font-size: 14px;
    color: #333;
}
.preview-switcher button.active {
    background: #008cba;
    color: #fff;
    border-color: #007bb5;
}
.preview-switcher .preview-switcher-secondary {
    display: flex;
    gap: 6px;
    margin-top: 4px;
}
.preview-switcher .preview-switcher-secondary button {
    flex: 1;
    text-align: center;
    font-size: 13px;
    padding: 5px 8px;
}

/* matrix overlay (interactive) */
.preview-matrix-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.4);
    display: none;
    align-items: center;
    justify-content: center;
    z-index: 1100;
    padding: 24px;
}
.preview-matrix-overlay.is-visible {
    display: flex;
}
.preview-matrix-overlay-inner {
    background: #fff;
    border-radius: 12px;
    padding: 24px;
    max-width: 90vw;
    max-height: 90vh;
    overflow: auto;
    box-shadow: 0 16px 32px rgba(0,0,0,0.2);
}
.preview-matrix-overlay-inner h3 {
    margin: 0 0 12px;
}
.preview-matrix-overlay-close {
    margin-top: 16px;
    padding: 8px 16px;
    border: 1px solid #ccc;
    border-radius: 6px;
    background: #fff;
    cursor: pointer;
}

/* interactive screen visibility */
body.preview-interactive .preview-screen { display: none; }
body.preview-interactive .preview-screen.is-active { display: flex; }

/* setup screen styling */
.preview-setup-form {
    display: flex;
    flex-direction: column;
    gap: 14px;
    align-items: center;
    margin-top: 12px;
}
.preview-setup-form fieldset {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 12px 16px;
    text-align: left;
    min-width: 280px;
}
.preview-setup-form legend {
    font-weight: 600;
    padding: 0 6px;
    color: #333;
}
.preview-setup-form label {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 0;
    cursor: pointer;
    font-size: 16px;
}

/* keep card buttons inert-looking when disabled */
.preview-long .next-button[disabled],
.preview-pdf .next-button[disabled] {
    opacity: 0.55;
    cursor: default;
}

/* PDF media tweaks */
@media print {
    .preview-treatment-bar, .preview-switcher,
    .preview-matrix-overlay { display: none !important; }
    .preview-screen { page-break-inside: avoid; margin-bottom: 16px; }
    body { background: #fff; }
}
"""


# ---------------------------------------------------------------------------
# JS for long view
# ---------------------------------------------------------------------------

JS_LONG = r"""
(function () {
    var data = __PREVIEW_DATA__;
    var current = 0;

    function applyTreatment(idx) {
        current = idx;
        document.querySelectorAll('.preview-var').forEach(function (el) {
            var v = el.dataset.var;
            var row = data.values[v];
            var val = row && idx < row.length ? row[idx] : undefined;
            if (val !== undefined && val !== null && String(val).length > 0) {
                el.textContent = String(val);
                el.classList.remove('is-empty');
            } else {
                el.textContent = '‹' + v + '›';
                el.classList.add('is-empty');
            }
        });
        document.querySelectorAll('.preview-cond').forEach(function (el) {
            var v = el.dataset.condVar;
            var row = data.values[v];
            var cur = row && idx < row.length ? String(row[idx]) : '';
            var matched = false;
            el.querySelectorAll('.preview-cond-branch').forEach(function (br) {
                if (!matched && String(br.dataset.condVal) === cur) {
                    br.style.display = '';
                    matched = true;
                } else {
                    br.style.display = 'none';
                }
            });
            if (!matched) {
                var first = el.querySelector('.preview-cond-branch');
                if (first) first.style.display = '';
            }
        });
        var sel = document.getElementById('preview-treatment-select');
        if (sel) sel.value = String(idx);
    }

    document.addEventListener('DOMContentLoaded', function () {
        var sel = document.getElementById('preview-treatment-select');
        if (sel) {
            sel.addEventListener('change', function () {
                applyTreatment(Number(sel.value));
            });
        }
        applyTreatment(0);
    });
})();
"""


# ---------------------------------------------------------------------------
# JS for interactive view
# ---------------------------------------------------------------------------

JS_INTERACTIVE = r"""
(function () {
    var data = __PREVIEW_DATA__;
    var currentTreatment = 0;

    function applyTreatment(idx) {
        currentTreatment = idx;
        document.querySelectorAll('.preview-var').forEach(function (el) {
            var v = el.dataset.var;
            var row = data.values[v];
            var val = row && idx < row.length ? row[idx] : undefined;
            if (val !== undefined && val !== null && String(val).length > 0) {
                el.textContent = String(val);
                el.classList.remove('is-empty');
            } else {
                el.textContent = '‹' + v + '›';
                el.classList.add('is-empty');
            }
        });
        document.querySelectorAll('.preview-cond').forEach(function (el) {
            var v = el.dataset.condVar;
            var row = data.values[v];
            var cur = row && idx < row.length ? String(row[idx]) : '';
            var matched = false;
            el.querySelectorAll('.preview-cond-branch').forEach(function (br) {
                if (!matched && String(br.dataset.condVal) === cur) {
                    br.style.display = '';
                    matched = true;
                } else {
                    br.style.display = 'none';
                }
            });
            if (!matched) {
                var first = el.querySelector('.preview-cond-branch');
                if (first) first.style.display = '';
            }
        });
        document.querySelectorAll('.preview-switcher [data-treatment]').forEach(function (btn) {
            btn.classList.toggle('active', Number(btn.dataset.treatment) === idx);
        });
    }

    var screens = [];
    var currentScreen = 0;

    function showScreen(i) {
        if (i < 0 || i >= screens.length) return;
        currentScreen = i;
        screens.forEach(function (s, j) {
            s.classList.toggle('is-active', j === i);
        });
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    function resetToSetup() {
        showScreen(0);
    }

    document.addEventListener('DOMContentLoaded', function () {
        screens = Array.prototype.slice.call(
            document.querySelectorAll('.preview-screen')
        );

        // Switcher buttons
        document.querySelectorAll('.preview-switcher [data-treatment]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                applyTreatment(Number(btn.dataset.treatment));
            });
        });

        var resetBtn = document.getElementById('preview-reset');
        if (resetBtn) {
            resetBtn.addEventListener('click', resetToSetup);
        }

        // Matrix toggle
        var matrixToggle = document.getElementById('preview-matrix-toggle');
        var overlay = document.getElementById('preview-matrix-overlay');
        if (matrixToggle && overlay) {
            matrixToggle.addEventListener('click', function () {
                overlay.classList.add('is-visible');
            });
            overlay.addEventListener('click', function (e) {
                if (e.target === overlay) overlay.classList.remove('is-visible');
            });
            var closeBtn = overlay.querySelector('.preview-matrix-overlay-close');
            if (closeBtn) closeBtn.addEventListener('click', function () {
                overlay.classList.remove('is-visible');
            });
        }

        // Setup screen: pick treatment + begin
        var beginBtn = document.getElementById('preview-begin');
        if (beginBtn) {
            beginBtn.addEventListener('click', function () {
                var picked = document.querySelector(
                    '.preview-setup-form input[name="preview-treatment-pick"]:checked'
                );
                if (picked) applyTreatment(Number(picked.value));
                showScreen(1);
            });
        }

        // Back/Next buttons inside each card
        document.querySelectorAll('.preview-screen').forEach(function (screen, idx) {
            var prev = screen.querySelector('.preview-nav-prev');
            var next = screen.querySelector('.preview-nav-next');
            if (prev) {
                prev.addEventListener('click', function () {
                    if (currentScreen <= 1) {
                        // first instruction or setup -> nothing
                        return;
                    }
                    showScreen(currentScreen - 1);
                });
            }
            if (next) {
                next.addEventListener('click', function () {
                    if (currentScreen < screens.length - 1) {
                        showScreen(currentScreen + 1);
                    }
                });
            }
        });

        // Keyboard arrows
        document.addEventListener('keydown', function (e) {
            if (['INPUT', 'TEXTAREA', 'SELECT'].indexOf(
                    (e.target.tagName || '').toUpperCase()) !== -1) return;
            if (e.key === 'ArrowLeft') {
                if (currentScreen > 1) showScreen(currentScreen - 1);
            } else if (e.key === 'ArrowRight') {
                if (currentScreen < screens.length - 1) showScreen(currentScreen + 1);
            }
        });

        applyTreatment(0);
        showScreen(0);
    });
})();
"""


# ---------------------------------------------------------------------------
# Build long HTML
# ---------------------------------------------------------------------------

def build_long_html(
    blocks: list[dict],
    quiz_items: list[dict],
    state: dict,
    css: str,
) -> str:
    transformed = []
    for b in blocks:
        inner = transform_for_client(b["inner"])
        cls = b.get("classes", "instruction-block")
        block_html = f'<div class="{cls}">{inner}</div>'
        transformed.append(
            wrap_card(block_html, header=None, show_controls=True)
        )

    transformed.append(
        wrap_card(quiz_inner_html(quiz_items), header="Quiz",
                  show_controls=False,
                  header_text="Answer the questions below before starting the experiment.")
    )

    treatments = state.get("treatments", [])
    options = "".join(
        f'<option value="{i}">{html_module.escape(t)}</option>'
        for i, t in enumerate(treatments)
    )
    matrix_block = (
        '<div class="preview-matrix-wrap">'
        '<h3>Treatment matrix</h3>'
        + matrix_table_html(state)
        + "</div>"
        '<div class="preview-treatment-bar">'
        '<label for="preview-treatment-select">Treatment</label>'
        f'<select id="preview-treatment-select">{options}</select>'
        "</div>"
    )

    data_blob = json.dumps(state, ensure_ascii=False)
    js = JS_LONG.replace("__PREVIEW_DATA__", data_blob)

    return _wrap_document(
        title="Instructions preview (long)",
        body_class="preview-long",
        css=css + "\n" + PREVIEW_EXTRA_CSS,
        body_html=matrix_block + "\n".join(transformed),
        script=js,
    )


# ---------------------------------------------------------------------------
# Build interactive HTML
# ---------------------------------------------------------------------------

def build_interactive_html(
    blocks: list[dict],
    quiz_items: list[dict],
    state: dict,
    css: str,
) -> str:
    treatments = state.get("treatments", [])

    # Setup card (screen 0)
    radio_html = "".join(
        f'<label><input type="radio" name="preview-treatment-pick" value="{i}"'
        f'{" checked" if i == 0 else ""}> {html_module.escape(t)}</label>'
        for i, t in enumerate(treatments)
    )
    setup_inner = (
        '<p style="font-size:17px;color:#555;">'
        'This is a preview of the instructions. Pick a treatment to begin; '
        'you can switch at any time from the panel in the top-right corner.'
        '</p>'
        '<div class="preview-matrix-wrap" style="margin:8px 0 0;">'
        '<h3>Treatment matrix</h3>'
        + matrix_table_html(state, table_id="preview-matrix-setup-table") +
        '</div>'
        '<form class="preview-setup-form" onsubmit="return false;">'
        '<fieldset>'
        '<legend>Start with treatment</legend>'
        + radio_html +
        '</fieldset>'
        '<button type="button" id="preview-begin" class="next-button" '
        'style="margin-top:4px;">Begin</button>'
        '</form>'
    )
    setup_card = wrap_card(
        setup_inner,
        header="Preview setup",
        show_controls=False,
        extra_class="preview-setup-screen",
    )

    # Instruction + prequiz + quiz cards
    transformed_cards = []
    for b in blocks:
        inner = transform_for_client(b["inner"])
        cls = b.get("classes", "instruction-block")
        block_html = f'<div class="{cls}">{inner}</div>'
        transformed_cards.append(
            wrap_card(block_html, header=None, show_controls=True)
        )

    transformed_cards.append(
        wrap_card(quiz_inner_html(quiz_items), header="Quiz",
                  show_controls=False,
                  header_text="Answer the questions below before starting the experiment.")
    )

    treatment_buttons = "".join(
        f'<button data-treatment="{i}">{html_module.escape(t)}</button>'
        for i, t in enumerate(treatments)
    )

    switcher = (
        '<div class="preview-switcher" aria-label="Preview controls">'
        '<div class="preview-switcher-title">Treatment</div>'
        + treatment_buttons +
        '<div class="preview-switcher-secondary">'
        '<button id="preview-reset" type="button" title="Return to setup screen">Reset</button>'
        '<button id="preview-matrix-toggle" type="button">Show matrix</button>'
        '</div>'
        '</div>'
    )

    matrix_overlay = (
        '<div id="preview-matrix-overlay" class="preview-matrix-overlay">'
        '<div class="preview-matrix-overlay-inner">'
        '<h3>Treatment matrix</h3>'
        + matrix_table_html(state, table_id="preview-matrix-overlay-table") +
        '<button type="button" class="preview-matrix-overlay-close">Close</button>'
        '</div>'
        '</div>'
    )

    body_html = (
        switcher
        + matrix_overlay
        + setup_card
        + "\n".join(transformed_cards)
    )

    data_blob = json.dumps(state, ensure_ascii=False)
    js = JS_INTERACTIVE.replace("__PREVIEW_DATA__", data_blob)

    return _wrap_document(
        title="Instructions preview (interactive)",
        body_class="preview-interactive",
        css=css + "\n" + PREVIEW_EXTRA_CSS,
        body_html=body_html,
        script=js,
    )


# ---------------------------------------------------------------------------
# Build PDF HTML (rendered to PDF by Playwright)
# ---------------------------------------------------------------------------

def build_pdf_html(
    blocks: list[dict],
    quiz_items: list[dict],
    state: dict,
    css: str,
    pdf_col: int,
) -> str:
    ctx = build_context(state, pdf_col)

    rendered_cards = []
    for b in blocks:
        rendered_inner = render_for_pdf(b["inner"], ctx)
        cls = b.get("classes", "instruction-block")
        block_html = f'<div class="{cls}">{rendered_inner}</div>'
        rendered_cards.append(
            wrap_card(block_html, header=None, show_controls=True)
        )

    rendered_cards.append(
        wrap_card(quiz_inner_html(quiz_items), header="Quiz",
                  show_controls=False,
                  header_text="Answer the questions below before starting the experiment.")
    )

    matrix_block = (
        '<div class="preview-matrix-wrap">'
        '<h3>Treatment matrix '
        f'(PDF treatment: {html_module.escape(state.get("treatments", ["?"])[pdf_col] if pdf_col < len(state.get("treatments", [])) else "?")})</h3>'
        + matrix_table_html(state) +
        "</div>"
    )

    return _wrap_document(
        title="Instructions preview (PDF)",
        body_class="preview-pdf preview-long",
        css=css + "\n" + PREVIEW_EXTRA_CSS,
        body_html=matrix_block + "\n".join(rendered_cards),
        script="",
    )


def _wrap_document(
    *, title: str, body_class: str, css: str, body_html: str, script: str
) -> str:
    script_tag = f"<script>{script}</script>" if script else ""
    return (
        "<!DOCTYPE html>\n<html lang=\"en\"><head>"
        f"<meta charset=\"utf-8\"><title>{html_module.escape(title)}</title>"
        f"<style>{css}</style>"
        f"</head><body class=\"{body_class}\">"
        f"{body_html}"
        f"{script_tag}"
        "</body></html>"
    )


# ---------------------------------------------------------------------------
# PDF rendering via Playwright
# ---------------------------------------------------------------------------

def render_pdf(html: str, output_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        page = context.new_page()
        page.set_content(html, wait_until="load")
        page.emulate_media(media="print")
        page.pdf(
            path=str(output_path),
            format="A4",
            print_background=True,
            margin={"top": "16mm", "bottom": "16mm",
                    "left": "12mm", "right": "12mm"},
        )
        browser.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _tkinter_can_open() -> bool:
    """Importable AND can actually open a window in this environment.

    On macOS DISPLAY is never set (tkinter uses Cocoa, not X11), so we can't
    use DISPLAY as a proxy for 'no GUI'. The reliable check is to try opening
    a hidden root window and destroy it.
    """
    try:
        import tkinter as tk
    except Exception:
        return False
    try:
        probe = tk.Tk()
        probe.withdraw()
        probe.destroy()
        return True
    except Exception:
        return False


def _build_template_state(
    detected_vars: list[str], defaults: dict, saved_state: dict
) -> dict:
    """Build a starter state JSON for the headless fallback path."""
    treatments = saved_state.get("treatments") or ["Treatment 1", "Treatment 2"]
    saved_values = saved_state.get("values") or {}
    values: dict = {}
    # Pre-populate detected vars
    for v in detected_vars:
        if v in saved_values:
            row = list(saved_values[v])
            while len(row) < len(treatments):
                row.append("")
            values[v] = row
        else:
            default = defaults.get(v, "")
            values[v] = [str(default) if default != "" else ""] + [""] * (
                len(treatments) - 1
            )
    # Keep any user-added vars from prior state
    for v, row in saved_values.items():
        if v not in values:
            values[v] = list(row)
    return dict(
        treatments=treatments,
        values=values,
        pdf_treatment=saved_state.get("pdf_treatment") or treatments[0],
    )


def _write_template_and_exit(
    detected_vars: list[str], defaults: dict, saved_state: dict
) -> int:
    template = _build_template_state(detected_vars, defaults, saved_state)
    STATE_FILE.write_text(
        json.dumps(template, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    sys.stdout.write(
        "tkinter popup unavailable (or skipped). A pre-filled state file\n"
        f"has been written to: {STATE_FILE}\n\n"
        "Edit that file to set treatment column names and variable values,\n"
        "then re-run the script. On the next run the existing state will be\n"
        "used directly (no popup needed).\n\n"
        "Schema:\n"
        '  {"treatments": ["Row player", "Column player"],\n'
        '   "values": {"role": ["row", "column"], "stag_payoff": ["4", "4"]},\n'
        '   "pdf_treatment": "Row player"}\n'
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate Instructions preview HTML/PDF outputs."
    )
    parser.add_argument(
        "--no-popup",
        action="store_true",
        help=(
            "Skip the tkinter popup; write a pre-filled JSON template and "
            "exit so it can be edited and re-run with --config."
        ),
    )
    parser.add_argument(
        "--config",
        default=None,
        metavar="PATH",
        help=(
            "Path to a JSON config that fully specifies treatments and values. "
            "Bypasses the popup."
        ),
    )
    args = parser.parse_args()

    check_dependencies()

    # Detect content
    blocks = parse_blocks(INSTRUCTIONS_HTML) + parse_blocks(PREQUIZ_HTML)
    quiz_items = load_quiz_items()
    defaults = load_session_defaults()

    detected = set()
    for b in blocks:
        detected |= extract_variables(b["inner"])
    detected_vars = sorted(detected)

    saved_state = load_state()

    # --config bypasses popup entirely
    if args.config:
        cfg_path = Path(args.config)
        if not cfg_path.is_absolute():
            cfg_path = PROJECT_ROOT / cfg_path
        if not cfg_path.exists():
            sys.stderr.write(f"ERROR: config file not found: {cfg_path}\n")
            return 1
        try:
            state = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception as exc:
            sys.stderr.write(f"ERROR: could not parse {cfg_path}: {exc}\n")
            return 1
    elif args.no_popup:
        # Explicit no-popup: reuse existing state if usable, else write a
        # template and exit so the user can edit and re-run.
        if saved_state.get("treatments") and saved_state.get("values"):
            state = saved_state
        else:
            return _write_template_and_exit(
                detected_vars, defaults, saved_state
            )
    else:
        # Default: popup mode. Try tkinter first (native feel); if it can't
        # open a window in this environment, silently fall back to the
        # browser-based form. No tkinter? No problem — the user never sees
        # an error, just a browser tab.
        if _tkinter_can_open():
            ui_result = run_tkinter_ui(detected_vars, defaults, saved_state)
        else:
            ui_result = run_web_ui(detected_vars, defaults, saved_state)
        if ui_result is None:
            sys.stderr.write("Popup closed without Generate; nothing written.\n")
            return 1
        state = ui_result

    # Determine PDF treatment column index
    treatments = state.get("treatments", ["Treatment 1"])
    pdf_name = state.get("pdf_treatment") or treatments[0]
    if pdf_name in treatments:
        pdf_col = treatments.index(pdf_name)
    else:
        pdf_col = 0
        state["pdf_treatment"] = treatments[0]

    save_state(state)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    css = inline_css()

    long_html = build_long_html(blocks, quiz_items, state, css)
    interactive_html = build_interactive_html(blocks, quiz_items, state, css)
    pdf_html = build_pdf_html(blocks, quiz_items, state, css, pdf_col)

    (OUT_DIR / LONG_HTML_NAME).write_text(long_html, encoding="utf-8")
    (OUT_DIR / INTERACTIVE_HTML_NAME).write_text(
        interactive_html, encoding="utf-8"
    )

    # PDF
    check_chromium()
    render_pdf(pdf_html, OUT_DIR / PDF_NAME)
    return 0


if __name__ == "__main__":
    sys.exit(main())
