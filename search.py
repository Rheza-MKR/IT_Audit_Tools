import pandas as pd
import os
import questionary
from rich.console import Console
from rich.table import Table

console = Console()

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

def select_column(df):
    """Allow user to select a column using arrow keys."""
    columns = list(df.columns)  # Ensure it's a list

    # Check if columns are incorrectly parsed (single string instead of list)
    if len(columns) == 1 and "," in columns[0]:
        console.print("[bold red]Error: CSV file may have incorrect delimiters.[/bold red]")
        return "back"

    column_choices = columns + ["Back"]

    column_choice = questionary.select(
        "Select a column to search in:", choices=column_choices
    ).ask()

    return "back" if column_choice == "Back" else column_choice

def search_csv(df, column, keyword):
    """Search for rows that contain the keyword in the specified column."""
    matched_rows = df[df[column].astype(str).str.contains(keyword, case=False, na=False)]
    match_count = matched_rows.shape[0]  # Get the number of matching rows
    return matched_rows, match_count

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

def main():
    """Main function for CSV search tool."""
    console.print("[bold cyan]CSV Search Tool[/bold cyan]")
    csv_file = select_csv_file()

    if csv_file:
        df = read_csv_safely(csv_file)
        if df is not None:
            column = select_column(df)
            if column != "back":
                keyword = questionary.text("Enter the keyword to search for:").ask()
                results, match_count = search_csv(df, column, keyword)
                display_results(results, match_count)
                export_option = questionary.confirm("Do you want to export the results?").ask()
                if export_option:
                    export_results(results)

if __name__ == "__main__":
    main()
