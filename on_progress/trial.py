import os
from datetime import timedelta

import pandas as pd
import numpy as np
import questionary
from rich.console import Console
from rich.table import Table

console = Console()

DATA_DIR = "./data"

def read_csv(path: str) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(path, encoding="utf-8", on_bad_lines="skip")
        if len(df.columns) == 1:
            df = pd.read_csv(path, encoding="utf-8", sep=";", on_bad_lines="skip")
        return df
    except Exception as e:
        console.print(f"[bold red] Failed to read {path}: {e}[/bold red]")
        return None

def detect_near_duplicates(df: pd.DataFrame, timestamp_col: str, detail_cols: list[str], threshold_seconds: int = 60) -> pd.DataFrame:
    work_df = df.copy()
    work_df[timestamp_col] = pd.to_datetime(work_df[timestamp_col], errors="coerce")

    work_df = work_df.dropna(subset=[timestamp_col])
    work_df = work_df.sort_values(by=detail_cols + [timestamp_col]).reset_index(drop=True)

    grouped = work_df.groupby(detail_cols, sort=False)

    duplicate_indices = set()
    for _, group in grouped:
        timestamps = group[timestamp_col].to_list()
        indices = group.index.to_list()

        current_cluster = [indices[0]]

        for i in range(1, len(timestamps)):
            time_diff = abs((timestamps[i] - timestamps[i - 1]).total_seconds())

            if time_diff <= threshold_seconds:
                # Continue the cluster
                current_cluster.append(indices[i])
            else:
                # If cluster size > 1, save it
                if len(current_cluster) > 1:
                    duplicate_indices.update(current_cluster)
                # Start a new potential cluster
                current_cluster = [indices[i]]

        # Final cluster check
        if len(current_cluster) > 1:
            duplicate_indices.update(current_cluster)

    duplicates_df = work_df.loc[sorted(duplicate_indices)].reset_index(drop=True)
    return duplicates_df


def list_csv_files(directory: str) -> list[str]:
    return [f for f in os.listdir(directory) if f.lower().endswith(".csv")]


def choose_csv_file() -> str | None:
    files = list_csv_files(DATA_DIR)
    if not files:
        console.print("[bold red]No CSV files found in ./data directory.[/bold red]")
        return None
    choice = questionary.select("Select a CSV file to analyse:", choices=files + ["Cancel"]).ask()
    return None if choice == "Cancel" else os.path.join(DATA_DIR, choice)


def choose_timestamp_column(df: pd.DataFrame) -> str | None:
    col = questionary.select("Select the timestamp column:", choices=list(df.columns) + ["Cancel"]).ask()
    return None if col == "Cancel" else col


def choose_detail_columns(df: pd.DataFrame) -> list[str] | None:
    cols = questionary.checkbox(
        "Select column(s) that define a transaction (space to toggle, enter to confirm):",
        choices=list(df.columns),
    ).ask()
    if not cols:
        console.print("[bold red] You must choose at least one detail column.[/bold red]")
        return None
    return cols


def show_dataframe(df: pd.DataFrame, title: str):
    table = Table(show_header=True, header_style="bold magenta", title=title)
    for col in df.columns:
        table.add_column(str(col))
    for _, row in df.iterrows():
        table.add_row(*[str(row[c]) for c in df.columns])
    console.print(table)


def export_dataframe(df: pd.DataFrame, default_name: str):
    file_format = questionary.select("Export format:", choices=["CSV", "XLSX", "Cancel"]).ask()
    if file_format == "Cancel":
        return
    file_name = questionary.text("Enter file name (without extension):", default=default_name).ask()
    if not file_name:
        console.print("[bold red] No file name provided. Export aborted.[/bold red]")
        return
    path = f"./data/{file_name}." + ("csv" if file_format == "CSV" else "xlsx")
    try:
        if file_format == "CSV":
            df.to_csv(path, index=False)
        else:
            df.to_excel(path, index=False)
        console.print(f"[bold green] Duplicates exported to {path}[/bold green]")
    except Exception as e:
        console.print(f"[bold red] Failed to export: {e}[/bold red]")


def main():
    console.print("[bold cyan] Time Based Duplicate‑Detection Tool [/bold cyan]")

    file_path = choose_csv_file()
    if file_path is None:
        return

    df = read_csv(file_path)
    if df is None or df.empty:
        return

    ts_col = choose_timestamp_column(df)
    if ts_col is None:
        return

    detail_cols = choose_detail_columns(df)
    if detail_cols is None:
        return

    duplicates = detect_near_duplicates(df, ts_col, detail_cols, threshold_seconds=60)

    if duplicates.empty:
        console.print("[bold green] No near‑duplicate transactions found![/bold green]")
        return

    console.print(f"[bold yellow] Found {len(duplicates)} potential duplicates.[/bold yellow]")
    show_dataframe(duplicates.head(20), title="Duplicate Preview (first 20 rows)")

    if questionary.confirm("Export all duplicates?").ask():
        export_dataframe(duplicates, default_name="duplicates")


if __name__ == "__main__":
    main()