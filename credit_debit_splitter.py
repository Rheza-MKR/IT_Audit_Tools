import os
from pathlib import Path
import pandas as pd
from rich.console import Console
from rich.table import Table
import questionary

# ✅ shared safe reader (handles CSV/Excel + sheet/header flow & column cleaning)
from utils.import_utils import read_file_safely

console = Console()

# ────────────────────────── folder & file selection ──────────────────────────

def ask_directory() -> str:
    """Prompt for a folder path until a valid directory is provided."""
    while True:
        p = questionary.path("📂 Enter the folder containing your source files:").ask()
        if not p:
            continue
        path = Path(p).expanduser().resolve()
        if path.is_dir():
            return str(path)
        console.print(f"[bold red]Directory '{path}' does not exist – try again.[/bold red]")

def list_tabular_files(data_dir: str):
    """Return list of .csv/.xlsx/.xls in the given folder."""
    try:
        return [
            f for f in os.listdir(data_dir)
            if f.lower().endswith((".csv", ".xlsx", ".xls"))
        ]
    except FileNotFoundError:
        return []

def select_one_file(data_dir: str) -> Path | None:
    files = list_tabular_files(data_dir)
    if not files:
        console.print(f"[bold red]No CSV/Excel files found in {data_dir}[/bold red]")
        return None
    choice = questionary.select("Select ONE file to process:", choices=files + ["<Back>"]).ask()
    if not choice or choice == "<Back>":
        return None
    return Path(data_dir) / choice

# ────────────────────────── helpers ──────────────────────────

def _snake(s: str) -> str:
    return (
        str(s)
        .strip()
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("\t", " ")
        .replace("-", " ")
        .replace("/", " ")
        .lower()
        .replace("  ", " ")
        .replace(" ", "_")
    )

def _resolve_column(df: pd.DataFrame, *candidates: str) -> str | None:
    """
    Try to find a column regardless of case/spacing/snake_case.
    Returns the actual df column name or None.
    """
    colmap = {c: c for c in df.columns}
    lower_map = {str(c).lower(): c for c in df.columns}
    snake_map = {_snake(c): c for c in df.columns}
    compact_map = {str(c).lower().replace("_", ""): c for c in df.columns}

    for name in candidates:
        variants = {
            name,
            str(name).lower(),
            _snake(name),
            str(name).lower().replace(" ", "_"),
            str(name).lower().replace(" ", ""),
        }
        for v in variants:
            if v in colmap: return colmap[v]
        for v in variants:
            if v in lower_map: return lower_map[v]
        for v in variants:
            if v in snake_map: return snake_map[v]
        for v in variants:
            compact = v.replace("_", "")
            if compact in compact_map: return compact_map[compact]
    return None

def _classify_flags(series: pd.Series) -> pd.Series:
    """
    Normalize 'Debit or Credit' flags to 'DEBIT' / 'CREDIT' / NaN.
    Accepts D/DR/DEB and C/CR/CRED too.
    """
    s = series.astype(str).str.strip().str.upper()
    exact_map = {
        "DEBIT": "DEBIT", "D": "DEBIT", "DR": "DEBIT", "DEB": "DEBIT",
        "CREDIT": "CREDIT", "C": "CREDIT", "CR": "CREDIT", "CRE": "CREDIT", "CRED": "CREDIT",
    }
    mapped = s.map(exact_map)
    needs = mapped.isna()
    short = s.str.len() <= 6
    mapped = mapped.where(~(needs & short & s.str.startswith("D")), "DEBIT")
    mapped = mapped.where(~(needs & short & s.str.startswith("C")), "CREDIT")
    mapped = mapped.where(~mapped.isna(), other=pd.NA)
    return mapped

def split_debit_credit(df: pd.DataFrame, amount_col: str, flag_col: str) -> pd.DataFrame:
    """Add vectorized 'debit'/'credit' columns based on flag, preserving all columns."""
    out = df.copy()
    out[amount_col] = pd.to_numeric(out[amount_col], errors="coerce")

    flags = _classify_flags(out[flag_col])
    out["debit"] = out[amount_col].where(flags.eq("DEBIT"))
    out["credit"] = out[amount_col].where(flags.eq("CREDIT"))

    cols = ["debit", "credit"] + [c for c in out.columns if c not in ("debit", "credit")]
    return out[cols]

def show_preview(df: pd.DataFrame, n: int = 10):
    table = Table(show_header=True, header_style="bold magenta")
    for c in df.columns:
        table.add_column(str(c))
    for _, row in df.head(n).iterrows():
        table.add_row(*[("" if pd.isna(val) else str(val)) for val in row])
    console.print(table)

# ────────────────────────── single-file processor ──────────────────────────

def process_single_file(file_path: Path):
    console.print(f"\n[cyan]Processing[/cyan] {file_path.name} …")

    df = read_file_safely(file_path)
    if df is None:
        console.print(f"[bold red]Failed to read {file_path.name} — aborting.[/bold red]")
        return
    if df.empty:
        console.print(f"[bold yellow]{file_path.name} has 0 rows — aborting.[/bold yellow]")
        return

    # Try to resolve required columns automatically
    amount_col = _resolve_column(df, "Amount", "amount", "amt", "transaction_amount")
    flag_col   = _resolve_column(df, "Debit or Credit", "debit_or_credit", "dr_cr", "debit_credit")

    # If not found, ask the user to pick columns
    if amount_col is None:
        amount_col = questionary.select(
            "Pick the Amount column:",
            choices=list(map(str, df.columns))
        ).ask()
    if flag_col is None:
        flag_col = questionary.select(
            "Pick the Debit/Credit flag column:",
            choices=list(map(str, df.columns))
        ).ask()

    if not amount_col or not flag_col:
        console.print("[bold red]Required columns not provided — aborting.[/bold red]")
        return

    out_df = split_debit_credit(df, amount_col=amount_col, flag_col=flag_col)
    show_preview(out_df)

    # Export (CSV for consistency)
    out_path = file_path.with_name(f"{file_path.stem}_Processed.csv")
    try:
        out_df.to_csv(out_path, index=False, na_rep="<NA>")
        console.print(f"[green]✓ Saved processed file to {out_path.name}[/green]")
    except Exception as e:
        console.print(f"[bold red]Failed to save {out_path.name}: {e}[/bold red]")

# ────────────────────────── main / entry-point ──────────────────────────

def main():
    console.print("[bold cyan]Debit/Credit Splitter — Single File Mode[/bold cyan]")
    data_dir = ask_directory()
    file_path = select_one_file(data_dir)
    if not file_path:
        console.print("[blue]No file selected.[/blue]")
        return
    process_single_file(file_path)

if __name__ == "__main__":
    main()
