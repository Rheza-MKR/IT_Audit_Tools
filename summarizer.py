import pandas as pd
from rich.console import Console
from rich.table import Table
from pathlib import Path
import questionary
import os

console = Console()

def read_csv_safely(path):
    """Robust CSV reader with fallback handling."""
    try:
        df = pd.read_csv(path, encoding="utf-8", on_bad_lines="skip")
        if len(df.columns) == 1:
            df = pd.read_csv(path, encoding="utf-8", sep=";", on_bad_lines="skip")
        return df
    except Exception as e:
        console.print(f"[bold red]Error reading file: {e}[/bold red]")
        return None

def summarize_csv(df):
    """Generate a descriptive summary of the dataset."""
    console.print("\n[bold blue]📊 CSV Summary Report[/bold blue]")

    # Row and column info
    console.print(f"[bold]Total Rows:[/bold] {df.shape[0]}")
    console.print(f"[bold]Total Columns:[/bold] {df.shape[1]}")

    # Missing values
    missing_info = df.isna().sum()
    console.print("\n[bold yellow]🛠 Missing Values:[/bold yellow]")
    for col, missing in missing_info.items():
        status = f"[red]{missing} missing[/red]" if missing > 0 else "[green]OK[/green]"
        console.print(f" - {col}: {status}")

    # Primary key selection
    pk_column = questionary.select(
        "Select the primary key column:", choices=list(df.columns) + ["None"]
    ).ask()
    if pk_column == "None":
        pk_column = None

    if pk_column:
        missing_pk = df[pk_column].isna().sum()
        if missing_pk > 0:
            console.print(f"[bold red]❌ Missing values in primary key '{pk_column}': {missing_pk}[/bold red]")
        else:
            console.print(f"[bold green]✅ No missing values in primary key '{pk_column}'[/bold green]")

        pk_dupes = df.duplicated(subset=[pk_column]).sum()
        if pk_dupes > 0:
            console.print(f"[bold red]❌ Duplicate primary keys found: {pk_dupes}[/bold red]")
        else:
            console.print("[bold green]✅ No duplicate primary keys[/bold green]")

    # Quick stats for numeric columns
    numeric_cols = df.select_dtypes(include="number").columns
    if len(numeric_cols) > 0:
        console.print("\n[bold cyan]📈 Numeric Column Statistics[/bold cyan]")
        stats_table = Table(show_header=True, header_style="bold magenta")
        stats_table.add_column("Column")
        stats_table.add_column("Mean")
        stats_table.add_column("Median")
        stats_table.add_column("Min")
        stats_table.add_column("Max")
        stats_table.add_column("Sum")
        for col in numeric_cols:
            stats_table.add_row(
                col,
                f"{df[col].mean():.2f}",
                f"{df[col].median():.2f}",
                f"{df[col].min():.2f}",
                f"{df[col].max():.2f}",
                f"{df[col].sum():.2f}"
            )
        console.print(stats_table)

    # Frequency counts for categorical columns
    cat_cols = df.select_dtypes(exclude="number").columns
    if len(cat_cols) > 0:
        console.print("\n[bold cyan]📋 Top Values for Categorical Columns[/bold cyan]")
        for col in cat_cols:
            console.print(f"[bold]{col}[/bold]:")
            freq = df[col].value_counts(dropna=False).head(5)
            for val, count in freq.items():
                console.print(f"   - {val}: {count} ({count / len(df) * 100:.1f}%)")

    # Date range for datetime columns
    date_cols = df.select_dtypes(include="datetime").columns
    if len(date_cols) > 0:
        console.print("\n[bold cyan]📅 Date Ranges[/bold cyan]")
        for col in date_cols:
            console.print(f"{col}: {df[col].min()} → {df[col].max()}")

    console.print("\n[bold blue]✅ Summary complete.[/bold blue]")

def _ask_directory() -> Path:
    """Loop until the user enters an existing directory path."""
    while True:
        dir_path = Path(questionary.text("Enter the audit directory path:").ask()).expanduser()
        if dir_path.is_dir():
            return dir_path
        console.print(f"[bold red]Directory '{dir_path}' does not exist – try again.[/bold red]")

def select_csv_from_data_folder(directory):
    """Choose a CSV file interactively from the directory."""
    files = [f for f in os.listdir(directory) if f.endswith(".csv")]
    if not files:
        console.print("[bold red]No CSV files found in that folder.[/bold red]")
        return None
    file_choice = questionary.select("Select a CSV file to summarize:", choices=files + ["Back"]).ask()
    return None if file_choice == "Back" else os.path.join(directory, file_choice)

def export_missing_rows(df, directory):
    """Export rows with missing values in selected columns."""
    console.print("\n[bold cyan]Export Rows with Missing Data[/bold cyan]")

    cols_input = questionary.text(
        "Enter column name(s) to check (comma-separated), or type 'cancel' to exit:"
    ).ask()
    if cols_input.strip().lower() == "cancel":
        return

    selected_cols = [col.strip() for col in cols_input.split(",")]
    invalid = [col for col in selected_cols if col not in df.columns]
    if invalid:
        console.print(f"[bold red]Invalid column(s): {', '.join(invalid)}[/bold red]")
        return

    missing_df = df[df[selected_cols].isnull().any(axis=1)]
    if missing_df.empty:
        console.print("[bold green]No missing values found in the selected column(s).[/bold green]")
        return

    file_format = questionary.select("Choose the export format:", choices=["CSV", "XLSX"]).ask()
    file_name = questionary.text("Enter the file name (without extension):").ask()
    export_path = Path(directory) / f"{file_name}.{file_format.lower()}"

    try:
        if file_format == "CSV":
            missing_df.to_csv(export_path, index=False)
        else:
            missing_df.to_excel(export_path, index=False)
        console.print(f"[bold green]Exported {len(missing_df)} rows to {export_path}[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Export failed: {e}[/bold red]")

def main():
    console.print("[bold cyan]CSV Summarizer Tool[/bold cyan]")
    dir_answer = _ask_directory()
    file_path = select_csv_from_data_folder(dir_answer)

    if file_path:
        df = read_csv_safely(file_path)
        if df is not None:
            summarize_csv(df)
            if questionary.confirm("Do you want to export rows with missing data?").ask():
                export_missing_rows(df, dir_answer)

if __name__ == "__main__":
    main()
