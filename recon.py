import pandas as pd
import os
import inquirer
from pathlib import Path
from rich.console import Console
import questionary

console = Console()

def _ask_directory() -> Path:
    while True:
        dir_path = Path(questionary.text("Enter the audit directory path:").ask()).expanduser().resolve()
        if dir_path.is_dir():
            return dir_path
        console.print(f"[bold red]Directory '{dir_path}' does not exist – try again.[/bold red]")

def select_csv_from_folder(directory, prompt="Select a CSV file to analyze:"):
    """List CSV files in the given directory and prompt user to select one."""
    files = [f for f in os.listdir(directory) if f.endswith('.csv')]
    if not files:
        print("No CSV files found in the selected directory.")
        return None
    question = [inquirer.List('file', message=prompt, choices=files)]
    answer = inquirer.prompt(question)
    return Path(directory) / answer['file'] if answer else None

def get_columns(csv_file):
    """Get column names from a CSV file."""
    try:
        df = pd.read_csv(csv_file, encoding='utf-8', delimiter=',', on_bad_lines='skip', nrows=1)
        return df.columns.tolist()
    except Exception as e:
        print(f"Error reading {csv_file}: {e}")
        return []

def select_column(columns, prompt):
    """Prompt user to select a column."""
    question = [inquirer.List('column', message=prompt, choices=columns)]
    answer = inquirer.prompt(question)
    return answer['column'] if answer else None

def check_data_format(df, column):
    """Check for missing values, special characters, or negative values in a column."""
    errors = []
    df[column] = df[column].astype(str).str.strip()

    if df[column].isnull().any():
        errors.append("Missing values detected.")

    special_char_mask = df[column].str.contains(r'[^\w\s]', regex=True, na=False)
    if special_char_mask.any():
        errors.append("Special characters detected.")

    if df[column].str.replace('.', '', 1).str.isnumeric().all():
        if (df[column].astype(float) < 0).any():
            errors.append("Negative values detected.")

    return errors

def select_reconcile_method():
    """Prompt user to select a reconciliation method."""
    question = [inquirer.List('reconcile_method', message="Select reconciliation method:", choices=[
        "Standard (full match)", "First N characters", "Last N characters"
    ])]
    answer = inquirer.prompt(question)
    method = answer['reconcile_method'] if answer else None

    num_chars = None
    if method in ["First N characters", "Last N characters"]:
        num_chars_input = inquirer.text("Enter number of characters:")
        try:
            num_chars = int(num_chars_input)
        except:
            print("Invalid number.")
            return None, None

    return method, num_chars

def select_export_format():
    """Prompt user to select an export file format (CSV or XLSX)."""
    question = [inquirer.List('export_format', message="Select an export format:", choices=["CSV", "XLSX"])]
    answer = inquirer.prompt(question)
    return answer['export_format'] if answer else None

def reconcile_files(file1_path, file2_path, key_column1, key_column2, method, num_chars):
    try:
        df1 = pd.read_csv(file1_path, encoding='utf-8', on_bad_lines='skip')
        df2 = pd.read_csv(file2_path, encoding='utf-8', on_bad_lines='skip')
    except Exception as e:
        print(f"Error reading files: {e}")
        return None

    errors1 = check_data_format(df1, key_column1)
    errors2 = check_data_format(df2, key_column2)

    if errors1 or errors2:
        print("\nData Format Issues:")
        if errors1:
            print(f"Issues in {file1_path.name} - {key_column1}: {', '.join(errors1)}")
        if errors2:
            print(f"Issues in {file2_path.name} - {key_column2}: {', '.join(errors2)}")

        if not inquirer.confirm("Continue despite data issues?", default=False):
            return None

    df1[key_column1] = df1[key_column1].astype(str).str.strip()
    df2[key_column2] = df2[key_column2].astype(str).str.strip()

    if method == "First N characters":
        df1[key_column1] = df1[key_column1].str[:num_chars]
        df2[key_column2] = df2[key_column2].str[:num_chars]
    elif method == "Last N characters":
        df1[key_column1] = df1[key_column1].str[-num_chars:]
        df2[key_column2] = df2[key_column2].str[-num_chars:]

    matched = df1[df1[key_column1].isin(df2[key_column2])]
    unmatched = df1[~df1[key_column1].isin(df2[key_column2])]

    print(f"\nReconciliation Summary:")
    print(f"Records in {file1_path.name}: {len(df1)}")
    print(f"Matched: {len(matched)}")
    print(f"Unmatched: {len(unmatched)}")

    if inquirer.confirm("Export unmatched records?", default=True):
        fmt = select_export_format()
        output_file = Path(file1_path.parent) / f"unmatched_{file1_path.stem}.{fmt.lower()}"
        try:
            if fmt == "CSV":
                unmatched.to_csv(output_file, index=False)
            else:
                unmatched.to_excel(output_file, index=False)
            print(f"Saved: {output_file}")
        except Exception as e:
            print(f"Error saving: {e}")

def main():
    data_dir = _ask_directory()
    print("[Reconciliation App]")

    file1_path = select_csv_from_folder(data_dir, "Select main file:")
    if not file1_path:
        return
    file2_path = select_csv_from_folder(data_dir, "Select reference file:")
    if not file2_path:
        return

    col1 = select_column(get_columns(file1_path), f"Column to match in {file1_path.name}")
    col2 = select_column(get_columns(file2_path), f"Column to match in {file2_path.name}")
    method, num_chars = select_reconcile_method()
    if method is None:
        return

    reconcile_files(file1_path, file2_path, col1, col2, method, num_chars)

if __name__ == "__main__":
    main()
