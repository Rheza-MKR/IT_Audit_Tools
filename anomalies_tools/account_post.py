import pandas as pd
from rich.console import Console
from pathlib import Path
import questionary
import os
import re

console = Console()

# ───────────────────────────── file helpers ─────────────────────────────
def _ask_directory() -> Path:
    while True:
        dir_path = Path(questionary.text("Enter the audit directory path:").ask()).expanduser().resolve()
        if dir_path.is_dir():
            return dir_path
        console.print(f"[bold red]Directory '{dir_path}' does not exist – try again.[/bold red]")

def list_data_files(directory: Path):
    """List CSV and Excel files."""
    return sorted([f.name for f in directory.glob("*.csv")] +
                  [f.name for f in directory.glob("*.xls")] +
                  [f.name for f in directory.glob("*.xlsx")])

def select_data_file_from_folder(directory: Path):
    files = list_data_files(directory)
    if not files:
        console.print("[bold red]No CSV or Excel files found in the folder.[/bold red]")
        return None
    file_choice = questionary.select("Select a file to analyze:", choices=files + ["Back"]).ask()
    return None if file_choice == "Back" else directory / file_choice

def read_file_safely(path: Path) -> pd.DataFrame | None:
    """Read CSV or Excel into DataFrame with a couple fallbacks for CSV."""
    try:
        if path.suffix.lower() in (".xls", ".xlsx"):
            return pd.read_excel(path)
        if path.suffix.lower() == ".csv":
            try:
                df = pd.read_csv(path, encoding="utf-8", on_bad_lines="skip")
                if len(df.columns) == 1:
                    df = pd.read_csv(path, encoding="utf-8", sep=";", on_bad_lines="skip")
                return df
            except Exception:
                return pd.read_csv(path, encoding="latin-1", on_bad_lines="skip")
        console.print(f"[bold red]Unsupported file type: {path.suffix}[/bold red]")
        return None
    except Exception as e:
        console.print(f"[bold red]Error reading file: {e}[/bold red]")
        return None

def export_dataframe(df, dir_path: Path):
    if df is None or df.empty:
        console.print("[bold yellow]No data to export.[/bold yellow]")
        return

    export = questionary.confirm("Do you want to export the flagged data?", default=True).ask()
    if not export:
        return

    fmt = questionary.select("Select export format:", choices=["CSV", "XLSX"]).ask()
    fname = questionary.text("Enter filename (without extension):").ask()
    out_path = dir_path / f"{fname}.{'csv' if fmt == 'CSV' else 'xlsx'}"

    try:
        if fmt == "CSV":
            df.to_csv(out_path, index=False)
        else:
            df.to_excel(out_path, index=False)
        console.print(f"[bold green]Exported to {out_path}[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Failed to export: {e}[/bold red]")

# ───────────────────────────── core logic ─────────────────────────────
def check_wrong_journal_entry(df: pd.DataFrame):
    transaction_col = questionary.select("Select the transaction ID column:", choices=list(df.columns)).ask()
    account_num_col = questionary.select("Select the account number column:", choices=list(df.columns)).ask()
    account_name_col = questionary.select("Select the account name column:", choices=list(df.columns)).ask()

    # Get user-specified account numbers to exclude
    account_excl_input = questionary.text("Enter specific account numbers to exclude (comma-separated):").ask()
    excluded_numbers = [acc.strip() for acc in account_excl_input.split(",") if acc.strip()]

    # Keywords to exclude based on account names
    keyword_input = questionary.text("Enter keywords to ignore in account names (comma-separated):").ask()
    ignore_keywords = [k.strip().lower() for k in keyword_input.split(",") if k.strip()]
    kw_regex = "|".join(re.escape(k) for k in ignore_keywords) if ignore_keywords else None

    wrong_entries = []

    for _, group in df.groupby(transaction_col, dropna=False):
        # Exclude group if any account name contains a keyword
        if kw_regex and group[account_name_col].astype(str).str.lower().str.contains(kw_regex).any():
            continue

        # Exclude group if any account number is in the excluded list
        if excluded_numbers and group[account_num_col].astype(str).isin(excluded_numbers).any():
            continue

        # BS/PnL detection
        acc_nums = group[account_num_col].astype(str)
        has_bs = acc_nums.str.startswith(("1", "2", "3")).any()
        has_pnl = acc_nums.str.startswith(("4", "5", "6", "7")).any()

        if has_bs and has_pnl:
            wrong_entries.append(group)

    if wrong_entries:
        result_df = pd.concat(wrong_entries, ignore_index=True)
        console.print(f"[bold yellow]Found {len(result_df)} rows with invalid BS and PnL combination.[/bold yellow]")
        return result_df
    else:
        console.print("[bold green]No invalid combinations found.[/bold green]")
        return None

# ───────────────────────────── entry point ─────────────────────────────
def main():
    console.print("[bold cyan]Wrong Journal Entry Checker App[/bold cyan]")
    dir_path = _ask_directory()
    file_path = select_data_file_from_folder(dir_path)
    if not file_path:
        return
    df = read_file_safely(file_path)
    if df is None:
        return
    flagged_df = check_wrong_journal_entry(df)
    export_dataframe(flagged_df, dir_path)

if __name__ == "__main__":
    main()
