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

def clean_currency(series: pd.Series) -> pd.Series:
    """
    Robust currency normalizer:
    - Handles IDR strings like 'Rp 1.234.567', 'IDR -577000', '(577,000)', '1,234.56', '1.234,56'
    - Preserves negatives (leading '-' or parentheses)
    - Normalizes decimal/thousand separators heuristically
    - Formats as 'Rp 1,234,567' (no decimals; typical for IDR)
    Leaves unparseable values as-is.
    """
    def parse_money(val):
        if pd.isna(val):
            return val

        s = str(val).strip()
        if s == "":
            return pd.NA

        # Normalize unicode minus and trim
        s = s.replace("\u2212", "-")  # unicode minus → ascii

        # Detect parentheses negatives: (123,456)
        neg = False
        if s.startswith("(") and s.endswith(")"):
            neg = True
            s = s[1:-1].strip()

        # Keep only digits, comma, dot, minus
        s = re.sub(r"[^0-9,.\-]", "", s)

        # If minus appears not only at start, keep the first and drop the rest
        if s.count("-") > 1:
            s = "-" + s.replace("-", "")

        # Heuristics for separators
        has_comma = "," in s
        has_dot   = "." in s

        normalized = s
        if has_comma and has_dot:
            # Decide which is decimal: look at last separator
            last_comma = s.rfind(",")
            last_dot   = s.rfind(".")
            if last_comma > last_dot:
                # 1.234,56 → '.' thousands, ',' decimal
                normalized = s.replace(".", "").replace(",", ".")
            else:
                # 1,234.56 → ',' thousands, '.' decimal
                normalized = s.replace(",", "")
        elif has_comma and not has_dot:
            # Could be thousands or decimal.
            if s.count(",") > 1:
                # many commas ⇒ thousands
                normalized = s.replace(",", "")
            else:
                # single comma ⇒ treat as decimal
                normalized = s.replace(",", ".")
        elif has_dot and not has_comma:
            # Many dots ⇒ thousands; keep last dot as decimal
            if s.count(".") > 1:
                # remove all dots, but keep the last as decimal if it looks like decimal
                parts = s.split(".")
                if parts[-1].isdigit() and 1 <= len(parts[-1]) <= 2:
                    normalized = "".join(parts[:-1]) + "." + parts[-1]
                else:
                    normalized = s.replace(".", "")
            else:
                normalized = s

        # Ensure single leading minus
        neg = neg or normalized.startswith("-")
        normalized = normalized.lstrip("-")

        try:
            num = float(normalized)
            if neg:
                num = -num
            # IDR: no decimals
            return f"Rp {abs(num):,.0f}" if num >= 0 else f"-Rp {abs(num):,.0f}"
        except Exception:
            # leave original if not parseable
            return val

    return series.apply(parse_money)


def clean_datetime(series: pd.Series) -> pd.Series:
    """
    Parse mixed date/datetime strings.
    - If the non-null parsed values all have time == 00:00:00 → format as YYYY-MM-DD
    - Otherwise → format as YYYY-MM-DD HH:MM:SS
    Keeps unparseable values as-is.
    """
    # Try mixed parsing; keep tz out for consistent strings
    try:
        parsed = pd.to_datetime(series, errors="coerce", utc=False)
    except TypeError:
        # older pandas without flexible parsing path
        parsed = pd.to_datetime(series, errors="coerce")

    # If nothing parsed, return original
    if parsed.notna().sum() == 0:
        return series

    nonnull = parsed.dropna()
    # If any value has a time component (not equal to midnight), treat as datetime column
    has_time = (nonnull.dt.normalize() != nonnull).any()

    fmt = "%Y-%m-%d %H:%M:%S" if has_time else "%Y-%m-%d"
    out = parsed.dt.strftime(fmt)

    # keep originals where parsing failed
    out = out.where(parsed.notna(), series.astype(str))
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
        col_choice = questionary.checkbox(
            f"Select column(s) for {option}:", choices=list(df.columns)
        ).ask()

        if not col_choice:
            console.print(f"[yellow]Skipping {option} – no columns selected.[/yellow]")
            continue

        if option == "Currency Formatting":
            sugg = guess_currency_columns(df)
            console.print(f"[italic]Suggested currency-like columns:[/italic] {sugg or '— none detected —'}")
            col_choice = questionary.checkbox(
                "Select column(s) for Currency Formatting:",
                choices=prioritized_choices(list(df.columns), sugg)
            ).ask()

        elif option == "Datetime Formatting":
            sugg = guess_datetime_columns(df)
            console.print(f"[italic]Suggested date/datetime columns:[/italic] {sugg or '— none detected —'}")
            col_choice = questionary.checkbox(
                "Select column(s) for Datetime Formatting:",
                choices=prioritized_choices(list(df.columns), sugg)
            ).ask()
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
