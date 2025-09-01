#!/usr/bin/env python3
"""
Full Reconciliation Tool
────────────────────────────────────────────────────────────
Flow:
1) Pick a folder
2) Pick MAIN file → fully load it via read_file_safely (Excel sheet/header handled here)
3) Pick REFERENCE file → fully load via read_file_safely
4) Pick key columns (from the already-loaded DataFrames)
5) Choose match method (full / first N / last N)
6) See summary + export matched/unmatched
"""

from pathlib import Path
from typing import Optional, Tuple, List

import pandas as pd
import questionary
from rich.console import Console

# ✅ Only use your shared helpers; read_file_safely can call find_headers internally
from utils.import_utils import read_file_safely, find_headers  # noqa: F401 (imported for clarity)

console = Console()

# ───────────────────────── UI helpers ─────────────────────────

def ask_directory() -> Path:
    while True:
        p = Path(questionary.path("📂  Enter the directory containing your data files:").ask()).expanduser().resolve()
        if p.is_dir():
            return p
        console.print(f"[bold red]Directory '{p}' not found – try again.[/bold red]")

def list_tabular_files(folder: Path) -> List[str]:
    return sorted([f.name for f in folder.iterdir() if f.suffix.lower() in {".csv", ".xlsx", ".xls"}])

def select_file(folder: Path, prompt: str) -> Optional[Path]:
    files = list_tabular_files(folder)
    if not files:
        console.print("[bold red]No CSV or Excel files found in that folder.[/bold red]")
        return None
    choice = questionary.select(prompt, choices=files + ["<Back>"]).ask()
    if not choice or choice == "<Back>":
        return None
    return folder / choice

def select_column(df: pd.DataFrame, prompt: str) -> Optional[str]:
    cols = [str(c) for c in df.columns]
    if not cols:
        console.print("[bold red]No columns detected in the loaded data.[/bold red]")
        return None
    choice = questionary.select(prompt, choices=cols + ["<Back>"]).ask()
    if not choice or choice == "<Back>":
        return None
    return choice

# ───────────────────────── Recon logic ─────────────────────────

def check_data_format(df: pd.DataFrame, column: str) -> List[str]:
    """
    Quick hygiene checks (non-fatal); returns list of issues.
    """
    errs: List[str] = []
    if column not in df.columns:
        return [f"Column '{column}' not found."]
    # check missing BEFORE coercing to str
    if df[column].isna().any():
        errs.append("Missing values detected.")
    s = df[column].astype(str).str.strip()
    # special characters (non word/space)
    if s.str.contains(r"[^\w\s]", regex=True, na=False).any():
        errs.append("Special characters detected.")
    # numeric & negatives
    numeric_mask = s.str.replace(".", "", 1, regex=False).str.isnumeric()
    if numeric_mask.all() and len(s) > 0:
        try:
            if (s.astype(float) < 0).any():
                errs.append("Negative values detected.")
        except Exception:
            pass
    return errs

def select_reconcile_method() -> Tuple[Optional[str], Optional[int]]:
    method = questionary.select(
        "Select reconciliation method:",
        choices=[
            "Standard (full match)",
            "First N characters",
            "Last N characters",
            "<Back>",
        ],
    ).ask()
    if not method or method == "<Back>":
        return None, None

    num_chars = None
    if method in ("First N characters", "Last N characters"):
        num_chars_str = questionary.text("Enter number of characters (positive integer):").ask()
        try:
            num_chars = int(num_chars_str)
            if num_chars <= 0:
                raise ValueError
        except Exception:
            console.print("[bold red]Invalid number.[/bold red]")
            return None, None

    return method, num_chars

def select_export_format(default_excel: bool = False) -> Optional[str]:
    default = "XLSX" if default_excel else "CSV"
    fmt = questionary.select("Select an export format:", choices=["CSV", "XLSX"], default=default).ask()
    return fmt if fmt else None

def export_df(df: pd.DataFrame, out_path: Path) -> bool:
    try:
        if out_path.suffix.lower() == ".csv":
            df.to_csv(out_path, index=False)
        else:
            df.to_excel(out_path, index=False)
        console.print(f"[bold green]Saved → {out_path}[/bold green]")
        return True
    except Exception as e:
        console.print(f"[bold red]Error saving: {e}[/bold red]")
        return False

