import pandas as pd
import re
from pathlib import Path
import questionary
from rich.console import Console
import os
from utils.import_utils import read_file_safely
from questionary import Choice


console = Console()

# === FILE HANDLING ===

def _ask_directory():
    while True:
        dir_path = Path(questionary.text("Enter the directory path:").ask()).expanduser()
        if dir_path.is_dir():
            return dir_path
        console.print(f"[bold red]Directory '{dir_path}' does not exist – try again.[/bold red]")

def select_file_from_folder(directory):
    """List CSV & Excel files for selection."""
    files = [f for f in os.listdir(directory) if f.lower().endswith((".csv", ".xlsx", ".xls"))]
    if not files:
        console.print("[bold red]No CSV or Excel files found in this directory.[/bold red]")
        return None
    file_choice = questionary.select("Select a file to clean:", choices=files + ["Back"]).ask()
    return None if file_choice == "Back" else Path(directory) / file_choice

# === CLEAN-UP FUNCTIONS ===

def guess_currency_columns(df: pd.DataFrame) -> list[str]:
    pat = re.compile(r"(amount|amt|fee|price|total|balance|nilai|nominal)", re.I)
    return [c for c in df.columns if pat.search(str(c))]

def guess_datetime_columns(df: pd.DataFrame) -> list[str]:
    pat = re.compile(r"(date|datetime|time|created|updated|paid|settlement)", re.I)
    return [c for c in df.columns if pat.search(str(c))]

def prioritized_choices(all_cols, suggested):
    suggested_set = set(map(str, suggested))
    return (
        [Choice(title=f"★ {c}", value=c, checked=True) for c in all_cols if str(c) in suggested_set] +
        [Choice(title=str(c), value=c, checked=False) for c in all_cols if str(c) not in suggested_set]
    )

def _normalize_num_string(s: str) -> tuple[float | None, bool]:
    """
    Robust parser for money-like strings.
    Returns (float_value, success_flag).
    Handles: negatives, parentheses, 1,234.56 / 1.234,56 / Rp 1.234.567 etc.
    """
    if s is None:
        return None, False
    s = str(s).strip()
    if s == "":
        return None, False

    # parentheses for negatives: (123,456)
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1].strip()

    # normalize unicode minus
    s = s.replace("\u2212", "-")

    # keep only digits, comma, dot, minus
    s = re.sub(r"[^0-9,.\-]", "", s)

    # collapse multiple minus signs to a single leading minus
    if s.count("-") > 1:
        s = "-" + s.replace("-", "")
    leading_neg = s.startswith("-")
    s = s.lstrip("-")
    neg = neg or leading_neg

    if s == "":
        return None, False

    has_comma = "," in s
    has_dot = "." in s

    # Decide decimal vs thousands
    if has_comma and has_dot:
        # whichever separator occurs last in the string is the decimal
        last_c = s.rfind(",")
        last_d = s.rfind(".")
        if last_c > last_d:
            # 1.234,56 → '.' thousands, ',' decimal
            s = s.replace(".", "").replace(",", ".")
        else:
            # 1,234.56 → ',' thousands, '.' decimal
            s = s.replace(",", "")
    elif has_comma and not has_dot:
        # single comma likely decimal; many commas likely thousands
        if s.count(",") > 1:
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    elif has_dot and not has_comma:
        # many dots: treat as thousands separators unless last looks like decimal
        if s.count(".") > 1:
            parts = s.split(".")
            if parts[-1].isdigit() and 1 <= len(parts[-1]) <= 2:
                s = "".join(parts[:-1]) + "." + parts[-1]
            else:
                s = s.replace(".", "")

    try:
        val = float(s)
        if neg:
            val = -val
        return val, True
    except Exception:
        return None, False


def clean_currency_to_int(series: pd.Series) -> pd.Series:
    """
    Convert currency-like values to plain integer (nullable Int64).
    Examples:
      'Rp 1.234.567' -> 1234567
      '(577,000)'    -> -577000
      '1,234.56'     -> 1235   (rounded)
    Unparseable values become <NA>.
    """
    def to_int(val):
        if pd.isna(val):
            return pd.NA
        num, ok = _normalize_num_string(val)
        if not ok or num is None:
            return pd.NA
        # round to nearest integer (Rupiah has no fractional units)
        return int(round(num))
    out = series.apply(to_int)
    return out.astype("Int64")  # nullable integer dtype


