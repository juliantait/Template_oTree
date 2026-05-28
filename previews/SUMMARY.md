# Instructions preview generator

> **Worked example.** This template ships with a working **Stag Hunt** example
> in `intro/instructions_text.html` to demonstrate variable substitution and
> treatment-conditional content. A single treatment variable, `treatment`
> (assigned in `before/treatment_assignment.py` to `"row"` or `"column"`),
> drives the role-specific instructions; the payoffs are fixed constants on
> `intro.C`. To make your own experiment, replace `intro/instructions_text.html`
> and the matching wiring in `intro/__init__.py`'s `vars_for_template`.

`generate_instructions_preview.py` (in this directory) produces three
self-contained preview files alongside it:

- `instructions_preview_long.html` — every instruction block stacked vertically,
  each inside the live `.screen-card` chrome; a treatment dropdown at the top
  re-substitutes `{{ var }}` and toggles `{% if %}` branches in place.
- `instructions_preview_interactive.html` — mimics the live experiment, one
  block at a time, Back/Next nav. A setup screen 0 shows the full matrix and
  lets you pick the starting treatment before clicking Begin. A floating
  switcher in the top-right has one button per treatment, a **Reset** button
  that returns to screen 0, and a **Show matrix** toggle that reveals the
  matrix as an overlay.
- `instructions_preview.pdf` — long view rendered via Playwright headless
  Chromium. In the PDF, `{{ var }}` references stay as literal placeholders
  in the form `‹varname›` (using U+2039 / U+203A guillemets). The
  treatment-conditional `{% if %}` branches are resolved using the column
  selected as "PDF treatment".

## Easiest way to run (macOS)

Double-click `Preview_Instructions.command` in Finder. It will:

1. Auto-detect a project-local venv (`./venv/`, `./.venv/`, `./env/`, `./.env/`) and use its Python; otherwise it falls back to system `python3`.
2. Check that `jinja2`, `playwright`, and the headless Chromium browser are installed. If anything is missing, it prints clear install instructions and exits — **it never tries to install anything itself.**
3. Open the matrix popup. The script tries a native tkinter window first; if tkinter is not bundled with your Python (common with Homebrew Python), it silently falls back to a browser-based form served on `localhost`. Either way the experience is the same: fill the matrix, click Generate. When you click Generate, the three preview files are written to `previews/`. They are not auto-opened — open them yourself from Finder when you're ready.

### One-time setup on a new machine

```bash
cd /path/to/oTree-Template
python3 -m venv venv
source venv/bin/activate
pip install jinja2 playwright
playwright install chromium
```

After that the `.command` file picks up `./venv/` automatically — no further setup.

## Command-line

```bash
pip install jinja2 playwright
playwright install chromium     # one-time

python3 generate_instructions_preview.py
```

The tkinter popup shows a matrix grid:

- Columns are treatments (header cells are editable text).
- Rows are variables detected in `intro/instructions_text.html` and
  `intro/prequiz_text.html`. You can add more variable rows or treatment
  columns via the buttons at the bottom.
- Pick which treatment column the PDF should resolve conditionals against
  via the "PDF treatment" dropdown.
- Click **Generate**. Your matrix is saved to `.preview_state.json` and
  reloaded on the next run.

### Headless / no-display fallback

If tkinter is not installed, `DISPLAY` is empty, or you pass `--no-popup`:

- If `.preview_state.json` already contains treatment data, it is used as-is
  (no popup) — this is how the macOS `.command` will behave on the first run
  *after* you've populated it once.
- If `.preview_state.json` is missing or empty, the script writes a starter
  template to that file and prints instructions to edit it and re-run.

You can also pass an arbitrary config:

```bash
python3 generate_instructions_preview.py --config some_other_config.json
```

State file schema:

```json
{
  "treatments": ["Row player", "Column player"],
  "values": {
    "treatment":               ["row", "column"],
    "stag_payoff":             ["4",   "4"     ],
    "hare_payoff":             ["2",   "2"     ],
    "stag_alone":              ["0",   "0"     ],
    "num_experimental_rounds": ["10",  "10"    ],
    "showup":                  ["2.5", "2.5"   ],
    "quiz_bonus":              ["5",   "5"     ]
  },
  "pdf_treatment": "Row player"
}
```

Each `values` row must have one entry per treatment column.

## Markup conventions for authors

These conventions render natively in oTree templates AND are recognised by
the preview generator. Use them in `intro/instructions_text.html` and
`intro/prequiz_text.html`.

| Convention | Use |
|---|---|
| `{{ var }}`, `{{ C.const }}` | Variable substitution (replaced by the active treatment column in the preview). |
| `{% if var == value %}…{% elif var == value2 %}…{% endif %}` | Treatment-conditional content. |
| `<div class="instruction-block">…</div>` | One page; the preferred page-splitting style. |
| `{{block partN}}…{{endblock}}` | Legacy page-splitting style; still supported. If both styles appear in one file, the `instruction-block` divs win. |

A full reference also lives in the comment block at the top of
`intro/instructions_text.html`.

## Outputs are overwritten on each run

`previews/instructions_preview_long.html`,
`previews/instructions_preview_interactive.html`, and
`previews/instructions_preview.pdf` are overwritten on every successful run.
