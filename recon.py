import pandas as pd
import os
import inquirer
from pathlib import Path
from rich.console import Console
import questionary

console = Console()

# ───────────────────────── file helpers ─────────────────────────

def _ask_directory() -> Path:
    while True:
        dir_path = Path(questionary.text("Enter the audit directory path:").ask()).expanduser().resolve()
        if dir_path.is_dir():
            return dir_path
        console.print(f"[bold red]Directory '{dir_path}' does not exist – try again.[/bold red]")

def _list_tabular_files(directory: Path):
    """CSV & Excel."""
    return sorted([f for f in os.listdir(directory) if f.lower().endswith((".csv", ".xlsx", ".xls"))])

def select_file_from_folder(directory: Path, prompt="Select a file to analyze:") -> Path | None:
    files = _list_tabular_files(directory)
    if not files:
        console.print("[bold red]No CSV or Excel files found in the selected directory.[/bold red]")
        return None
    answer = inquirer.prompt([inquirer.List("file", message=prompt, choices=files)])
    return (Path(directory) / answer["file"]) if answer else None

def read_table_safely(path: Path) -> pd.DataFrame | None:
    """Open CSV or Excel with a couple of fallbacks."""
    try:
        suf = path.suffix.lower()
        if suf in (".xlsx", ".xls"):
            return pd.read_excel(path)
        # CSV branch
        try:
            df = pd.read_csv(path, encoding="utf-8", on_bad_lines="skip")
            if len(df.columns) == 1:  # wrong delimiter?
                df = pd.read_csv(path, encoding="utf-8", sep=";", on_bad_lines="skip")
            return df
        except Exception:
            return pd.read_csv(path, encoding="latin-1", on_bad_lines="skip")
    except Exception as e:
        console.print(f"[bold red]Error reading {path.name}: {e}[/bold red]")
        return None

def get_columns(file_path: Path):
    """Read just enough to get columns (CSV or Excel)."""
    try:
        if file_path.suffix.lower() in (".xlsx", ".xls"):
            df = pd.read_excel(file_path, nrows=1)
        else:
            df = pd.read_csv(file_path, encoding="utf-8", on_bad_lines="skip", nrows=1)
            if len(df.columns) == 1:
                df = pd.read_csv(file_path, encoding="utf-8", sep=";", on_bad_lines="skip", nrows=1)
        return df.columns.tolist()
    except Exception as e:
        print(f"Error reading {file_path.name}: {e}")
        return []

def select_column(columns, prompt):
    answer = inquirer.prompt([inquirer.List("column", message=prompt, choices=columns)])
    return answer["column"] if answer else None

# ───────────────────────── recon logic ─────────────────────────

def check_data_format(df: pd.DataFrame, column: str):
    """Quick hygiene checks; non-fatal."""
    errors = []
    # check missing BEFORE coercing to str
    if df[column].isna().any():
        errors.append("Missing values detected.")
    s = df[column].astype(str).str.strip()
    # special chars (non word/space)
    if s.str.contains(r"[^\w\s]", regex=True, na=False).any():
        errors.append("Special characters detected.")
    # numeric & negatives
    numeric_mask = s.str.replace(".", "", 1, regex=False).str.isnumeric()
    if numeric_mask.all():
        try:
            if (s.astype(float) < 0).any():
                errors.append("Negative values detected.")
        except Exception:
            pass
    return errors

def select_reconcile_method():
    q = [inquirer.List(
        "reconcile_method",
        message="Select reconciliation method:",
        choices=["Standard (full match)", "First N characters", "Last N characters"]
    )]
    ans = inquirer.prompt(q)
    method = ans["reconcile_method"] if ans else None

    num_chars = None
    if method in ["First N characters", "Last N characters"]:
        num_chars_input = inquirer.text("Enter number of characters:")
        try:
            num_chars = int(num_chars_input)
        except Exception:
            print("Invalid number.")
            return None, None
    return method, num_chars

def select_export_format():
    ans = inquirer.prompt([inquirer.List("export_format",
                                         message="Select an export format:",
                                         choices=["CSV", "XLSX"])])
    return ans["export_format"] if ans else None

def _export_df(df: pd.DataFrame, out_path: Path):
    try:
        if out_path.suffix.lower() == ".csv":
            df.to_csv(out_path, index=False)
        else:
            df.to_excel(out_path, index=False)
        print(f"Saved: {out_path}")
    except Exception as e:
        print(f"Error saving: {e}")

def reconcile_files(file1_path: Path, file2_path: Path, key_column1: str, key_column2: str, method: str, num_chars: int | None):
    df1 = read_table_safely(file1_path)
    df2 = read_table_safely(file2_path)
    if df1 is None or df2 is None:
        return None

    errors1 = check_data_format(df1, key_column1)
    errors2 = check_data_format(df2, key_column2)

    if errors1 or errors2:
        print("\nData Format Issues:")
        if errors1:
            print(f" - {file1_path.name} / {key_column1}: {', '.join(errors1)}")
        if errors2:
            print(f" - {file2_path.name} / {key_column2}: {', '.join(errors2)}")
        if not inquirer.confirm("Continue despite data issues?", default=False):
            return None

    # normalize match columns
    df1[key_column1] = df1[key_column1].astype(str).str.strip()
    df2[key_column2] = df2[key_column2].astype(str).str.strip()

    if method == "First N characters":
        df1[key_column1] = df1[key_column1].str[:num_chars]
        df2[key_column2] = df2[key_column2].str[:num_chars]
    elif method == "Last N characters":
        df1[key_column1] = df1[key_column1].str[-num_chars:]
        df2[key_column2] = df2[key_column2].str[-num_chars:]

    matched   = df1[df1[key_column1].isin(df2[key_column2])]
    unmatched = df1[~df1[key_column1].isin(df2[key_column2])]

    print("\nReconciliation Summary:")
    print(f"Records in {file1_path.name}: {len(df1)}")
    print(f"Matched:   {len(matched)}")
    print(f"Unmatched: {len(unmatched)}")

    if inquirer.confirm("Export unmatched records?", default=True):
        fmt = select_export_format()
        if not fmt:
            return None
        out_path = file1_path.parent / f"unmatched_{file1_path.stem}.{fmt.lower()}"
        _export_df(unmatched, out_path)

    return matched, unmatched

# ───────────────────────── entrypoint ─────────────────────────

def main():
    data_dir = _ask_directory()
    print("[Reconciliation App]")

    file1_path = select_file_from_folder(data_dir, "Select main file:")
    if not file1_path:
        return
    file2_path = select_file_from_folder(data_dir, "Select reference file:")
    if not file2_path:
        return

    cols1 = get_columns(file1_path)
    cols2 = get_columns(file2_path)
    if not cols1 or not cols2:
        return

    col1 = select_column(cols1, f"Column to match in {file1_path.name}")
    col2 = select_column(cols2, f"Column to match in {file2_path.name}")
    if not col1 or not col2:
        return

    method, num_chars = select_reconcile_method()
    if method is None:
        return

    reconcile_files(file1_path, file2_path, col1, col2, method, num_chars)

if __name__ == "__main__":
    main()
