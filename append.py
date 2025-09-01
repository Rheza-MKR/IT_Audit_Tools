import os
from pathlib import Path
import pandas as pd
import questionary
from questionary import Choice
from rich.console import Console
from utils.import_utils import read_file_safely

console = Console()

# ───────────────────────────── File helpers ─────────────────────────────

def ask_directory() -> Path:
    while True:
        p = Path(questionary.path("📂  Enter folder containing CSV/Excel files:").ask()).expanduser().resolve()
        if p.is_dir():
            return p
        console.print(f"[bold red]Directory '{p}' not found – try again.[/bold red]")


def list_data_files(folder: Path):
    """List all CSV and Excel files in a folder."""
    return [f.name for f in folder.glob("*") if f.suffix.lower() in (".csv", ".xlsx", ".xls")]


def select_multiple_data_files(folder: Path):
    files = list_data_files(folder)
    if not files:
        console.print("[bold red]No Excel/CSV files in that folder.[/bold red]")
        return None
    choices = questionary.checkbox("✅ Select files to append:", choices=files).ask()
    return choices if choices and len(choices) >= 2 else None



# ───────────────────────────── Schema alignment ─────────────────────────────

def inspect_columns(dfs: dict[str, pd.DataFrame]) -> tuple[set, set, dict[str, set]]:
    """Return union, intersection, and per-file columns."""
    per_file = {name: set(df.columns) for name, df in dfs.items()}
    all_cols = set().union(*per_file.values())
    common_cols = set.intersection(*per_file.values()) if per_file else set()
    return all_cols, common_cols, per_file


def choose_alignment_mode(all_cols: set, common_cols: set, first_cols: list[str]) -> tuple[str, list[str]]:
    """
    Ask how to align columns:
      - union
      - intersection
      - first
      - manual (pick from union)
    Returns (mode, selected_columns)
    """
    console.print("\n[bold cyan]Column alignment options:[/bold cyan]")
    console.print(f"- Union (force append): {len(all_cols)} columns")
    console.print(f"- Intersection (common to all): {len(common_cols)} columns")
    console.print(f"- Match first file’s columns: {len(first_cols)} columns")

    mode = questionary.select(
        "How do you want to align the columns across files?",
        choices=[
            Choice("Force append (use union of all columns)", value="union"),
            Choice("Only common columns (intersection)", value="intersection"),
            Choice("Match first file’s columns", value="first"),
            Choice("Choose columns manually from union", value="manual"),
        ],
    ).ask()

    if mode == "union":
        return mode, sorted(all_cols)
    if mode == "intersection":
        return mode, sorted(common_cols)
    if mode == "first":
        return mode, list(first_cols)

    # manual
    pick = questionary.checkbox(
        "Select the columns to use (from union):",
        choices=sorted(all_cols)
    ).ask()
    return "manual", pick


def align_dataframes(dfs: dict[str, pd.DataFrame], selected_cols: list[str]) -> dict[str, pd.DataFrame]:
    """
    Reindex/expand each df to selected_cols.
    Missing columns are added with NaN; extra columns are dropped.
    """
    aligned = {}
    for name, df in dfs.items():
        # Add missing columns as NaN
        for c in selected_cols:
            if c not in df.columns:
                df[c] = pd.NA
        aligned[name] = df[selected_cols].copy()
    return aligned


# ───────────────────────────── Append logic ─────────────────────────────

def export_table(df: pd.DataFrame, folder: Path, default_name: str):
    if df is None or df.empty:
        console.print("[bold yellow]No data to export.[/bold yellow]")
        return
    if not questionary.confirm("Do you want to export this table?", default=True).ask():
        return
    fmt = questionary.select("Choose format:", choices=["CSV", "XLSX"]).ask()
    name = questionary.text("File name (without extension):", default=default_name).ask()
    out_path = folder / f"{name}.{fmt.lower()}"
    try:
        if fmt == "CSV":
            df.to_csv(out_path, index=False)
        else:
            df.to_excel(out_path, index=False)
        console.print(f"[bold green]✅ Saved → {out_path}[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Failed to save: {e}[/bold red]")


def append_with_schema_resolution(folder: Path, files: list[str]):
    # Read all files first
    loaded: dict[str, pd.DataFrame] = {}
    for f in files:
        df = read_file_safely(folder / f)
        if df is None:
            console.print(f"[bold red]Skipping unreadable file: {f}[/bold red]")
            continue
        loaded[f] = df

    if len(loaded) < 2:
        console.print("[bold red]Need at least two readable files to append.[/bold red]")
        return

    # Show a tiny peek for context
    console.print("\n[bold blue]Preview (first 5 rows) of first file:[/bold blue]")
    console.print(loaded[files[0]].head())

    # Decide schema
    all_cols, common_cols, per_file_cols = inspect_columns(loaded)
    mode, selected_cols = choose_alignment_mode(all_cols, common_cols, list(loaded[files[0]].columns))

    if not selected_cols:
        console.print("[bold red]No columns selected; aborting.[/bold red]")
        return

    # Align all dataframes to the chosen schema
    aligned = align_dataframes(loaded, selected_cols)

    # Ask for unique columns (must be subset of selected_cols)
    while True:
        unique_columns = questionary.checkbox(
            "🔑 Select column(s) to define uniqueness:",
            choices=selected_cols
        ).ask()
        if not unique_columns:
            console.print("[red]❌ You must select at least one unique column.[/red]")
            continue
        # Ok if selected
        break

    # Start with the first file as base
    ordered_names = [f for f in files if f in aligned]  # preserve user selection order
    base = aligned[ordered_names[0]].drop_duplicates(subset=unique_columns)

    # Append loop
    for name in ordered_names[1:]:
        next_df = aligned[name]
        combined = pd.concat([base, next_df], ignore_index=True)

        # Duplicated rows w.r.t unique columns
        dup_mask = combined.duplicated(subset=unique_columns, keep=False)
        duplicated_rows = combined[dup_mask]

        if not duplicated_rows.empty:
            console.print(f"[bold yellow]⚠️  Found {len(duplicated_rows)} duplicated rows when appending {name}[/bold yellow]")
            if questionary.confirm("Do you want to export duplicated rows?", default=False).ask():
                export_table(duplicated_rows, folder, default_name=f"duplicates_from_{Path(name).stem}")

        # Keep unique
        base = combined.drop_duplicates(subset=unique_columns, keep="first")

    console.print(f"[bold green]✅ Appending done. Final row count: {len(base)}[/bold green]")

    export_table(base, folder, default_name="appended")


# ───────────────────────────── Entrypoint ─────────────────────────────

def main():
    console.print("[bold cyan]Append Tables (Schema‑Aware)[/bold cyan]")

    folder = ask_directory()
    files = select_multiple_data_files(folder)
    if not files:
        console.print("[red]Please select at least two files.[/red]")
        return

    append_with_schema_resolution(folder, files)


if __name__ == "__main__":
    main()
