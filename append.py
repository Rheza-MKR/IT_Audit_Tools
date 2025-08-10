import os
from pathlib import Path
import pandas as pd
import questionary
from rich.console import Console

console = Console()


def ask_directory() -> Path:
    while True:
        p = Path(questionary.path("📂  Enter folder containing CSV files:").ask()).expanduser()
        if p.is_dir():
            return p
        console.print(f"[bold red]Directory '{p}' not found – try again.[/bold red]")


def list_data_files(folder: Path):
    """List all CSV and Excel files in a folder."""
    return [f.name for f in folder.glob("*") if f.suffix.lower() in (".csv", ".xlsx", ".xls")]


def select_multiple_csv_files(folder: Path):
    files = list_data_files(folder)
    if not files:
        console.print("[bold red]No Excel/CSV files in that folder.[/bold red]")
        return None
    choices = questionary.checkbox("✅ Select files to append:", choices=files).ask()
    return choices if choices and len(choices) >= 2 else None


def read_file_safely(path: Path) -> pd.DataFrame | None:
    """Read CSV or Excel safely with multiple fallbacks."""
    try:
        if path.suffix.lower() in (".xlsx", ".xls"):
            return pd.read_excel(path)
        elif path.suffix.lower() == ".csv":
            # Try multiple read_csv configs
            for kwargs in (dict(), dict(sep=";"), dict(encoding="latin-1")):
                try:
                    return pd.read_csv(path, on_bad_lines="skip", low_memory=False, **kwargs)
                except Exception:
                    continue
        else:
            console.print(f"[bold red]❌ Unsupported file format: {path.suffix}[/bold red]")
            return None
    except Exception as e:
        console.print(f"[bold red]❌ Could not open {path.name}: {e}[/bold red]")
        return None


def append_unique_rows(folder: Path, files: list[str], unique_columns: list[str]):
    base_df = read_file_safely(folder / files[0])
    if base_df is None:
        return

    base_df = base_df.drop_duplicates(subset=unique_columns)

    for i in range(1, len(files)):
        next_df = read_file_safely(folder / files[i])
        if next_df is None:
            continue

        if set(base_df.columns) != set(next_df.columns):
            console.print(f"[bold red]Column mismatch. Skipping {files[i]}.[/bold red]")
            continue

        combined = pd.concat([base_df, next_df], ignore_index=True)
        duplicated = combined[combined.duplicated(subset=unique_columns, keep=False)]

        if not duplicated.empty:
            console.print(f"[bold yellow]⚠️  Found {len(duplicated)} duplicated rows from {files[i]}[/bold yellow]")
            if questionary.confirm("Do you want to export duplicated rows?").ask():
                fmt = questionary.select("Choose format:", choices=["CSV", "XLSX"]).ask()
                name = questionary.text("Enter file name (without extension):").ask()
                out_path = folder / f"{name}.{fmt.lower()}"
                if fmt == "CSV":
                    duplicated.to_csv(out_path, index=False)
                else:
                    duplicated.to_excel(out_path, index=False)
                console.print(f"[green]✅ Exported duplicated rows → {out_path}[/green]")

        base_df = pd.concat([base_df, next_df]).drop_duplicates(subset=unique_columns)

    console.print(f"[bold green]✅ Appending done. Final row count: {len(base_df)}[/bold green]")

    if questionary.confirm("Do you want to export the final combined table?").ask():
        fmt = questionary.select("Choose format:", choices=["CSV", "XLSX"]).ask()
        name = questionary.text("File name (without extension):").ask()
        out_path = folder / f"{name}.{fmt.lower()}"
        if fmt == "CSV":
            base_df.to_csv(out_path, index=False)
        else:
            base_df.to_excel(out_path, index=False)
        console.print(f"[bold green]✅ Final combined file saved → {out_path}[/bold green]")


def main():
    console.print("[bold cyan]CSV Append Unique Rows Tool[/bold cyan]")

    folder = ask_directory()
    files = select_multiple_csv_files(folder)
    if not files:
        console.print("[red]Please select at least two CSV files.[/red]")
        return

    sample_df = read_file_safely(folder / files[0])
    if sample_df is None:
        return

    unique_columns = questionary.checkbox("🔑 Select column(s) to define uniqueness:", choices=list(sample_df.columns)).ask()
    if not unique_columns:
        console.print("[red]❌ You must select at least one unique column.[/red]")
        return

    append_unique_rows(folder, files, unique_columns)


if __name__ == "__main__":
    main()
