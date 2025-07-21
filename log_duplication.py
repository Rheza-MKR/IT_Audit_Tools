import pandas as pd
from datetime import timedelta
from rich.console import Console
from pathlib import Path
import questionary
import os

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

    export = questionary.confirm("Do you want to export the detected duplicates?", default=True).ask()
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

def detect_duplicates_within_period(df):
    date_col = questionary.select("Select the date/timestamp column:", choices=list(df.columns)).ask()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

    unit_choices = ["minutes", "hours", "days"]
    unit = questionary.select("Select the time unit for checking duplicates:", choices=unit_choices).ask()
    value = questionary.text(f"Enter the time threshold in {unit} (e.g., 10):").ask()

    try:
        value = int(value)
    except ValueError:
        console.print("[bold red]Invalid number – aborting.[/bold red]")
        return None

    considered_columns = questionary.checkbox("Select the columns to consider for duplicate detection:", choices=list(df.columns)).ask()

    df_sorted = df.sort_values(by=date_col).copy()
    df_sorted["duplicate_flag"] = False

    for i in range(1, len(df_sorted)):
        current = df_sorted.iloc[i]
        prev = df_sorted.iloc[i - 1]

        time_diff = (current[date_col] - prev[date_col])
        threshold = pd.to_timedelta(value, unit=unit)

        if time_diff <= threshold and all(current[col] == prev[col] for col in considered_columns):
            df_sorted.loc[df_sorted.index[i], "duplicate_flag"] = True
            df_sorted.loc[df_sorted.index[i - 1], "duplicate_flag"] = True

    duplicates_df = df_sorted[df_sorted["duplicate_flag"]]
    if not duplicates_df.empty:
        console.print(f"[bold yellow]Detected {len(duplicates_df)} rows with duplicates within {value} {unit}.[/bold yellow]")
        return duplicates_df.drop(columns=["duplicate_flag"])
    else:
        console.print("[bold green]No duplicates detected within the specified period.[/bold green]")
        return None

def main():
    console.print("[bold cyan]Duplicate Within Time Period Checker[/bold cyan]")
    dir_path = _ask_directory()
    file_path = select_csv_from_folder(dir_path)
    if not file_path:
        return
    df = read_csv_safely(file_path)
    if df is None:
        return
    dup_df = detect_duplicates_within_period(df)
    export_dataframe(dup_df, dir_path)

if __name__ == "__main__":
    main()