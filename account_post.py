import pandas as pd
from rich.console import Console
from pathlib import Path
import questionary
import os
import re

console = Console()

def read_csv_safely(path):
    try:
        df = pd.read_csv(path, encoding="utf-8", on_bad_lines="skip")
        if len(df.columns) == 1:
            df = pd.read_csv(path, encoding="utf-8", sep=";", on_bad_lines="skip")
        return df
    except Exception as e:
        console.print(f"[bold red]Error reading file: {e}[/bold red]")
        return None

def _ask_directory() -> Path:
    while True:
        dir_path = Path(questionary.text("Enter the audit directory path:").ask()).expanduser()
        if dir_path.is_dir():
            return dir_path
        console.print(f"[bold red]Directory '{dir_path}' does not exist – try again.[/bold red]")

def select_csv_from_folder(directory):
    files = [f for f in os.listdir(directory) if f.endswith(".csv")]
    if not files:
        console.print("[bold red]No CSV files found in the folder.[/bold red]")
        return None
    file_choice = questionary.select("Select a CSV file to analyze:", choices=files + ["Back"]).ask()
    return None if file_choice == "Back" else os.path.join(directory, file_choice)

def export_dataframe(df, dir_path):
    if df is None or df.empty:
        console.print("[bold yellow]No data to export.[/bold yellow]")
        return

    export = questionary.confirm("Do you want to export the flagged data?", default=True).ask()
    if not export:
        return

    fmt = questionary.select("Select export format:", choices=["CSV", "XLSX"]).ask()
    fname = questionary.text("Enter filename (without extension):").ask()
    out_path = Path(f"{dir_path}/{fname}.{ 'csv' if fmt == 'CSV' else 'xlsx'}")

    try:
        if fmt == "CSV":
            df.to_csv(out_path, index=False)
        else:
            df.to_excel(out_path, index=False)
        console.print(f"[bold green]Exported to {out_path}[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Failed to export: {e}[/bold red]")

def check_wrong_journal_entry(df):
    transaction_col = questionary.select("Select the transaction ID column:", choices=list(df.columns)).ask()
    account_num_col = questionary.select("Select the account number column:", choices=list(df.columns)).ask()
    account_name_col = questionary.select("Select the account name column:", choices=list(df.columns)).ask()

    # Get user-specified account numbers to exclude
    account_excl_input = questionary.text("Enter specific account numbers to exclude (comma-separated):").ask()
    excluded_numbers = [acc.strip() for acc in account_excl_input.split(",") if acc.strip()]

    # Keywords to exclude based on account names
    keyword_input = questionary.text("Enter keywords to ignore in account names (comma-separated):").ask()
    ignore_keywords = [k.strip().lower() for k in keyword_input.split(",") if k.strip()]

    wrong_entries = []

    for tx_id, group in df.groupby(transaction_col):
        # Exclude group if any account name contains a keyword
        if group[account_name_col].astype(str).str.lower().str.contains('|'.join(re.escape(k) for k in ignore_keywords)).any():
            continue

        # Exclude group if any account number is in the excluded list
        if group[account_num_col].astype(str).isin(excluded_numbers).any():
            continue

        # BS/PnL detection
        account_nums = group[account_num_col].astype(str)
        has_bs = account_nums.str.startswith(("1", "2", "3")).any()
        has_pnl = account_nums.str.startswith(("4", "5", "6", "7")).any()

        if has_bs and has_pnl:
            wrong_entries.append(group)

    if wrong_entries:
        result_df = pd.concat(wrong_entries)
        console.print(f"[bold yellow]Found {len(result_df)} rows with invalid BS and PnL combination.[/bold yellow]")
        return result_df
    else:
        console.print("[bold green]No invalid combinations found.[/bold green]")
        return None


def main():
    console.print("[bold cyan]Wrong Journal Entry Checker App[/bold cyan]")
    dir_path = _ask_directory()
    file_path = select_csv_from_folder(dir_path)
    if not file_path:
        return
    df = read_csv_safely(file_path)
    if df is None:
        return
    flagged_df = check_wrong_journal_entry(df)
    export_dataframe(flagged_df, dir_path)

if __name__ == "__main__":
    main()
