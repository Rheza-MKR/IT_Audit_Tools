import pandas as pd
from rich.console import Console
from rich.table import Table
from pathlib import Path
import questionary
import os

console = Console()

# ───────────────────────── file helpers ─────────────────────────

def read_table_safely(path: Path) -> pd.DataFrame | None:
    """Read CSV or Excel with simple fallbacks."""
    try:
        suf = path.suffix.lower()
        if suf in (".xlsx", ".xls"):
            return pd.read_excel(path)
        # CSV branch
        try:
            df = pd.read_csv(path, encoding="utf-8", on_bad_lines="skip")
            if len(df.columns) == 1:
                df = pd.read_csv(path, encoding="utf-8", sep=";", on_bad_lines="skip")
            return df
        except Exception:
            return pd.read_csv(path, encoding="latin-1", on_bad_lines="skip")
    except Exception as e:
        console.print(f"[bold red]Error reading file: {e}[/bold red]")
        return None

def _ask_directory() -> Path:
    """Loop until the user enters an existing directory path."""
    while True:
        dir_path = Path(questionary.text("Enter the audit directory path:").ask()).expanduser()
        if dir_path.is_dir():
            return dir_path
        console.print(f"[bold red]Directory '{dir_path}' does not exist – try again.[/bold red]")

def select_file_from_folder(directory: Path) -> Path | None:
    """Choose a CSV/XLSX/XLS file interactively from the directory."""
    files = [f for f in os.listdir(directory) if f.lower().endswith((".csv", ".xlsx", ".xls"))]
    if not files:
        console.print("[bold red]No CSV or Excel files found in that folder.[/bold red]")
        return None
    file_choice = questionary.select("Select a file to summarize:", choices=files + ["Back"]).ask()
    return None if file_choice == "Back" else Path(directory) / file_choice

# ───────────────────────── summarizer core ───────────────────────

def _print_basic_overview(df: pd.DataFrame):
    console.print("\n[bold blue]📊 Dataset Summary[/bold blue]")
    console.print(f"[bold]Total Rows:[/bold] {df.shape[0]}")
    console.print(f"[bold]Total Columns:[/bold] {df.shape[1]}")

    # Missing values
    console.print("\n[bold yellow]🛠 Missing Values by Column[/bold yellow]")
    missing_info = df.isna().sum()
    for col, missing in missing_info.items():
        status = f"[red]{missing} missing[/red]" if missing > 0 else "[green]OK[/green]"
        console.print(f" - {col}: {status}")

def _maybe_pick_primary_key_and_report(df: pd.DataFrame):
    pk_column = questionary.select(
        "Select the primary key column (or None):", choices=list(df.columns) + ["None"]
    ).ask()
    if pk_column == "None":
        return
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

def _print_numeric_insights(df: pd.DataFrame):
    num_cols = df.select_dtypes(include="number").columns
    if len(num_cols) == 0:
        return

    console.print("\n[bold cyan]📈 Numeric Column Statistics (overview)[/bold cyan]")
    stats_table = Table(show_header=True, header_style="bold magenta")
    stats_table.add_column("Column")
    stats_table.add_column("Mean")
    stats_table.add_column("Median")
    stats_table.add_column("Min")
    stats_table.add_column("Max")
    stats_table.add_column("Sum")

    for col in num_cols:
        stats_table.add_row(
            col,
            f"{df[col].mean():.2f}",
            f"{df[col].median():.2f}",
            f"{df[col].min():.2f}",
            f"{df[col].max():.2f}",
            f"{df[col].sum():.2f}",
        )
    console.print(stats_table)

    # Ask how to treat zeros for "smallest" slice
    exclude_zeros = questionary.confirm(
        "For 'smallest values' lists, exclude zeros?", default=True
    ).ask()

    # Top max/min per numeric column
    console.print("\n[bold cyan]🔎 Extremes per numeric column[/bold cyan]")
    for col in num_cols:
        s = df[col].dropna()
        if exclude_zeros:
            s_min = s[s != 0]
        else:
            s_min = s

        top_max = s.sort_values(ascending=False).head(10)
        top_min = s_min.sort_values(ascending=True).head(10)

        console.print(f"\n[bold]{col}[/bold]")
        # Max 10
        table_max = Table(title="Top 10 Max", show_header=True, header_style="bold magenta")
        table_max.add_column("Value"); table_max.add_column("Row Index")
        for idx, val in top_max.items():
            table_max.add_row(f"{val}", str(idx))
        console.print(table_max)

        # Min 10
        if not top_min.empty:
            table_min = Table(title=f"Top 10 Min{' (non-zero)' if exclude_zeros else ''}", show_header=True, header_style="bold magenta")
            table_min.add_column("Value"); table_min.add_column("Row Index")
            for idx, val in top_min.items():
                table_min.add_row(f"{val}", str(idx))
            console.print(table_min)
        else:
            console.print("[italic]No non-zero values for min list.[/italic]")

