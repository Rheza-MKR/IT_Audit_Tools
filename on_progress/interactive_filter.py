import pandas as pd
import os
import questionary
from rich.console import Console
from rich.table import Table
from difflib import get_close_matches


console = Console()

OPERATORS = {
    '%=': 'contains',
    '==': 'equals',
    '>=': 'greater_equal',
    '<=': 'less_equal',
    '>': 'greater',
    '<': 'less'
}

def list_csv_files():
    """List all CSV files in the current directory."""
    files = [f for f in os.listdir('./data/') if f.endswith('.csv')]
    return files

def select_csv_file():
    """Allow user to select a CSV file using arrow keys."""
    csv_files = list_csv_files()

    if not csv_files:
        console.print("[bold red]No CSV files found in the directory![/bold red]")
        return None

    file_choice = questionary.select(
        "Select a CSV file:", choices=csv_files + ["Back"]
    ).ask()

    return None if file_choice == "Back" else file_choice

def read_csv_safely(file):
    """Read CSV file with automatic delimiter detection and encoding handling."""
    try:
        df = pd.read_csv('./data/'+file, encoding="utf-8", delimiter=None, on_bad_lines="skip")
        
        # Check if columns are incorrectly parsed as a single string
        if len(df.columns) == 1:
            console.print("[yellow]Warning: Only one column detected. Trying semicolon delimiter...[/yellow]")
            df = pd.read_csv(file, encoding="utf-8", sep=";", on_bad_lines="skip")

        return df
    except pd.errors.ParserError:
        console.print("[bold red]Error: Malformed CSV file. Trying semicolon delimiter...[/bold red]")
        try:
            df = pd.read_csv(file, sep=";", encoding="utf-8", on_bad_lines="skip")
            return df
        except Exception as e:
            console.print(f"[bold red]Failed to read CSV: {e}[/bold red]")
            return None
    except UnicodeDecodeError:
        console.print("[bold red]Encoding error. Trying 'latin-1' instead of UTF-8...[/bold red]")
        try:
            df = pd.read_csv(file, encoding="latin-1", on_bad_lines="skip")
            return df
        except Exception as e:
            console.print(f"[bold red]Failed to read CSV with latin-1 encoding: {e}[/bold red]")
            return None


def display_results(results, match_count):
    """Display search results in a table format and show match count."""
    if match_count == 0:
        console.print("[bold red]No matching records found![/bold red]")
        return

    console.print(f"[bold green]Found {match_count} matching record(s)[/bold green]")

    table = Table(show_header=True, header_style="bold magenta")
    for col in results.columns:
        table.add_column(col, style="cyan")

    for _, row in results.iterrows():
        table.add_row(*[str(row[col]) for col in results.columns])

    console.print(table)

def export_results(results):
    """Export search results to CSV or XLSX."""
    if results.empty:
        console.print("[bold red]No results to export![/bold red]")
        return

    file_format = questionary.select(
        "Choose the export format:", choices=["CSV", "XLSX"]
    ).ask()

    file_name = questionary.text("Enter the file name (without extension):").ask()

    if file_format == "CSV":
        results.to_csv('./data/'+file_name + ".csv", index=False)
        console.print(f"[bold green]Results exported to {file_name}.csv[/bold green]")
    elif file_format == "XLSX":
        results.to_excel('./data/'+file_name + ".xlsx", index=False)
        console.print(f"[bold green]Results exported to {file_name}.xlsx[/bold green]")

def find_similar_column(user_input, valid_columns):
    """Suggest the closest matching column name."""
    matches = get_close_matches(user_input, valid_columns, n=1, cutoff=0.6)
    return matches[0] if matches else None


def filter_list(df):
    """Build filter list from user input and validate columns and operators."""
    console.print("\n[bold yellow]Available columns:[/bold yellow]")
    for col in df.columns:
        console.print(f"- {col}")

    while True:
        user_input = questionary.text("Enter your filters (example: colA %= abc, colB == user, colC >= 100000):").ask()
        if not user_input:
            console.print("[bold red]No input provided. Please enter at least one filter.[/bold red]")
            continue

        filters = {}
        components = [x.strip() for x in user_input.split(',') if x.strip()]
        invalid = False

        for comp in components:
            found = False
            for op in OPERATORS.keys():
                if op in comp:
                    col, val = comp.split(op, 1)
                    col = col.strip()
                    val = val.strip()

                    if col not in df.columns:
                        suggestion = find_similar_column(col, df.columns)
                        if suggestion:
                            if questionary.confirm(f"Did you mean '{suggestion}' instead of '{col}'?").ask():
                                col = suggestion
                            else:
                                console.print(f"[bold red]Unknown column: {col}[/bold red]")
                                invalid = True
                                break
                        else:
                            console.print(f"[bold red]Unknown column: {col}[/bold red]")
                            invalid = True
                            break

                    # Validate data type
                    if pd.api.types.is_numeric_dtype(df[col]):
                        if op == '%=':
                            console.print(f"[bold red]Invalid operator '%=' for numeric column: {col}[/bold red]")
                            invalid = True
                            break
                        try:
                            val = float(val)
                        except ValueError:
                            console.print(f"[bold red]Value for numeric column '{col}' must be a number.[/bold red]")
                            invalid = True
                            break
                    elif pd.api.types.is_string_dtype(df[col]):
                        if op in ['>=', '<=', '>', '<']:
                            console.print(f"[bold red]Operator '{op}' not valid for string column: {col}[/bold red]")
                            invalid = True
                            break

                    filters[col] = (op, val)
                    found = True
                    break

            if not found:
                console.print(f"[bold red]Unsupported or missing operator in: {comp}[/bold red]")
                invalid = True
                break

        if not invalid:
            return filters

        console.print("[bold red]Please re-enter your filters correctly.[/bold red]")

def filter_csv(df, filters):
    """Apply multiple filters to the dataframe with AND condition."""
    mask = pd.Series([True] * len(df))

    for col, (op, val) in filters.items():
        if op == '%=':
            mask &= df[col].astype(str).str.contains(val, na=False)
        elif op == '==':
            mask &= df[col] == val
        elif op == '>=':
            mask &= pd.to_numeric(df[col], errors='coerce') >= val
        elif op == '<=':
            mask &= pd.to_numeric(df[col], errors='coerce') <= val
        elif op == '>':
            mask &= pd.to_numeric(df[col], errors='coerce') > val
        elif op == '<':
            mask &= pd.to_numeric(df[col], errors='coerce') < val

    result = df[mask]
    return result, result.shape[0]

def main():
    """Main function for CSV search tool."""
    console.print("[bold cyan]CSV Search Tool[/bold cyan]")
    csv_file = select_csv_file()

    if csv_file:
        df = read_csv_safely(csv_file)
        if df is not None:
            filters = filter_list(df) # data type is dictionary with cols and command
            results = filter_csv(filters)
            display_results(results)
            export_option = questionary.confirm("Do you want to export the results?").ask()
            if export_option:
                export_results(results)

if __name__ == "__main__":
    main()
