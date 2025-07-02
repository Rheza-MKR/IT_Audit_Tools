import pandas as pd
import os
import questionary
from rich.console import Console
from rich.table import Table

console = Console()

def list_csv_files():
    files = [f for f in os.listdir('./data/') if f.endswith('.csv')]
    return files


def select_multiple_csv_files():
    files = list_csv_files()
    if not files:
        console.print("[bold red]No CSV files found in the ./data directory.[/bold red]")
        return None
    choices = questionary.checkbox("Select CSV files to append:", choices=files).ask()
    return choices if choices and len(choices) >= 2 else None


def read_csv_safely(file):
    try:
        df = pd.read_csv('./data/' + file, encoding='utf-8', delimiter=',', on_bad_lines='skip')
        return df
    except Exception as e:
        console.print(f"[bold red]Failed to read {file}: {e}[/bold red]")
        return None


def append_unique_rows(files, unique_columns):
    base_df = read_csv_safely(files[0])
    if base_df is None:
        return

    base_df = base_df.drop_duplicates(subset=unique_columns)

    for i in range(1, len(files)):
        next_df = read_csv_safely(files[i])
        if next_df is None:
            continue

        # Check if columns match
        if set(base_df.columns) != set(next_df.columns):
            console.print(f"[bold red]Column mismatch between files. Skipping {files[i]}.[/bold red]")
            continue

        combined_df = pd.concat([base_df, next_df], ignore_index=True)
        combined_df = combined_df.drop_duplicates(subset=unique_columns, keep=False)

        duplicates = pd.concat([base_df, next_df], ignore_index=True).duplicated(subset=unique_columns, keep=False)
        duplicated_rows = pd.concat([base_df, next_df], ignore_index=True)[duplicates]

        if not duplicated_rows.empty:
            console.print(f"[bold yellow]Found {len(duplicated_rows)} duplicated rows when appending {files[i]}.[/bold yellow]")
            if questionary.confirm("Do you want to export duplicated rows?").ask():
                file_format = questionary.select("Choose export format:", choices=["CSV", "XLSX"]).ask()
                file_name = questionary.text("Enter the file name (without extension):").ask()

                if file_format == "CSV":
                    duplicated_rows.to_csv(f'./data/{file_name}.csv', index=False)
                    console.print(f"[bold green]Duplicated rows exported to {file_name}.csv[/bold green]")
                elif file_format == "XLSX":
                    duplicated_rows.to_excel(f'./data/{file_name}.xlsx', index=False)
                    console.print(f"[bold green]Duplicated rows exported to {file_name}.xlsx[/bold green]")

        base_df = pd.concat([base_df, next_df]).drop_duplicates(subset=unique_columns)

    console.print("[bold green]Appending completed. Unique records retained.[/bold green]")
    if questionary.confirm("Do you want to export the final combined table?").ask():
        file_format = questionary.select("Choose export format:", choices=["CSV", "XLSX"]).ask()
        file_name = questionary.text("Enter the file name (without extension):").ask()

        if file_format == "CSV":
            base_df.to_csv(f'./data/{file_name}.csv', index=False)
            console.print(f"[bold green]Final combined table exported to {file_name}.csv[/bold green]")
        elif file_format == "XLSX":
            base_df.to_excel(f'./data/{file_name}.xlsx', index=False)
            console.print(f"[bold green]Final combined table exported to {file_name}.xlsx[/bold green]")


def main():
    console.print("[bold cyan]CSV Append Unique Rows Tool[/bold cyan]")
    files = select_multiple_csv_files()
    if not files:
        console.print("[bold red]Please select at least two CSV files to append.[/bold red]")
        return

    sample_df = read_csv_safely(files[0])
    if sample_df is None:
        return

    unique_columns = questionary.checkbox("Select the column(s) that should be unique:", choices=list(sample_df.columns)).ask()
    if not unique_columns:
        console.print("[bold red]You must select at least one unique column.[/bold red]")
        return

    append_unique_rows(files, unique_columns)


if __name__ == "__main__":
    main()
