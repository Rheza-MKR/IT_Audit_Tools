import os
from pathlib import Path
import pandas as pd
import questionary
from rich.console import Console

console = Console()

def _ask_directory() -> Path:
    while True:
        dir_path = Path(questionary.text("Enter the audit directory path:").ask()).expanduser()
        if dir_path.is_dir():
            return dir_path
        console.print(f"[bold red]Directory '{dir_path}' does not exist – try again.[/bold red]")

def read_csv_safely(path: Path) -> pd.DataFrame:
    try:
        df = pd.read_csv(path, encoding="utf-8", on_bad_lines="skip")
        if len(df.columns) == 1:
            df = pd.read_csv(path, encoding="utf-8", sep=";", on_bad_lines="skip")
        return df
    except Exception as e:
        console.print(f"[bold red]Error reading file: {e}[/bold red]")
        return None

def select_csv_from_folder(directory: Path) -> Path:
    csv_files = [f.name for f in directory.glob("*.csv")]
    if not csv_files:
        console.print("[bold red]No CSV files found in the directory.[/bold red]")
        return None
    selected = questionary.select("Select a CSV file to check:", choices=csv_files + ["Back"]).ask()
    return None if selected == "Back" else directory / selected

def check_improper_descriptions(df: pd.DataFrame, directory: Path):
    while True:
        # Select group column
        txn_col = questionary.select("Select the Transaction ID column to group by:", choices=list(df.columns)).ask()

        # Select description column to check
        desc_col = questionary.select("Select the column to check for short entries:", choices=list(df.columns)).ask()
        min_len = questionary.text("Minimum acceptable character length (e.g. 5):").ask()

        try:
            min_len = int(min_len)
        except ValueError:
            console.print("[bold red]Invalid number – aborting check.[/bold red]")
            return

        # Identify group IDs where any row fails the length check
        short_desc_groups = (
            df[df[desc_col].astype(str).str.len() < min_len][txn_col]
            .dropna()
            .unique()
            .tolist()
        )

        result_df = df[df[txn_col].isin(short_desc_groups)]

        if result_df.empty:
            console.print("[bold green]No improper entries based on description length.[/bold green]")
            if not questionary.confirm("Do you want to check another column?", default=False).ask():
                break
            continue

        console.print(f"[bold yellow]Found {len(result_df)} entries across {len(short_desc_groups)} transactions[/bold yellow]")

        # ✅ Ask BEFORE additional filter logic
        filter_more = questionary.confirm("Do you want to filter further by another column?", default=False).ask()

        if filter_more:
            logic_type = questionary.select(
                "How should filters be combined?",
                choices=["AND (intersection)", "OR (append without duplicates)"]
            ).ask()

            while True:
                filter_col = questionary.select(
                    "Select a column to filter by:",
                    choices=[c for c in df.columns if c not in (desc_col, txn_col)] + ["<Done>"]
                ).ask()

                if filter_col == "<Done>":
                    break

                unique_values = df[filter_col].dropna().astype(str).unique().tolist()
                selected_values = questionary.checkbox(
                    f"Select value(s) in '{filter_col}' to include:", choices=unique_values
                ).ask()

                if selected_values:
                    filter_condition = df[filter_col].astype(str).isin(selected_values)
                    if logic_type.startswith("AND"):
                        result_df = result_df[filter_condition.loc[result_df.index]]
                    else:
                        result_df = pd.concat([result_df, df[filter_condition & df[txn_col].isin(short_desc_groups)]]).drop_duplicates()

        # ✅ Export
        export = questionary.confirm("Do you want to export the results?", default=True).ask()
        if export:
            file_format = questionary.select("Choose export format:", choices=["CSV", "XLSX"]).ask()
            file_name = questionary.text("Enter export file name (without extension):").ask()
            out_path = directory / f"{file_name}.{ 'csv' if file_format == 'CSV' else 'xlsx'}"
            try:
                if file_format == "CSV":
                    result_df.to_csv(out_path, index=False)
                else:
                    result_df.to_excel(out_path, index=False)
                console.print(f"[bold green]Exported {len(result_df)} entries to {out_path}[/bold green]")
            except Exception as e:
                console.print(f"[bold red]Export failed: {e}[/bold red]")

        # ✅ After export or skip, exit loop
        break


def main():
    console.print("[bold cyan]Improper Description Entries Checker[/bold cyan]")
    dir_path = _ask_directory()
    file_path = select_csv_from_folder(dir_path)
    if file_path:
        df = read_csv_safely(file_path)
        if df is not None:
            check_improper_descriptions(df, dir_path)

if __name__ == "__main__":
    main()
