import pandas as pd
from rich.console import Console
from pathlib import Path
import questionary

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

def select_data_file_from_folder(directory: Path):
    files = list_data_files(directory)
    if not files:
        console.print("[bold red]No CSV or Excel files found in the folder.[/bold red]")
        return None
    file_choice = questionary.select("Select a file to analyze:", choices=files + ["Back"]).ask()
    return None if file_choice == "Back" else directory / file_choice

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

def export_dataframe(df, dir_path: Path):
    if df is None or df.empty:
        console.print("[bold yellow]No data to export.[/bold yellow]")
        return

    export = questionary.confirm("Do you want to export the grouped summary?", default=True).ask()
    if not export:
        return

    fmt = questionary.select("Select export format:", choices=["CSV", "XLSX"]).ask()
    fname = questionary.text("Enter filename (without extension):").ask()
    out_path = dir_path / f"{fname}.{'csv' if fmt == 'CSV' else 'xlsx'}"

    try:
        if fmt == "CSV":
            df.to_csv(out_path)
        else:
            df.to_excel(out_path)
        console.print(f"[bold green]Exported to {out_path}[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Failed to export: {e}[/bold red]")

# ───────────────────────────── core logic ─────────────────────────────
def sum_of_grouped_desc(df: pd.DataFrame):
    desc_col = questionary.select("Select the description column:", choices=list(df.columns)).ask()
    debit_col = questionary.select("Select the debit column:", choices=list(df.columns)).ask()
    credit_col = questionary.select("Select the credit column:", choices=list(df.columns)).ask()
    keyword_input = questionary.text("Enter keywords to group by (comma-separated, case-insensitive):").ask()

    keywords = [k.strip().lower() for k in keyword_input.split(",") if k.strip()]

    # Try to coerce debit/credit to numeric safely (commas etc.)
    def _to_num(s):
        return pd.to_numeric(pd.Series(s).astype(str).str.replace(r"[^\d\.\-]", "", regex=True),
                             errors="coerce").fillna(0.0)

    debit_num  = _to_num(df[debit_col])
    credit_num = _to_num(df[credit_col])

    data = []
    for keyword in keywords:
        mask = df[desc_col].astype(str).str.lower().str.contains(keyword, na=False)
        debit_sum = float(debit_num[mask].sum())
        credit_sum = float(credit_num[mask].sum())
        data.append({
            "Keyword": keyword,
            "Debit": debit_sum,
            "Credit": credit_sum
        })

    result_df = pd.DataFrame(data).set_index("Keyword")
    return result_df

# ───────────────────────────── entry point ─────────────────────────────
def main():
    console.print("[bold cyan]Sum of Grouped Description App[/bold cyan]")
    dir_path = _ask_directory()
    file_path = select_data_file_from_folder(dir_path)
    if not file_path:
        return
    df = read_file_safely(file_path)
    if df is None:
        return
    summary_df = sum_of_grouped_desc(df)
    console.print(summary_df)
    export_dataframe(summary_df, dir_path)

if __name__ == "__main__":
    main()
