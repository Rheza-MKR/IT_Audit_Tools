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
    do_check = questionary.confirm("Do you want to identify transactions with mixed BS and PnL accounts?", default=True).ask()
    if not do_check:
        return None

    transaction_col = questionary.select("Select the transaction ID column:", choices=list(df.columns)).ask()
    account_col = questionary.select("Select the account ID column:", choices=list(df.columns)).ask()

    wrong_entries = []

    for tx_id, group in df.groupby(transaction_col):
        account_series = group[account_col].astype(str)
        bs = account_series.str.startswith(("1", "2", "3")).any()
        pnl = account_series.str.startswith(("4", "5", "6", "7")).any()

        # Exclude 6.5.1.3 entries from PnL detection
        has_exception = account_series.str.contains(r"^6\.5\.1\.3$").any()
        exception_filtered = account_series[~account_series.str.contains(r"^6\.5\.1\.3$")]
        filtered_pnl = exception_filtered.str.startswith(("4", "5", "6", "7")).any()

        if bs and filtered_pnl:
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
