import pandas as pd
from rich.console import Console
from pathlib import Path
import questionary
import os
import re

console = Console()

# ── File helpers ──────────────────────────────────────────────────────────
def _ask_directory() -> Path:
    while True:
        dir_path = Path(questionary.text("Enter the audit directory path:").ask()).expanduser().resolve()
        if dir_path.is_dir():
            return dir_path
        console.print(f"[bold red]Directory '{dir_path}' does not exist – try again.[/bold red]")

def _list_data_files(directory: Path):
    return sorted([f for f in os.listdir(directory) if f.lower().endswith((".csv", ".xls", ".xlsx"))])

def select_data_file_from_folder(directory):
    files = _list_data_files(directory)
    if not files:
        console.print("[bold red]No CSV/XLS/XLSX files found in the folder.[/bold red]")
        return None
    file_choice = questionary.select("Select a file to analyze:", choices=files + ["Back"]).ask()
    return None if file_choice == "Back" else os.path.join(directory, file_choice)

def read_file_safely(path: str | Path) -> pd.DataFrame | None:
    path = Path(path)
    try:
        ext = path.suffix.lower()
        if ext in (".xls", ".xlsx"):
            return pd.read_excel(path)
        if ext == ".csv":
            try:
                df = pd.read_csv(path, encoding="utf-8", on_bad_lines="skip")
                if len(df.columns) == 1:
                    df = pd.read_csv(path, encoding="utf-8", sep=";", on_bad_lines="skip")
                return df
            except Exception:
                return pd.read_csv(path, encoding="latin-1", on_bad_lines="skip")
        console.print(f"[bold red]Unsupported file type: {ext}[/bold red]")
        return None
    except Exception as e:
        console.print(f"[bold red]Error reading file: {e}[/bold red]")
        return None

def export_dataframe(df, dir_path):
    if df is None:
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

# ── Core logic ────────────────────────────────────────────────────────────
def recognize_alpha_in_transaction_id(df):
    do_check = questionary.confirm("Do you want to identify transactions with alphabetic characters in their transaction ID?", default=True).ask()
    if not do_check:
        return None

    transaction_col = questionary.select("Select the transaction ID column:", choices=list(df.columns)).ask()

    # Work on a copy to avoid mutating the caller unless they export
    result = df.copy()
    result["manual entry"] = result[transaction_col].astype(str).str.contains(r"[A-Za-z]", regex=True, na=False)

    if result["manual entry"].any():
        console.print(f"[bold yellow]Flagged {int(result['manual entry'].sum())} rows with alphabetic transaction IDs.[/bold yellow]")
        return result
    else:
        console.print("[bold green]No transactions with alphabetic characters found.[/bold green]")
        return None

# ── Entrypoint ───────────────────────────────────────────────────────────
def main():
    console.print("[bold cyan]Manual Entry Checker App[/bold cyan]")
    dir_path = _ask_directory()
    file_path = select_data_file_from_folder(dir_path)
    if not file_path:
        return
    df = read_file_safely(file_path)
    if df is None:
        return
    updated_df = recognize_alpha_in_transaction_id(df)
    export_dataframe(updated_df, dir_path)

if __name__ == "__main__":
    main()
