import pandas as pd
from rich.console import Console
from rich.table import Table
import questionary
import os

console = Console()

def read_csv_safely(path):
    """Robust CSV reader with fallback handling."""
    try:
        df = pd.read_csv(path, encoding="utf-8", on_bad_lines="skip")
        if len(df.columns) == 1:
            df = pd.read_csv(path, encoding="utf-8", sep=";", on_bad_lines="skip")
        return df
    except Exception as e:
        console.print(f"[bold red]Error reading file: {e}[/bold red]")
        return None

def summarize_csv(df):
    """Summarize row count, missing values, and duplicate records."""
    console.print("\n[bold blue] CSV Summary Report[/bold blue]")

    row_count = df.shape[0]
    console.print(f"[bold]Total Rows:[/bold] {row_count}")

    pk_column = questionary.select(
        "Select the primary key column:", choices=list(df.columns) + ["None"]
    ).ask()
    if pk_column == "None":
        pk_column = None

    console.print("\n[bold yellow]Missing Values Per Column:[/bold yellow]")
    for col in df.columns:
        missing = df[col].isna().sum()
        if missing > 0:
            console.print(f" - [red]{col}[/red]: {missing} missing")
        else:
            console.print(f" - [green]{col}[/green]: OK")

    if pk_column:
        missing_pk = df[pk_column].isna().sum()
        if missing_pk > 0:
            console.print(f"[bold red] Missing values in primary key '{pk_column}': {missing_pk}[/bold red]")
        else:
            console.print(f"[bold green] No missing values in primary key '{pk_column}'[/bold green]")

    if pk_column:
        dup_rows = df.duplicated(subset=[col for col in df.columns if col != pk_column]).sum()
        if dup_rows > 0:
            console.print(f"[bold red] Duplicates found (excluding primary key): {dup_rows}[/bold red]")
        else:
            console.print("[bold green] No duplicates found (excluding primary key)[/bold green]")
    else:
        dup_all = df.duplicated().sum()
        if dup_all > 0:
            console.print(f"[bold red] Duplicate full rows found: {dup_all}[/bold red]")
        else:
            console.print("[bold green] No duplicate rows found[/bold green]")

    console.print("[bold blue]Summary complete.[/bold blue]\n")

def select_csv_from_data_folder():
    """Choose a CSV file interactively from /data/."""
    folder = "./data"
    files = [f for f in os.listdir(folder) if f.endswith(".csv")]

    if not files:
        console.print("[bold red]No CSV files found in /data folder.[/bold red]")
        return None

    file_choice = questionary.select("Select a CSV file to summarize:", choices=files + ["Back"]).ask()
    return None if file_choice == "Back" else os.path.join(folder, file_choice)

def export_missing_rows(df):
    """Export rows with missing values in selected columns."""
    console.print("\n[bold cyan] Export Rows with Missing Data[/bold cyan]")

    while True:
        cols_input = questionary.text(
            "Enter column name(s) to check (comma-separated), or type 'cancel' to exit:"
        ).ask()

        if cols_input.strip().lower() == "cancel":
            return

        selected_cols = [col.strip() for col in cols_input.split(",")]
        invalid = [col for col in selected_cols if col not in df.columns]

        if invalid:
            console.print(f"[bold red]Invalid column(s): {', '.join(invalid)}[/bold red]")
            continue  # re-prompt
        else:
            break  # valid input

    missing_df = df[df[selected_cols].isnull().any(axis=1)]

    if missing_df.empty:
        console.print("[bold green] No missing values found in the selected column(s).[/bold green]")
        return

    file_format = questionary.select(
        "Choose the export format:", choices=["CSV", "XLSX"]
    ).ask()

    file_name = questionary.text("Enter the file name (without extension):").ask()

    export_path = f"./data/{file_name}." + ("csv" if file_format == "CSV" else "xlsx")

    try:
        if file_format == "CSV":
            missing_df.to_csv(export_path, index=False)
        else:
            missing_df.to_excel(export_path, index=False)
        console.print(f"[bold green] Exported {len(missing_df)} rows to {export_path}[/bold green]")
    except Exception as e:
        console.print(f"[bold red] Export failed: {e}[/bold red]")

def export_duplicate_rows(df):
    """Export duplicate rows based on user-selected subset of columns."""
    console.print("\n[bold cyan] Export Duplicate Rows[/bold cyan]")

    col_input = questionary.text(
        "Enter column name(s) to check for duplicates (comma-separated), or type 'cancel' to exit:"
    ).ask()

    if col_input.strip().lower() == "cancel":
        return

    selected_cols = [col.strip() for col in col_input.split(",")]
    invalid_cols = [col for col in selected_cols if col not in df.columns]

    if invalid_cols:
        console.print(f"[bold red]Invalid column(s): {', '.join(invalid_cols)}[/bold red]")
        return

    dup_df = df[df.duplicated(subset=selected_cols, keep=False)]

    if dup_df.empty:
        console.print("[bold green] No duplicate rows found for the selected columns.[/bold green]")
        return

    file_format = questionary.select(
        "Choose the export format:", choices=["CSV", "XLSX"]
    ).ask()

    file_name = questionary.text("Enter the file name (without extension):").ask()

    export_path = f"./data/{file_name}." + ("csv" if file_format == "CSV" else "xlsx")

    try:
        if file_format == "CSV":
            dup_df.to_csv(export_path, index=False)
        else:
            dup_df.to_excel(export_path, index=False)
        console.print(f"[bold green] Exported {len(dup_df)} duplicate rows to {export_path}[/bold green]")
    except Exception as e:
        console.print(f"[bold red] Export failed: {e}[/bold red]")

def main():
    console.print("[bold cyan]CSV Summarizer Tool[/bold cyan]")
    file_path = select_csv_from_data_folder()

    if file_path:
        df = read_csv_safely(file_path)
        if df is not None:
            summarize_csv(df)
            view_option = questionary.select(
                "Which rows do you want to view/export?",
                choices=["Missing Values", "Duplicate Rows", "Cancel"]
            ).ask()

            if view_option == "Missing Values":
                export_missing_rows(df)

            elif view_option == "Duplicate Rows":
                export_duplicate_rows(df)

if __name__ == "__main__":
    main()
