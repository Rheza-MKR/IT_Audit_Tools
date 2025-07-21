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

def detect_duplicates_groupby(df):
    date_col = questionary.select("Select the datetime/timestamp column:", choices=list(df.columns)).ask()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

    considered_cols = questionary.checkbox("Select columns to consider for duplication:", choices=[c for c in df.columns if c != date_col]).ask()

    time_unit = questionary.select("Select time unit:", choices=["minute", "hour", "day", "month", "year"]).ask()
    # Build the period columns based on the selected unit
    if time_unit == "day":
        group_keys = [df[date_col].dt.year, df[date_col].dt.month, df[date_col].dt.day]
    elif time_unit == "month":
        group_keys = [df[date_col].dt.year, df[date_col].dt.month]
    elif time_unit == "year":
        group_keys = [df[date_col].dt.year]
    elif time_unit == "hour":
        group_keys = [df[date_col].dt.year, df[date_col].dt.month, df[date_col].dt.day, df[date_col].dt.hour]
    elif time_unit == "minute":
        group_keys = [df[date_col].dt.year, df[date_col].dt.month, df[date_col].dt.day, df[date_col].dt.hour, df[date_col].dt.minute]
    else:
        raise ValueError("Unsupported time unit.")

    group_df = df.copy()
    group_df["_grp1"] = group_keys[0]
    for i, key in enumerate(group_keys[1:], 2):
        group_df[f"_grp{i}"] = key

    grp_cols = [f"_grp{i+1}" for i in range(len(group_keys))]
    result_idxs = []
    for _, group in group_df.groupby(grp_cols):
        group = group.sort_values(by=date_col)
        dups = group.duplicated(subset=considered_cols, keep=False)
        if dups.any():
            result_idxs.extend(group[dups].index.tolist())
    return df.loc[result_idxs].copy()

def detect_duplicates_within_period(df):
    date_col = questionary.select("Select the datetime/timestamp column:", choices=list(df.columns)).ask()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    considered_cols = questionary.checkbox("Select columns to consider for duplication:", choices=[c for c in df.columns if c != date_col]).ask()

    unit = questionary.select("Select interval unit:", choices=["seconds", "minutes", "hours", "days"]).ask()
    interval_val = int(questionary.text(f"Enter the number of {unit} for the interval (e.g. 2):").ask())
    df = df.sort_values(by=date_col).reset_index(drop=True)
    interval = pd.to_timedelta(f"{interval_val} {unit}")
    idxs = set()
    for i, row in df.iterrows():
        lower = row[date_col]
        upper = lower + interval
        mask = (df[date_col] > lower) & (df[date_col] <= upper)
        sub = df.loc[mask, :]
        for j, cmp_row in sub.iterrows():
            if all(row[col] == cmp_row[col] for col in considered_cols):
                idxs.add(i)
                idxs.add(j)
    return df.loc[sorted(idxs)].copy()

def main():
    console.print("[bold cyan]Time-based Duplicate Checker App[/bold cyan]")
    dir_path = _ask_directory()
    file_path = select_csv_from_folder(dir_path)
    if not file_path:
        return

    df = read_csv_safely(file_path)
    if df is None:
        return

    mode = questionary.select("Select checking mode:", choices=[
        "Group by time period",
        "Duplicate within time interval"
    ]).ask()

    if mode == "Group by time period":
        flagged_df = detect_duplicates_groupby(df)
    else:
        flagged_df = detect_duplicates_within_period(df)

    if not flagged_df.empty:
        console.print(f"[bold yellow]Found {len(flagged_df)} potential duplicates based on your selection.[/bold yellow]")
    else:
        console.print("[bold green]No duplicates found based on the selected criteria.[/bold green]")

    export_dataframe(flagged_df, dir_path)

if __name__ == "__main__":
    main()
