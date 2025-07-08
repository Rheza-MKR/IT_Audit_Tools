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

def extract_by_accounts(df):
    col = questionary.select("Select the column to assess:", choices=list(df.columns)).ask()
    account_input = questionary.text("Enter account values (comma-separated):").ask()
    accounts = [a.strip() for a in account_input.split(",") if a.strip()]

    filtered_df = df[df[col].astype(str).isin(accounts)]
    console.print(f"[bold green]Extracted {len(filtered_df)} rows where '{col}' matches given accounts.[/bold green]")
    return filtered_df

def recognize_pattern(df, dir_path):
    do_pattern = questionary.confirm("Do you want to recognize a pattern in a specific column?", default=True).ask()
    if not do_pattern:
        return

    target_col = questionary.select("Select the column to apply pattern recognition:", choices=list(df.columns)).ask()
    console.print("\n[bold blue]Pattern Explanation:[/bold blue]")
    console.print("^xx  = starts with 'xx'\nxx^  = ends with 'xx'\nxx   = contains 'xx' anywhere\n")

    pattern_input = questionary.text("Enter the pattern to search:").ask().strip()

    if pattern_input.startswith("^"):
        patt = f"^{re.escape(pattern_input[1:])}"
    elif pattern_input.endswith("^"):
        patt = f"{re.escape(pattern_input[:-1])}$"
    else:
        patt = f"{re.escape(pattern_input)}"

    matched_df = df[df[target_col].astype(str).str.contains(patt, regex=True, na=False)]

    console.print(f"[bold green]Found {len(matched_df)} rows matching pattern in '{target_col}'.[/bold green]")

    export = questionary.confirm("Do you want to export the result?", default=True).ask()
    if export:
        fmt = questionary.select("Select export format:", choices=["CSV", "XLSX"]).ask()
        fname = questionary.text("Enter filename (without extension):").ask()
        out_path = Path(f"{dir_path}/{fname}.{ 'csv' if fmt == 'CSV' else 'xlsx'}")
        try:
            if fmt == "CSV":
                matched_df.to_csv(out_path, index=False)
            else:
                matched_df.to_excel(out_path, index=False)
            console.print(f"[bold green]Exported to {out_path}[/bold green]")
        except Exception as e:
            console.print(f"[bold red]Failed to export: {e}[/bold red]")

def main():
    console.print("[bold cyan]Manual Entry Checker App[/bold cyan]")
    dir_path = _ask_directory()
    file_path = select_csv_from_folder(dir_path)

    if not file_path:
        return

    df = read_csv_safely(file_path)
    if df is None:
        return

    filtered_df = extract_by_accounts(df)
    recognize_pattern(filtered_df, dir_path)

if __name__ == "__main__":
    main()