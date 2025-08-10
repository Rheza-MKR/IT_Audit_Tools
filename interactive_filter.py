#!/usr/bin/env python3
"""
Interactive Table Filter Tool (CSV/Excel)
─────────────────────────────────────────
1) Pick folder and CSV/XLSX/XLS file (Excel sheet if multiple)
2) Choose filter mode: keep matching (IN) or remove matching (OUT)
3) Enter one or more filters (comma-separated), preview, then apply
4) Chain more filters
5) Export final result (CSV/XLSX)
"""
from pathlib import Path
import os
import re
import pandas as pd
import questionary
from questionary import Choice
from rich.console import Console
from rich.table import Table
from difflib import get_close_matches

console = Console()

# ───────────────────────── config ─────────────────────────

# Operator -> human hint
OPERATORS = {
    '%=':  'contains',
    '!%=': 'does NOT contain',
    '==':  'equals',
    '!=':  'not equal',
    '^=':  'starts with',
    '=^':  'ends with',
    '>=':  '≥',
    '<=':  '≤',
    '>':   '>',
    '<':   '<',
}

# Special "operators" (keyword at end of expression)
SPECIAL_FILTERS = {
    'isalpha':    "column contains letters [A–Z]",
    'isdigit':    "column contains digits [0–9]",
    'isspecial':  "column contains special characters",
    'isempty':    "column is empty (or NaN)",
    'isnotempty': "column is not empty",
}

# Parse priority (longest first so we don't misread '!=' as '!')
OP_PARSE_ORDER = ['!%=', '>=', '<=', '!=', '%=', '^=', '=^', '==', '>', '<']

# ─────────────────────── file helpers ──────────────────────

def ask_directory() -> Path:
    while True:
        p = Path(questionary.path("📂  Enter folder containing data files:").ask()).expanduser()
        if p.is_dir():
            return p
        console.print(f"[bold red]Directory '{p}' not found – try again.[/bold red]")

def list_table_files(folder: Path):
    return sorted([f.name for f in folder.iterdir() if f.suffix.lower() in {'.csv', '.xlsx', '.xls'}])

def select_table_file(folder: Path) -> tuple[Path, str | None]:
    files = list_table_files(folder)
    if not files:
        console.print("[bold red]No CSV or Excel files in that folder.[/bold red]")
        return None, None
    pick = questionary.select("Select a file:", choices=files + ["<Back>"]).ask()
    if pick == "<Back>":
        return None, None
    path = folder / pick
    sheet = None
    if path.suffix.lower() in {'.xlsx', '.xls'}:
        try:
            xl = pd.ExcelFile(path)
            if len(xl.sheet_names) > 1:
                sheet = questionary.select("Select sheet:", choices=xl.sheet_names).ask()
        except Exception as e:
            console.print(f"[bold red]Failed reading Excel: {e}[/bold red]")
            return None, None
    return path, sheet

def read_table_safely(path: Path, sheet: str | None) -> pd.DataFrame | None:
    try:
        if path.suffix.lower() in {'.xlsx', '.xls'}:
            return pd.read_excel(path, sheet_name=sheet) if sheet else pd.read_excel(path)
        # CSV
        try:
            df = pd.read_csv(path, encoding="utf-8", on_bad_lines="skip")
            if len(df.columns) == 1:
                df = pd.read_csv(path, encoding="utf-8", sep=";", on_bad_lines="skip")
            return df
        except Exception:
            return pd.read_csv(path, encoding="latin-1", on_bad_lines="skip")
    except Exception as e:
        console.print(f"[bold red]❌  Could not open {path.name}: {e}[/bold red]")
        return None

def show_dataframe(df: pd.DataFrame, max_rows: int = 10):
    table = Table(show_header=True, header_style="bold magenta")
    for c in df.columns:
        table.add_column(str(c))
    for _, row in df.head(max_rows).iterrows():
        table.add_row(*[str(x) if pd.notna(x) else "" for x in row])
    console.print(table)

def find_similar(col: str, options) -> str | None:
    m = get_close_matches(col, options, n=1, cutoff=0.6)
    return m[0] if m else None

# ────────────────────── filter building ─────────────────────

def build_filters(df: pd.DataFrame) -> list[tuple[str, str, str | float | None]]:
    """
    Return list of filter rules: (column, operator|special, value_or_None).
    Accepts multiple rules separated by commas in one input.
    """
    console.print("\n[bold yellow]Columns:[/bold yellow] " + ", ".join(map(str, df.columns)))
    console.print("[italic]Operators:[/italic]  " +
                  ", ".join(f"{k} ({v})" for k, v in OPERATORS.items()))
    console.print("[italic]Special:[/italic]  " +
                  ", ".join(f"{k} → {v}" for k, v in SPECIAL_FILTERS.items()))

    raw_input = questionary.text(
        "Enter filters (e.g. Amount >= 1000, Description %= refund, Code ^= ABC):"
    ).ask()
    if not raw_input:
        raise ValueError("No filters provided.")

    rules = []
    for raw in [x.strip() for x in raw_input.split(",") if x.strip()]:
        # special keyword?
        found_special = False
        for keyword in SPECIAL_FILTERS:
            if raw.endswith(keyword):
                col = raw[:-len(keyword)].strip()
                op = keyword
                val = None
                found_special = True
                break
        if not found_special:
            # normal operator
            op = None
            for cand in OP_PARSE_ORDER:
                if cand in raw:
                    op = cand
                    break
            if not op:
                raise ValueError(f"No valid operator found in filter: {raw}")
            col, val = map(str.strip, raw.split(op, 1))

        if col not in df.columns:
            suggestion = find_similar(col, df.columns)
            if suggestion and questionary.confirm(f"Did you mean '{suggestion}' for '{col}'?").ask():
                col = suggestion
            else:
                raise ValueError(f"Unknown column: {col}")

        # numeric coercion when appropriate
        if (op not in SPECIAL_FILTERS) and (op not in {'%=', '!%=', '^=', '=^'}):
            if pd.api.types.is_numeric_dtype(df[col]):
                try:
                    val = float(val)
                except ValueError:
                    raise ValueError(f"Value for numeric column '{col}' must be a number.")
        rules.append((col, op, val))
    return rules

