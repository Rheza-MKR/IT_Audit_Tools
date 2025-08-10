import os
from pathlib import Path
import pandas as pd
import questionary
from rich.console import Console

console = Console()

# ───────────────────────────── file helpers ─────────────────────────────
def _ask_directory() -> Path:
    while True:
        dir_path = Path(questionary.text("Enter the audit directory path:").ask()).expanduser().resolve()
        if dir_path.is_dir():
            return dir_path
        console.print(f"[bold red]Directory '{dir_path}' does not exist – try again.[/bold red]")

def list_data_files(directory: Path):
    return sorted([f.name for f in directory.glob("*.csv")] +
                  [f.name for f in directory.glob("*.xls")] +
                  [f.name for f in directory.glob("*.xlsx")])

def select_data_file_from_folder(directory: Path) -> Path | None:
    files = list_data_files(directory)
    if not files:
        console.print("[bold red]No CSV or Excel files found in the directory.[/bold red]")
        return None
    selected = questionary.select("Select a file to check:", choices=files + ["Back"]).ask()
    return None if selected == "Back" else directory / selected

def read_file_safely(path: Path) -> pd.DataFrame | None:
    try:
        if path.suffix.lower() in (".xls", ".xlsx"):
            return pd.read_excel(path)
        if path.suffix.lower() == ".csv":
            try:
                df = pd.read_csv(path, encoding="utf-8", on_bad_lines="skip")
                if len(df.columns) == 1:
                    df = pd.read_csv(path, encoding="utf-8", sep=";", on_bad_lines="skip")
                return df
            except Exception:
                return pd.read_csv(path, encoding="latin-1", on_bad_lines="skip")
        console.print(f"[bold red]Unsupported file type: {path.suffix}[/bold red]")
        return None
    except Exception as e:
        console.print(f"[bold red]Error reading file: {e}[/bold red]")
        return None

def export_dataframe(df: pd.DataFrame, directory: Path):
    export = questionary.confirm("Do you want to export the results?", default=True).ask()
    if not export:
        return

    file_format = questionary.select("Choose export format:", choices=["CSV", "XLSX"]).ask()
    file_name = questionary.text("Enter export file name (without extension):").ask()
    out_path = directory / f"{file_name}.{ 'csv' if file_format == 'CSV' else 'xlsx'}"
    try:
        if file_format == "CSV":
            df.to_csv(out_path, index=False)
        else:
            df.to_excel(out_path, index=False)
        console.print(f"[bold green]Exported {len(df)} entries to {out_path}[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Export failed: {e}[/bold red]")

# ───────────────────────────── core logic ─────────────────────────────
def check_improper_descriptions(df: pd.DataFrame) -> pd.DataFrame | None:
    txn_col = questionary.select("Select the Transaction ID column to group by:", choices=list(df.columns)).ask()
    desc_col = questionary.select("Select the column to check for short entries:", choices=list(df.columns)).ask()
    min_len = questionary.text("Minimum acceptable character length (e.g. 5):").ask()

    try:
        min_len = int(min_len)
    except ValueError:
        console.print("[bold red]Invalid number – aborting check.[/bold red]")
        return None

    # Create flag column
    df = df.copy()
    df["improper desc"] = df[desc_col].astype(str).str.len() < min_len

    # Find transaction groups with at least one flagged row
    flagged_txns = df.loc[df["improper desc"], txn_col].dropna().unique().tolist()
    result_df = df[df[txn_col].isin(flagged_txns)]

    if result_df.empty:
        console.print("[bold green]No improper entries based on description length.[/bold green]")
        return None

    console.print(f"[bold yellow]Found {len(result_df)} entries across {len(flagged_txns)} transactions[/bold yellow]")
    console.print(f"[bold blue]Flagged rows: {int(df['improper desc'].sum())}[/bold blue]")

    return result_df

# ───────────────────────────── entry point ─────────────────────────────
def main():
    console.print("[bold cyan]Improper Description Entries Checker[/bold cyan]")
    dir_path = _ask_directory()
    file_path = select_data_file_from_folder(dir_path)
    if not file_path:
        return
    df = read_file_safely(file_path)
    if df is None:
        return
    result_df = check_improper_descriptions(df)
    if result_df is not None:
        export_dataframe(result_df, dir_path)

if __name__ == "__main__":
    main()
