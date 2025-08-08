import pandas as pd
import re
from pathlib import Path
import questionary
from rich.console import Console
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

# === CLEAN-UP FUNCTIONS ===

def clean_currency(series):
    """Remove non-numeric except decimal and format with thousands separator."""
    def fix_currency(val):
        if pd.isna(val):
            return val
        cleaned = re.sub(r"[^\d.]", "", str(val))
        try:
            num = float(cleaned)
            return f"Rp {num:,.0f}"
        except:
            return val
    return series.apply(fix_currency)

def clean_datetime(series):
    """Convert to standard YYYY-MM-DD or YYYY-MM-DD HH:MM:SS."""
    return pd.to_datetime(series, errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")

def clean_phone(series):
    """Standardize Indonesian phone numbers."""
    def fix_phone(val):
        if pd.isna(val):
            return val
        s = re.sub(r"[^\d+]", "", str(val))  # remove all non-numeric except +
        if s.startswith("62") and not s.startswith("+"):
            s = "+62" + s[2:]
        elif s.startswith("0"):
            pass  # keep as is
        elif s.startswith("+62"):
            pass  # already correct
        else:
            s = "0" + s  # fallback
        return s
    return series.apply(fix_phone)

def _ask_directory():
    while True:
        dir_path = Path(questionary.text("Enter the directory path:").ask()).expanduser()
        if dir_path.is_dir():
            return dir_path
        console.print(f"[bold red]Directory '{dir_path}' does not exist – try again.[/bold red]")

def select_csv_from_folder(directory):
    files = [f for f in os.listdir(directory) if f.endswith(".csv")]
    if not files:
        console.print("[bold red]No CSV files found in this directory.[/bold red]")
        return None
    file_choice = questionary.select("Select a CSV file to clean:", choices=files + ["Back"]).ask()
    return None if file_choice == "Back" else os.path.join(directory, file_choice)

def main():
    console.print("[bold cyan]CSV Clean-Up Tool[/bold cyan]")
    dir_answer = _ask_directory()
    file_path = select_csv_from_folder(dir_answer)
    if not file_path:
        return

    df = read_csv_safely(file_path)
    if df is None:
        return

    clean_options = questionary.checkbox(
        "Select clean-up operations:",
        choices=["Currency Formatting", "Datetime Formatting", "Phone Number Formatting"]
    ).ask()

    if not clean_options:
        console.print("[bold red]No clean-up option selected.[/bold red]")
        return

    for option in clean_options:
        col_choice = questionary.checkbox(
            f"Select column(s) for {option}:", choices=list(df.columns)
        ).ask()

        if not col_choice:
            console.print(f"[yellow]Skipping {option} – no columns selected.[/yellow]")
            continue

        if option == "Currency Formatting":
            for col in col_choice:
                df[col] = clean_currency(df[col])
        elif option == "Datetime Formatting":
            for col in col_choice:
                df[col] = clean_datetime(df[col])
        elif option == "Phone Number Formatting":
            for col in col_choice:
                df[col] = clean_phone(df[col])

    # Export cleaned file
    if questionary.confirm("Do you want to export the cleaned file?").ask():
        file_format = questionary.select("Choose export format:", choices=["CSV", "XLSX"]).ask()
        file_name = questionary.text("Enter the file name (without extension):").ask()
        export_path = Path(dir_answer) / f"{file_name}.{file_format.lower()}"

        try:
            if file_format == "CSV":
                df.to_csv(export_path, index=False)
            else:
                df.to_excel(export_path, index=False)
            console.print(f"[bold green]Exported cleaned file to {export_path}[/bold green]")
        except Exception as e:
            console.print(f"[bold red]Export failed: {e}[/bold red]")

if __name__ == "__main__":
    main()
