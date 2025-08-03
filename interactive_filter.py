#!/usr/bin/env python3
"""
Interactive CSV Filter Tool
───────────────────────────
1. Ask for data folder
2. Ask whether to *filter-IN* (keep) or *filter-OUT* (remove) rows
3. Build filters with helpful hints
4. Allow chaining more filters until the user stops
5. Export the final DataFrame (CSV / XLSX)
"""
import os
from pathlib import Path
import pandas as pd
import questionary
from rich.console import Console
from rich.table import Table
from difflib import get_close_matches
import re
from questionary import Choice

console = Console()

# ───────────────────────────── helpers ──────────────────────────────
OPERATORS = {
    '%=': 'contains',
    '==': 'equals',
    '>=': '≥',
    '<=': '≤',
    '>':  '>',
    '<':  '<',
}

SPECIAL_FILTERS = {
    'isalpha':  "column contains letters [A–Z]",
    'isdigit':  "column contains digits [0-9]",
    'isspecial':"column contains special characters",
}

def ask_directory() -> Path:
    while True:
        p = Path(questionary.path("📂  Enter folder containing CSV files:").ask()).expanduser()
        if p.is_dir():
            return p
        console.print(f"[bold red]Directory '{p}' not found – try again.[/bold red]")

def list_csv_files(folder: Path):
    return [f.name for f in folder.glob("*.csv")]

def select_csv_file(folder: Path) -> Path | None:
    csvs = list_csv_files(folder)
    if not csvs:
        console.print("[bold red]No CSV files in that folder.[/bold red]")
        return None
    pick = questionary.select("Select a CSV file:", choices=csvs + ["<Back>"]).ask()
    return None if pick == "<Back>" else folder / pick

def read_csv_safely(path: Path) -> pd.DataFrame | None:
    for kwargs in (dict(delimiter=None),
                   dict(separator=';'),
                   dict(encoding='latin-1')):
        try:
            return pd.read_csv(path, on_bad_lines="skip", low_memory=False, **kwargs)
        except Exception:
            continue
    console.print(f"[bold red]❌  Could not open {path.name}[/bold red]")
    return None

def show_dataframe(df: pd.DataFrame, max_rows: int = 10):
    table = Table(show_header=True, header_style="bold magenta")
    for c in df.columns:
        table.add_column(str(c))
    for _, row in df.head(max_rows).iterrows():
        table.add_row(*[str(x) if pd.notna(x) else "" for x in row])
    console.print(table)

def find_similar(col: str, options) -> str | None:
    matches = get_close_matches(col, options, n=1, cutoff=0.6)
    return matches[0] if matches else None

# ────────────────────────── build filters ──────────────────────────
def build_filters(df: pd.DataFrame) -> list[tuple[str, str, str | float]]:
    """
    Build and return a list of filter rules.
    Each rule is (column, operator, value or None).
    """
    console.print("\n[bold yellow]Columns:[/bold yellow] " + ", ".join(df.columns))
    console.print("[italic]Supported operators:[/italic]  " +
                  ", ".join(f"{k}  ({v})" for k, v in OPERATORS.items()))
    console.print("[italic]Special keywords:[/italic]  " +
                  ", ".join(f"{k} → {v}" for k, v in SPECIAL_FILTERS.items()))

    raw_input = questionary.text("Enter filters (e.g. Amount >= 1000, Description %= refund):").ask()
    if not raw_input:
        raise ValueError("No filters provided.")

    rules = []

    for raw in [x.strip() for x in raw_input.split(",") if x.strip()]:
        # Check for special keyword operators
        for keyword in SPECIAL_FILTERS:
            if raw.endswith(keyword):
                col = raw[:-len(keyword)].strip()
                op = keyword
                val = None
                break
        else:
            op = next((o for o in OPERATORS if o in raw), None)
            if not op:
                raise ValueError(f"No valid operator found in filter: {raw}")
            col, val = map(str.strip, raw.split(op, 1))

        if col not in df.columns:
            suggestion = find_similar(col, df.columns)
            if suggestion and questionary.confirm(f"Did you mean '{suggestion}'?").ask():
                col = suggestion
            else:
                raise ValueError(f"Unknown column: {col}")

        if op not in SPECIAL_FILTERS and pd.api.types.is_numeric_dtype(df[col]):
            try:
                val = float(val)
            except ValueError:
                raise ValueError(f"Value for numeric column '{col}' must be a number.")

        rules.append((col, op, val))

    return rules

def apply_filter(df: pd.DataFrame, rule, mode: str) -> pd.DataFrame:
    """
    Apply one filter; mode is 'in' => keep, 'out' => drop.
    rule = (col, op, val)
    """
    col, op, val = rule
    if op == '%=':
        mask = df[col].astype(str).str.contains(val, na=False)
    elif op == '==':
        mask = df[col] == val
    elif op == '>=':
        mask = pd.to_numeric(df[col], errors='coerce') >= val
    elif op == '<=':
        mask = pd.to_numeric(df[col], errors='coerce') <= val
    elif op == '>':
        mask = pd.to_numeric(df[col], errors='coerce') > val
    elif op == '<':
        mask = pd.to_numeric(df[col], errors='coerce') < val
    elif op == 'isalpha':
        mask = df[col].astype(str).str.contains(r'[A-Za-z]', na=False)
    elif op == 'isdigit':
        mask = df[col].astype(str).str.contains(r'[0-9]', na=False)
    elif op == 'isspecial':
        mask = df[col].astype(str).str.contains(r'[^A-Za-z0-9\s]', na=False)
    else:
        raise ValueError("Unsupported operator")

    return df[mask] if mode == 'in' else df[~mask]

# ───────────────────────────── main flow ───────────────────────────
def main():
    console.print("[bold cyan]CSV Filter Tool[/bold cyan]")

    # 1️⃣  folder & file
    folder = ask_directory()
    path   = select_csv_file(folder)
    if not path:
        return
    df = read_csv_safely(path)
    if df is None:
        return

    # 2️⃣  choose filter-in or filter-out default
    mode = questionary.select(
        "Default behaviour for each filter?",
        choices=[
        Choice("Keep rows that MATCH filter (filter-IN)", value="in"),
        Choice("Remove rows that MATCH filter (filter-OUT)", value="out")
        ]
    ).ask()

    working_df = df.copy()
    while True:
        try:
            rules = build_filters(working_df)
        except ValueError as e:
            console.print(f"[bold red]{e}[/bold red]")
            continue

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


    # 5️⃣ export
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