def clean_datetime_ddmmyyyy(series: pd.Series) -> pd.Series:
    """
    Parse dates/datetimes.
    - If value has time component (not midnight) → 'ddmmyyyy HH:MM:SS'
    - Else → 'ddmmyyyy'
    Unparseable values remain unchanged.
    """
    # parse
    parsed = pd.to_datetime(series, errors="coerce", utc=False)

    # if entirely unparseable, keep original
    if parsed.notna().sum() == 0:
        return series

    # drop tz if any
    try:
        parsed = parsed.dt.tz_localize(None)
    except Exception:
        pass

    # Determine per-row if time exists (not normalized midnight)
    normalized = parsed.dt.normalize()
    has_time_mask = (parsed != normalized) & parsed.notna()

    # Build output strings
    out = series.astype(str)  # start with originals
    # rows with time
    out.loc[has_time_mask] = parsed.loc[has_time_mask].dt.strftime("%d%m%Y %H:%M:%S")
    # rows without time
    no_time_mask = parsed.notna() & (~has_time_mask)
    out.loc[no_time_mask] = parsed.loc[no_time_mask].dt.strftime("%d%m%Y")
    return out


def clean_phone(series):
    """Standardize Indonesian phone numbers."""
    def fix_phone(val):
        if pd.isna(val):
            return val
        s = re.sub(r"[^\d+]", "", str(val))  # keep only digits and '+'
        if s.startswith("62") and not s.startswith("+"):
            s = "+62" + s[2:]
        elif s.startswith("0"):
            pass  # already in local format
        elif s.startswith("+62"):
            pass  # already correct
        else:
            s = "0" + s  # fallback
        return s
    return series.apply(fix_phone)

# === MAIN FLOW ===

def main():
    console.print("[bold cyan]CSV/Excel Clean-Up Tool[/bold cyan]")
    dir_answer = _ask_directory()
    file_path = select_file_from_folder(dir_answer)
    if not file_path:
        return

    df = read_file_safely(file_path)
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
        # Ask per operation, showing suggestions BEFORE selection
        if option == "Currency Formatting":
            sugg = guess_currency_columns(df)
            console.print(f"[italic]Suggested currency-like columns:[/italic] {sugg or '— none detected —'}")
            cols = questionary.checkbox(
                "Select column(s) for Currency Formatting:",
                choices=prioritized_choices(list(df.columns), sugg)
            ).ask()
            if not cols:
                console.print("[yellow]Skipping Currency Formatting – no columns selected.[/yellow]")
                continue

            for col in cols:
                before = df[col].astype("string")
                df[col] = clean_currency_to_int(df[col])
                after = df[col].astype("string")
                changed = (before != after).sum()
                console.print(f"[green]✓ {col}:[/green] converted {changed} cells to integer")

        elif option == "Datetime Formatting":
            sugg = guess_datetime_columns(df)
            console.print(f"[italic]Suggested date/datetime columns:[/italic] {sugg or '— none detected —'}")
            cols = questionary.checkbox(
                "Select column(s) for Datetime Formatting:",
                choices=prioritized_choices(list(df.columns), sugg)
            ).ask()
            if not cols:
                console.print("[yellow]Skipping Datetime Formatting – no columns selected.[/yellow]")
                continue

            for col in cols:
                before = df[col].astype("string")
                df[col] = clean_datetime_ddmmyyyy(df[col])
                after = df[col].astype("string")
                changed = (before != after).sum()
                console.print(f"[green]✓ {col}:[/green] normalized {changed} date/datetime cells")

        elif option == "Phone Number Formatting":
            cols = questionary.checkbox(
                "Select column(s) for Phone Number Formatting:",
                choices=[Choice(title=str(c), value=c) for c in df.columns]
            ).ask()
            if not cols:
                console.print("[yellow]Skipping Phone Number Formatting – no columns selected.[/yellow]")
                continue

            for col in cols:
                before = df[col].astype("string")
                df[col] = clean_phone(df[col])
                after = df[col].astype("string")
                changed = (before != after).sum()
                console.print(f"[green]✓ {col}:[/green] standardized {changed} phone numbers")

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
