import pandas as pd
import os
import inquirer

def select_csv_file(prompt):
    """Prompt user to select a CSV file."""
    files = [f for f in os.listdir('.') if f.endswith('.csv')]
    while not files:
        print("No CSV files found. Please add a CSV file and try again.")
        input("Press Enter to retry...")
        files = [f for f in os.listdir('.') if f.endswith('.csv')]

    questions = [inquirer.List('file', message=prompt, choices=files)]
    answer = inquirer.prompt(questions)
    return answer['file']

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
    questions = [inquirer.List('column', message=prompt, choices=columns)]
    answer = inquirer.prompt(questions)
    return answer['column']

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
    questions = [
        inquirer.List('reconcile_method', message="Select a reconciliation method:", choices=[
            "Reconcile standard (default)",
            "Reconcile from first N characters",
            "Reconcile from last N characters"
        ])
    ]
    answer = inquirer.prompt(questions)

    num_chars = None
    if answer['reconcile_method'] in ["Reconcile from first N characters", "Reconcile from last N characters"]:
        num_chars_input = inquirer.text("Enter the number of characters to use for reconciliation")

        # Check if the input is a valid integer
        try:
            num_chars = int(num_chars_input)
        except ValueError:
            print("Invalid input! Please enter a valid number.")
            return None, None  # Exit early or handle appropriately

    return answer['reconcile_method'], num_chars

def select_export_format():
    """Prompt user to select an export file format (CSV or XLSX)."""
    questions = [
        inquirer.List('export_format', message="Select an export format:", choices=[
            "CSV",
            "XLSX"
        ])
    ]
    answer = inquirer.prompt(questions)
    return answer['export_format']

def reconcile_files(file1, file2, key_column1, key_column2, reconcile_method, num_chars):
    """Perform reconciliation between two CSV files."""
    try:
        df1 = pd.read_csv(file1, encoding='utf-8', delimiter=',', on_bad_lines='skip')
        df2 = pd.read_csv(file2, encoding='utf-8', delimiter=',', on_bad_lines='skip')
    except Exception as e:
        print(f"Error reading files: {e}")
        return

    errors1 = check_data_format(df1, key_column1)
    errors2 = check_data_format(df2, key_column2)

    if errors1 or errors2:
        print("\nData Format Issues:")
        if errors1:
            print(f"Issues in {file1} - {key_column1}: {', '.join(errors1)}")
        if errors2:
            print(f"Issues in {file2} - {key_column2}: {', '.join(errors2)}")

        if not inquirer.confirm("Do you want to continue despite data format issues?", default=False):
            print("Reconciliation aborted.")
            return

    df1[key_column1] = df1[key_column1].astype(str).str.strip()
    df2[key_column2] = df2[key_column2].astype(str).str.strip()

    if reconcile_method == "Reconcile from first N characters":
        df1[key_column1] = df1[key_column1].str[:num_chars]
        df2[key_column2] = df2[key_column2].str[:num_chars]
    elif reconcile_method == "Reconcile from last N characters":
        df1[key_column1] = df1[key_column1].str[-num_chars:]
        df2[key_column2] = df2[key_column2].str[-num_chars:]

    matched = df1[df1[key_column1].isin(df2[key_column2])]
    unmatched_1 = df1[~df1[key_column1].isin(df2[key_column2])]

    print("\nReconciliation Summary:")
    print(f"Total records in {file1}: {len(df1)}")
    print(f"Total Matched: {len(matched)}")
    print(f"Total Unmatched: {len(unmatched_1)}")

    if inquirer.confirm("Do you want to export unmatched records?", default=True):
        # Select the export format
        export_format = select_export_format()
        output_filename = f"unmatch-{os.path.basename(file1)}"

        if export_format == "CSV":
            unmatched_1.to_csv(output_filename, index=False)
            print(f"\nUnmatched records from {file1} saved as {output_filename}.")
        elif export_format == "XLSX":
            output_filename = output_filename.replace(".csv", ".xlsx")
            unmatched_1.to_excel(output_filename, index=False)
            print(f"\nUnmatched records from {file1} saved as {output_filename}.")

        # Ask if the user wants to go back to the main menu instead of undoing the operation
        if inquirer.confirm("Do you want to go back to the Reconcile menu?", default=False):
            main()  # Call the main function to go back to the main menu

def main():
    """Main function for recon.py."""
    print("CSV Reconciliation Tool")

    file1 = select_csv_file("Select the main CSV file (file1):")
    file2 = select_csv_file("Select the second CSV file (file2):")

    key_column1 = select_column(get_columns(file1), "Select the column for reconciliation in file1:")
    key_column2 = select_column(get_columns(file2), "Select the column for reconciliation in file2:")

    reconcile_method, num_chars = select_reconcile_method()
    if reconcile_method is None:
        print("Reconciliation aborted due to invalid number input.")
        return

    reconcile_files(file1, file2, key_column1, key_column2, reconcile_method, num_chars)

if __name__ == "__main__":
    main()
