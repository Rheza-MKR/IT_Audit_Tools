import os
from pathlib import Path
import pandas as pd
import questionary
from rich.console import Console
import manual_entry
import improper_desc
import account_post

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
    
def check_directory(directory: Path):
    dir_manual_entry = directory / "manual_entry"
    dir_desc = directory / "description_check"
    dir_acc = directory / "account_post"
    dir_month = directory / "monthly_duplicate"
    dir_day = directory / "daily_duplicate"
    for subdir in [dir_manual_entry, dir_desc, dir_acc, dir_month, dir_day]:
        if not subdir.exists():
            subdir.mkdir(parents=True, exist_ok=True)
            print(f"[+] Created directory: {subdir}")

def export_dataframe(df: pd.DataFrame, dir_path: Path, file_name):
    if df is None:
        return

    out_path = dir_path / f"{file_name}.csv"
    try:
        df.to_csv(out_path, index=False)
    except Exception as e:
        console.print(f"[bold red]Failed to export: {e}[/bold red]")

def process_csv(directory: Path) -> Path:
    file_processed = 0
    csv_files = [f.name for f in directory.glob("*.csv")]
    if not csv_files:
        console.print("[bold red]No CSV files found in the directory.[/bold red]")
        return None
    check_directory(directory)

    for file_name in csv_files:
        file_path = directory / file_name
        console.print(f"[bold blue]Processing file: {file_path}[/bold blue]")
        df = read_csv_safely(file_path)
        if df is None:
            console.print(f"[bold red]Failed to read {file_path}[/bold red]")
            continue

        # Manual entry
        # df_manual_entry = manual_entry.recognize_alpha_in_transaction_id(df.copy())
        # if df_manual_entry is not None:
        #     export_dataframe(df_manual_entry, directory / "manual_entry", file_name[:-4] + "_manual_entry")
        # else:
        #     console.print(f"[bold yellow]No manual entry issues found in {file_name}.[/bold yellow]")

        # Improper description
        # df_improper_desc = improper_desc.check_improper_descriptions(df.copy())
        # if df_improper_desc is not None:
        #     export_dataframe(df_improper_desc, directory / "description_check", file_name[:-4] + "_improper_desc")
        # else:
        #     console.print(f"[bold yellow]No improper description issues found in {file_name}.[/bold yellow]")

        # Account posting
        df_account_post = account_post.check_wrong_journal_entry(df.copy())
        if df_account_post is not None:
            export_dataframe(df_account_post, directory / "account_post", file_name[:-4] + "_account_post")
        else:
            console.print(f"[bold yellow]No account posting issues found in {file_name}.[/bold yellow]")

        df_duplicate = account_post.check_wrong_journal_entry(df.copy())
        if df_duplicate is not None:
            export_dataframe(df_duplicate, directory / "duplicate_month", file_name[:-4] + "_duplicate_month")
        else:
            console.print(f"[bold yellow]No duplication found in {file_name}.[/bold yellow]")

        file_processed += 1
    return file_processed > 0


dir_path = _ask_directory()
sucess = process_csv(dir_path)

if sucess:
    console.print("[bold green]CSV files processed successfully.[/bold green]")
else :
    console.print("[bold red]No CSV files processed.[/bold red]")