def apply_filter(df: pd.DataFrame, rule, mode: str) -> pd.DataFrame:
    """
    Apply one filter; mode 'in' keeps matches, 'out' removes matches.
    rule = (col, op, val)
    """
    col, op, val = rule

    if op == '%=':
        mask = df[col].astype(str).str.contains(str(val), na=False, regex=False)
    elif op == '!%=':
        mask = ~df[col].astype(str).str.contains(str(val), na=False, regex=False)
    elif op == '^=':
        mask = df[col].astype(str).str.startswith(str(val), na=False)
    elif op == '=^':
        mask = df[col].astype(str).str.endswith(str(val), na=False)
    elif op == '==':
        mask = df[col] == val
    elif op == '!=':
        mask = df[col] != val
    elif op == '>=':
        mask = pd.to_numeric(df[col], errors='coerce') >= float(val)
    elif op == '<=':
        mask = pd.to_numeric(df[col], errors='coerce') <= float(val)
    elif op == '>':
        mask = pd.to_numeric(df[col], errors='coerce') > float(val)
    elif op == '<':
        mask = pd.to_numeric(df[col], errors='coerce') < float(val)
    elif op == 'isalpha':
        mask = df[col].astype(str).str.contains(r'[A-Za-z]', na=False)
    elif op == 'isdigit':
        mask = df[col].astype(str).str.contains(r'[0-9]', na=False)
    elif op == 'isspecial':
        mask = df[col].astype(str).str.contains(r'[^A-Za-z0-9\s]', na=False)
    elif op == 'isempty':
        s = df[col].astype(str).str.strip()
        mask = s.eq("") | df[col].isna()
    elif op == 'isnotempty':
        s = df[col].astype(str).str.strip()
        mask = (~s.eq("")) & (~df[col].isna())
    else:
        raise ValueError("Unsupported operator")

    return df[mask] if mode == 'in' else df[~mask]

# ─────────────────────────── main flow ───────────────────────────

def main():
    console.print("[bold cyan]CSV/Excel Filter Tool[/bold cyan]")

    # 1) folder & file
    folder = ask_directory()
    path, sheet = select_table_file(folder)
    if not path:
        return
    df = read_table_safely(path, sheet)
    if df is None:
        return

    # 2) choose filter-in or filter-out default
    mode = questionary.select(
        "Default behaviour for each filter?",
        choices=[
            Choice("Keep rows that MATCH filter (filter-IN)", value="in"),
            Choice("Remove rows that MATCH filter (filter-OUT)", value="out")
        ]
    ).ask()

    # 3) iterative filtering
    working_df = df.copy()
    while True:
        try:
            rules = build_filters(working_df)
        except ValueError as e:
            console.print(f"[bold red]{e}[/bold red]")
            if not questionary.confirm("Try entering filters again?", default=True).ask():
                break
            continue

        # simulate
        simulated_df = working_df.copy()
        for rule in rules:
            simulated_df = apply_filter(simulated_df, rule, mode)

        console.print(f"[yellow]Filter preview:[/yellow] Would keep {len(simulated_df)} out of {len(working_df)} rows")
        if len(simulated_df) == 0:
            console.print("[red]No rows would be left after applying this filter – skipping.[/red]")
        elif questionary.confirm("Apply this filter?", default=True).ask():
            working_df = simulated_df
        else:
            console.print("[italic]Filter skipped.[/italic]")

        if len(working_df) == 0:
            console.print("[red]No rows left – stopping filter process.[/red]")
            break

        if not questionary.confirm("Add another filter?", default=False).ask():
            break

    # 4) export
    if questionary.confirm("Export the final result?", default=True).ask():
        fmt = questionary.select("Choose format:", choices=["CSV", "XLSX"]).ask()
        fname = questionary.text("File name (without extension):").ask()
        out_path = folder / f"{fname}.{fmt.lower()}"
        try:
            if fmt == "CSV":
                working_df.to_csv(out_path, index=False)
            else:
                working_df.to_excel(out_path, index=False)
            console.print(f"[bold green]Saved → {out_path}[/bold green]")
        except Exception as e:
            console.print(f"[bold red]Failed to save: {e}[/bold red]")

if __name__ == "__main__":
    main()