def _coerce_datetimes_for_info(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """
    Try to detect datetime-like columns (lightweight).
    We attempt conversion for object columns; if >70% parseable, treat as datetime.
    Returns (parsed_df, date_cols).
    """
    parsed_df = df.copy()
    date_cols: list[str] = []

    for col in parsed_df.columns:
        if pd.api.types.is_datetime64_any_dtype(parsed_df[col]):
            date_cols.append(col)
            continue

        if pd.api.types.is_object_dtype(parsed_df[col]):
            try:
                # Use mixed format parsing to avoid per-element warnings
                parsed = pd.to_datetime(parsed_df[col], errors="coerce", format="mixed")
            except TypeError:
                # For older pandas versions without format="mixed"
                parsed = pd.to_datetime(parsed_df[col], errors="coerce")

            if parsed.notna().mean() >= 0.70:
                parsed_df[col] = parsed
                date_cols.append(col)

    return parsed_df, date_cols


def _print_date_ranges(df: pd.DataFrame):
    parsed_df, date_cols = _coerce_datetimes_for_info(df)
    if not date_cols:
        return

    console.print("\n[bold cyan]📅 Date Ranges[/bold cyan]")
    for col in date_cols:
        console.print(f"{col}: {parsed_df[col].min()} → {parsed_df[col].max()}")

def _top_frequencies(df: pd.DataFrame) -> dict[str, pd.Series]:
    """Return a dict of value_counts for all columns."""
    freq_map = {}
    for col in df.columns:
        vc = df[col].value_counts(dropna=False)
        freq_map[col] = vc
    return freq_map

def _print_top10_frequencies(freq_map: dict[str, pd.Series], total_rows: int):
    console.print("\n[bold cyan]📋 Top 10 Frequencies per Column[/bold cyan]")
    for col, vc in freq_map.items():
        console.print(f"[bold]{col}[/bold]:")
        top10 = vc.head(10)
        for val, count in top10.items():
            pct = (count / total_rows * 100) if total_rows > 0 else 0.0
            console.print(f"  - {val}: {count} ({pct:.1f}%)")

def _export_frequencies(freq_map: dict[str, pd.Series], src_path: Path, dir_path: Path):
    """Export all/selected column frequencies to CSV files or single Excel workbook with sheets."""
    if not freq_map:
        console.print("[bold yellow]No frequency data to export.[/bold yellow]")
        return

    scope = questionary.select(
        "Export frequencies for…",
        choices=["All columns", "Select columns", "Cancel"]
    ).ask()
    if scope == "Cancel":
        return

    if scope == "Select columns":
        cols = list(freq_map.keys())
        chosen = questionary.checkbox("Pick columns to export:", choices=cols).ask()
        if not chosen:
            console.print("[yellow]No columns chosen — skipping export.[/yellow]")
            return
        freq_map = {c: freq_map[c] for c in chosen}

    fmt = questionary.select("Export format:", choices=["CSV (one file per column)", "Excel (one workbook, multiple sheets)"]).ask()

    out_dir = dir_path / f"{src_path.stem}_stats"
    out_dir.mkdir(parents=True, exist_ok=True)

    if fmt.startswith("CSV"):
        for col, vc in freq_map.items():
            safe_name = f"{col}_stats.csv"
            out_path = out_dir / safe_name
            vc.rename("count").to_frame().to_csv(out_path)
        console.print(f"[bold green]Saved CSV frequency tables in: {out_dir}[/bold green]")
    else:
        out_xlsx = out_dir / f"{src_path.stem}_stats.xlsx"
        try:
            with pd.ExcelWriter(out_xlsx, engine="xlsxwriter") as xw:
                for col, vc in freq_map.items():
                    # Excel sheet names max 31 chars; sanitize
                    sheet = str(col)[:31].replace("/", "_").replace("\\", "_").replace("*", "_").replace("?", "_").replace("]", "_").replace("[", "_").replace(":", "_")
                    vc.rename("count").to_frame().to_excel(xw, sheet_name=sheet)
            console.print(f"[bold green]Saved Excel frequency workbook: {out_xlsx}[/bold green]")
        except Exception as e:
            console.print(f"[bold red]Failed to save Excel: {e}[/bold red]")

# ───────────────────────── entrypoint ─────────────────────────

def summarize_file(path: Path, base_dir: Path):
    df = read_table_safely(path)
    if df is None:
        return

    # 1) Overview + missing + PK checks
    _print_basic_overview(df)
    _maybe_pick_primary_key_and_report(df)

    # 2) Numeric insights (stats + top max/min)
    _print_numeric_insights(df)

    # 3) Date ranges (light inference)
    _print_date_ranges(df)

    # 4) Top 10 frequencies per column
    freq_map = _top_frequencies(df)
    _print_top10_frequencies(freq_map, len(df))

    # 5) Export frequencies?
    if questionary.confirm("Do you want to export the frequency tables?", default=True).ask():
        _export_frequencies(freq_map, path, base_dir)

    console.print("\n[bold blue]✅ Summary complete.[/bold blue]")

def main():
    console.print("[bold cyan]CSV/Excel Summarizer Tool[/bold cyan]")
    dir_answer = _ask_directory()
    file_path = select_file_from_folder(dir_answer)
    if not file_path:
        return
    summarize_file(file_path, dir_answer)

if __name__ == "__main__":
    main()
