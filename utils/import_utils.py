import os
from pathlib import Path
import pandas as pd
import questionary
from questionary import Choice
from rich.console import Console

console = Console()


def find_headers(path: Path, sheet_name: str | int = 0, max_rows: int = 20) -> int | None:
    """
    Try to detect the header row in an Excel sheet.
    Returns the row index (0-based) to use as header, or None if not found.

    Strategy:
    - Reads the first `max_rows` rows without headers.
    - Chooses the first row where all or most cells are non-null.
    """
    try:
        preview = pd.read_excel(path, sheet_name=sheet_name, header=None, nrows=max_rows)
    except Exception as e:
        console.print(f"[bold red]❌ Failed to preview Excel sheet: {e}[/bold red]")
        return None

    best_row = None
    best_non_nulls = 0
    for i, row in preview.iterrows():
        non_nulls = row.notna().sum()
        if non_nulls > best_non_nulls:
            best_non_nulls = non_nulls
            best_row = i

    if best_row is not None:
        console.print(f"[green]🔎 Auto-detected header row at index {best_row}[/green]")
    else:
        console.print("[yellow]⚠ No clear header row detected.[/yellow]")

    return best_row


def read_file_safely(path: Path) -> pd.DataFrame | None:
    """Read CSV or Excel safely with multiple fallbacks and interactive sheet pick."""
    try:
        ext = path.suffix.lower()
        if ext in (".xlsx", ".xls"):
            try:
                xl = pd.ExcelFile(path)
            except Exception as e:
                console.print(f"[bold red]❌ Failed opening Excel file: {e}[/bold red]")
                return None

            # Pick sheet
            sheet_name = xl.sheet_names[0]
            if len(xl.sheet_names) > 1:
                sheet_name = questionary.select("Select sheet:", choices=xl.sheet_names).ask()
                if not sheet_name:
                    console.print("[blue]No sheet selected. Exiting.[/blue]")
                    return None

            # Ask whether to auto detect header
            if questionary.confirm("Do you want to auto-detect the header row?", default=False).ask():
                header_row = find_headers(path, sheet_name=sheet_name)
                if header_row is not None:
                    return pd.read_excel(path, sheet_name=sheet_name, header=header_row)
                else:
                    console.print("[yellow]Falling back to default header=0[/yellow]")
                    return pd.read_excel(path, sheet_name=sheet_name, header=0)
            else:
                return pd.read_excel(path, sheet_name=sheet_name, header=0)

        elif ext == ".csv":
            for kwargs in (dict(), dict(sep=";"), dict(encoding="latin-1")):
                try:
                    return pd.read_csv(path, on_bad_lines="skip", low_memory=False, **kwargs)
                except Exception:
                    continue
            console.print(f"[bold red]❌ Could not read CSV with common fallbacks.[/bold red]")
            return None
        else:
            console.print(f"[bold red]❌ Unsupported file format: {path.suffix}[/bold red]")
            return None
    except Exception as e:
        console.print(f"[bold red]❌ Could not open {path.name}: {e}[/bold red]")
        return None
    