def reconcile_on_keys(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    key1: str,
    key2: str,
    method: str,
    num_chars: Optional[int],
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Return (matched_df1_rows, unmatched_df1_rows) after transforming keys based on method.
    """
    # Normalize keys
    df1 = df1.copy()
    df2 = df2.copy()
    df1[key1] = df1[key1].astype(str).str.strip()
    df2[key2] = df2[key2].astype(str).str.strip()

    if method == "First N characters":
        df1[key1] = df1[key1].str[:num_chars]
        df2[key2] = df2[key2].str[:num_chars]
    elif method == "Last N characters":
        df1[key1] = df1[key1].str[-num_chars:]
        df2[key2] = df2[key2].str[-num_chars:]

    key2_set = set(df2[key2])
    matched_mask = df1[key1].isin(key2_set)
    return df1[matched_mask].copy(), df1[~matched_mask].copy()

# ───────────────────────── Entrypoint ─────────────────────────

def main():
    console.print("[bold cyan]Full Reconciliation Tool[/bold cyan]")

    # 1) Pick folder
    data_dir = ask_directory()

    # 2) Pick MAIN file and fully load it (Excel handling occurs here)
    console.print("[bold]Select the main file (source to check):[/bold]")
    file1_path = select_file(data_dir, "Main file:")
    if not file1_path:
        return

    df1 = read_file_safely(file1_path)
    if df1 is None or df1.empty:
        console.print(f"[bold red]Failed to load data from {file1_path.name}.[/bold red]")
        return

    # 3) From the LOADED df1, choose the key column (no extra reads)
    key1 = select_column(df1, f"Column to match in {file1_path.name}")
    if not key1:
        return

    # 4) Only now pick the REFERENCE file and fully load it (Excel handling occurs here)
    console.print("[bold]Select the reference file (list to match against):[/bold]")
    file2_path = select_file(data_dir, "Reference file:")
    if not file2_path:
        return

    df2 = read_file_safely(file2_path)
    if df2 is None or df2.empty:
        console.print(f"[bold red]Failed to load data from {file2_path.name}.[/bold red]")
        return

    # 5) Choose key from LOADED df2
    key2 = select_column(df2, f"Column to match in {file2_path.name}")
    if not key2:
        return

    # 6) Choose reconciliation method
    method, num_chars = select_reconcile_method()
    if method is None:
        return

    # Optional hygiene checks (non-fatal)
    errs1 = check_data_format(df1, key1)
    errs2 = check_data_format(df2, key2)
    if errs1 or errs2:
        console.print("\n[bold yellow]Data Format Issues:[/bold yellow]")
        if errs1:
            console.print(f" - {file1_path.name} / {key1}: {', '.join(errs1)}")
        if errs2:
            console.print(f" - {file2_path.name} / {key2}: {', '.join(errs2)}")
        if not questionary.confirm("Continue despite data issues?", default=False).ask():
            return

    # 7) Reconcile
    matched, unmatched = reconcile_on_keys(df1, df2, key1, key2, method, num_chars)

    console.print("\n[bold blue]Reconciliation Summary[/bold blue]")
    console.print(f"Records in {file1_path.name}: [bold]{len(df1)}[/bold]")
    console.print(f"Matched:   [green]{len(matched)}[/green]")
    console.print(f"Unmatched: [red]{len(unmatched)}[/red]")

    # 8) Export?
    if questionary.confirm("Export unmatched records?", default=True).ask():
        fmt = select_export_format()
        if fmt:
            out_path = file1_path.parent / f"unmatched_{file1_path.stem}.{fmt.lower()}"
            export_df(unmatched, out_path)

    if questionary.confirm("Export matched records?", default=False).ask():
        fmt2 = select_export_format(default_excel=True)
        if fmt2:
            out_path2 = file1_path.parent / f"matched_{file1_path.stem}.{fmt2.lower()}"
            export_df(matched, out_path2)

    console.print("\n[bold blue]✅ Done.[/bold blue]")

if __name__ == "__main__":
    main()
