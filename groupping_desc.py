import pandas as pd
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

    export = questionary.confirm("Do you want to export the grouped summary?", default=True).ask()
    if not export:
        return

    fmt = questionary.select("Select export format:", choices=["CSV", "XLSX"]).ask()
    fname = questionary.text("Enter filename (without extension):").ask()
    out_path = Path(f"{dir_path}/{fname}.{ 'csv' if fmt == 'CSV' else 'xlsx'}")

    try:
        if fmt == "CSV":
            df.to_csv(out_path)
        else:
            df.to_excel(out_path)
        console.print(f"[bold green]Exported to {out_path}[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Failed to export: {e}[/bold red]")

def sum_of_grouped_desc(df):
    desc_col = questionary.select("Select the description column:", choices=list(df.columns)).ask()
    debit_col = questionary.select("Select the debit column:", choices=list(df.columns)).ask()
    credit_col = questionary.select("Select the credit column:", choices=list(df.columns)).ask()
    keyword_input = questionary.text("Enter keywords to group by (comma-separated, case-insensitive):").ask()

    keywords = [k.strip().lower() for k in keyword_input.split(",") if k.strip()]

    data = []
    for keyword in keywords:
        mask = df[desc_col].astype(str).str.lower().str.contains(keyword, na=False)
        debit_sum = df.loc[mask, debit_col].fillna(0).astype(float).sum()
        credit_sum = df.loc[mask, credit_col].fillna(0).astype(float).sum()
        data.append({
            "Keyword": keyword,
            "Debit": debit_sum,
            "Credit": credit_sum
        })

    result_df = pd.DataFrame(data).set_index("Keyword")
    return result_df

def main():
    console.print("[bold cyan]Sum of Grouped Description App[/bold cyan]")
    dir_path = _ask_directory()
    file_path = select_csv_from_folder(dir_path)
    if not file_path:
        return
    df = read_csv_safely(file_path)
    if df is None:
        return
    summary_df = sum_of_grouped_desc(df)
    console.print(summary_df)
    export_dataframe(summary_df, dir_path)

if __name__ == "__main__":
    main()