# MARIMO_CONVENTIONS.md

How to write marimo notebooks for this project. Read this before creating or editing any file in `notebooks/`.

Marimo replaces Jupyter for all notebooks in PRX Predictor. Marimo notebooks are stored as pure Python (`.py`), are reactive (cells re-run when their dependencies change), have first-class SQLite support, and integrate with Claude Code via `marimo pair`.

---

## 1. Why marimo, not Jupyter

- **Git-friendly:** notebooks are `.py` files, diff cleanly, no JSON noise
- **Reactive execution:** no hidden cell-order state; dependencies drive execution
- **Executable as scripts:** `python notebooks/00_peng_eda.py` runs the whole thing
- **Native SQLite support:** SQL cells query our `data/prx.db` directly, results come back as DataFrames
- **Claude Code integration:** `marimo pair` lets Claude Code edit notebooks while a live editor is open
- **Deployable:** any notebook can also be served as a read-only web app via `marimo run`

---

## 2. File format

Every marimo notebook is a Python file with this structure:

```python
import marimo

__generated_with = "0.x.y"
app = marimo.App()


@app.cell
def __():
    import pandas as pd
    import numpy as np
    return np, pd


@app.cell
def __(pd):
    df = pd.read_csv("data/external/peng_2024.csv")
    df
    return df,


@app.cell
def __(df):
    df.describe()
    return


if __name__ == "__main__":
    app.run()
```

Each cell is a function decorated with `@app.cell`. The function's parameters are the variables it consumes from earlier cells; the return tuple is what it exposes to later cells. Marimo enforces no mutable global state — variables only flow in via parameters.

---

## 3. Creating a new notebook

Two ways, both fine:

**Scaffold via marimo CLI (preferred):**
```bash
marimo edit notebooks/00_peng_eda.py
```
This opens the marimo editor on a fresh notebook and writes the `.py` file as you save. Best when you want to interactively build first.

**Write the file directly:**
Claude Code can also write the `.py` file using the structure in section 2 above. This is acceptable when the notebook is being authored from a spec rather than exploratively.

After either approach, the resulting `.py` is the source of truth — commit it to git.

---

## 4. Running a notebook

| Command | What it does | When to use |
|---|---|---|
| `marimo edit notebooks/foo.py` | Opens interactive editor | Authoring or debugging |
| `marimo run notebooks/foo.py` | Serves as a read-only web app | Sharing results |
| `python notebooks/foo.py` | Executes as a script | CI, automation, headless validation |

For verification at the end of a task, `python notebooks/foo.py` is the fastest check — it runs all cells in dependency order and surfaces any errors.

---

## 5. Querying SQLite (our data warehouse)

Marimo has first-class SQL cells. To query `data/prx.db`:

```python
@app.cell
def __():
    import marimo as mo
    import sqlite3
    conn = sqlite3.connect("data/prx.db")
    return conn, mo


@app.cell
def __(conn, mo):
    prx_matches = mo.sql(
        f"""
        SELECT m.match_id, m.date_utc, m.team1_score, m.team2_score
        FROM matches m
        WHERE m.team1_id = 624 OR m.team2_id = 624
        ORDER BY m.date_utc DESC
        LIMIT 20
        """,
        engine=conn,
    )
    return prx_matches,
```

`mo.sql()` returns a Polars DataFrame if Polars is installed, otherwise Pandas. The result is just a regular DataFrame — downstream cells consume it like any other.

For ad-hoc Python-only queries, plain `pd.read_sql(query, conn)` also works.

---

## 6. Notebook collaboration via `marimo pair`

Marimo has a documented Claude Code integration. From a terminal:

```bash
marimo pair notebooks/00_peng_eda.py
```

This opens the marimo editor in "pair" mode where Claude Code (or any agent CLI) can read the live notebook state and propose edits. Use this when you want Claude Code to iterate on a notebook with feedback rather than blind-writing it.

For most tasks in TASKS.md, direct `.py` editing is fine. Pair mode is more useful for exploratory phases (Phase 0 EDA, Phase 3 validation).

---

## 7. Conventions for this project

### Folder
All notebooks live in `notebooks/` at the repo root. Don't put notebooks anywhere else.

### Naming
`{NN}_{purpose}.py` where NN is a two-digit prefix matching task order:
- `00_peng_eda.py` — Phase 0 EDA
- `01_peng_baseline.py` — Phase 0 model
- `02_model_validation.py` — Phase 3 validation
- `03_player_skill_validation.py` — Phase 4 validation

### Imports
Put all imports in the first `@app.cell`. Don't scatter imports across cells. Common imports for this project:

```python
import marimo as mo
import pandas as pd
import numpy as np
import sqlite3
import matplotlib.pyplot as plt
```

If a notebook needs Bambi or scikit-learn, add to that first cell.

### Database connections
Open the SQLite connection in an early cell and pass it as a parameter to later cells. Don't reopen connections per cell.

### Plots
matplotlib by default (already in the stack via Bambi/statsmodels). Don't introduce plotly or altair unless a deviation entry is added and approved.

```python
@app.cell
def __(plt, results):
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(results["predicted"], results["actual"])
    ax.plot([0, 1], [0, 1], 'k--')
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    fig
    return
```

The last expression in a cell becomes its output, just like Jupyter — return `fig` to display it.

### Markdown for narration
Use `mo.md()` cells to narrate findings. Keep them one-line per finding, like the TASKS.md says:

```python
@app.cell
def __(mo):
    mo.md("**Finding:** team loadout dominates with odds ratio 2.2, matching Peng's published result.")
    return
```

### Determinism
Set seeds explicitly in any cell using randomness:
```python
@app.cell
def __(np):
    np.random.seed(42)
    return
```

This matters because marimo's reactivity will re-run cells; non-deterministic outputs cause confusing diffs.

---

## 8. Anti-patterns — don't do these

- **Don't use `IPython.display`** — that's Jupyter-only. Use cell return values.
- **Don't import from one notebook into another** with relative paths — if you need shared logic, put it in `models/` or `ingestion/` and import as a normal Python module.
- **Don't write to files inside notebooks** unless the task explicitly says so. Notebooks are for exploration and validation, not data pipelines. Pipelines live in `ingestion/`.
- **Don't use `%magic` commands** — marimo doesn't support them; they're Jupyter syntax.
- **Don't mutate variables** that were created in earlier cells. Marimo enforces this anyway, but writing code that wants to mutate will fight the reactive model. If you need to track a state, use `mo.state()`.
- **Don't add notebook-level configuration** (e.g., display options for pandas) — keep notebooks portable.

---

## 9. Committing notebooks

Notebooks are committed as `.py` files. Don't commit:
- `.marimo/` cache directories (add to `.gitignore`)
- Notebook-generated outputs (`*.html`, `*.pdf` from `marimo export`)
- Sample data the notebook reads — those live in `data/external/` and are themselves gitignored if large

`.gitignore` entry to add when setting up Phase 0:
```
.marimo/
notebooks/__pycache__/
*.html
data/external/*.csv
data/external/*.xlsx
```

---

## 10. When in doubt

- For marimo syntax questions: https://docs.marimo.io
- For SQL cell patterns: https://docs.marimo.io/guides/working_with_data/sql/
- For the pair-mode workflow with Claude Code: https://github.com/marimo-team/marimo

If a marimo behavior contradicts what's in this doc, add an entry to `docs/DEVIATIONS.md` and proceed with the marimo-correct behavior; this doc is the second source of truth, not the first.
