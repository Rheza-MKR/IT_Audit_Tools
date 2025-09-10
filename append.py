import os
from pathlib import Path
import pandas as pd
import questionary
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
    choices = questionary.checkbox("✅ Select files to append (in order):", choices=files).ask()
    return choices if choices and len(choices) >= 2 else None

# ───────────────────────────── Schema alignment ─────────────────────────────

def _ordered_union_by_selection(loaded: dict[str, pd.DataFrame], ordered_names: list[str]) -> list[str]:
    """
    Build a union of columns preserving first-seen order across the selected files:
    - first file's columns first, then any new columns as they appear in later files.
    """
    seen: set[str] = set()
    result: list[str] = []
    for name in ordered_names:
        for c in loaded[name].columns:
            if c not in seen:
                seen.add(c)
                result.append(c)
    return result

def inspect_columns(loaded: dict[str, pd.DataFrame], ordered_names: list[str]) -> tuple[list[str], set[str], dict[str, set[str]]]:
    """
    Returns:
      - union_ordered: union of columns in first-seen order across selected files
      - common_set: columns present in ALL selected files
      - per_file: mapping filename -> set of columns
    """
    per_file = {name: set(df.columns) for name, df in loaded.items()}
    # intersection over selected files in the given order
    common_set = set(loaded[ordered_names[0]].columns)
    for name in ordered_names[1:]:
        common_set &= set(loaded[name].columns)
    union_ordered = _ordered_union_by_selection(loaded, ordered_names)
    return union_ordered, common_set, per_file

def choose_alignment_mode(union_ordered: list[str], common_set: set[str], first_cols: list[str]) -> tuple[str, list[str]]:
    """
    Ask how to align columns:
      - union       → first-seen union order
      - intersection→ first file's order filtered to common
      - first       → exactly first file's order
      - manual      → pick from union (shown in first-seen order)
    Returns (mode, selected_columns)
    """
    console.print("\n[bold cyan]Column alignment options:[/bold cyan]")
    console.print(f"- Force append (union): {len(union_ordered)} columns (preserve first-seen order)")
    console.print(f"- Only common columns (intersection): {len(common_set)} columns (first file's order)")
    console.print(f"- Match first file’s columns: {len(first_cols)} columns")

    mode = questionary.select(
        "How do you want to align the columns across files?",
        choices=[
            "Force append (use union of all columns)",
            "Only common columns (intersection)",
            "Match first file’s columns",
            "Choose columns manually from union",
        ],
    ).ask()

    if mode == "Force append (use union of all columns)":
        return "union", list(union_ordered)

    if mode == "Only common columns (intersection)":
        # keep first file's order, filter to those present in all
        return "intersection", [c for c in first_cols if c in common_set]

    if mode == "Match first file’s columns":
        return "first", list(first_cols)

    # manual selection: present union in first-seen order (no sorting)
    pick = questionary.checkbox(
        "Select the columns to use (from union in first-seen order):",
        choices=union_ordered
    ).ask()
    return "manual", pick

def align_dataframes(dfs: dict[str, pd.DataFrame], selected_cols: list[str]) -> dict[str, pd.DataFrame]:
    """
    Reindex/expand each df to selected_cols (order preserved by selected_cols).
    Missing columns are added with NaN; extra columns are dropped.
    """
    aligned = {}
    for name, df in dfs.items():
        # add missing columns
        for c in selected_cols:
            if c not in df.columns:
                df[c] = pd.NA
        aligned[name] = df[selected_cols].copy()  # order is exactly as selected_cols
    return aligned

# ───────────────────────────── Append modes ─────────────────────────────

def select_append_mode() -> str:
    """
    Choose between:
      - Check duplicates (unique by keys)
      - Just append (no dedup)
    """
    return questionary.select(
        "Append mode:",
        choices=[
            "Check duplicates (unique by selected key columns)",
            "Just append (no deduplication)"
        ],
        default="Check duplicates (unique by selected key columns)"
    ).ask()

# ───────────────────────────── Export helper ─────────────────────────────

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

# ───────────────────────────── Core logic ─────────────────────────────

def append_with_schema_resolution(folder: Path, files: list[str]):
    # Read all files first (preserve user-selected order)
    loaded: dict[str, pd.DataFrame] = {}
    for f in files:
        df = read_file_safely(folder / f)
        if df is None:
            console.print(f"[bold red]Skipping unreadable file: {f}[/bold red]")
            continue
        loaded[f] = df

    ordered_names = [f for f in files if f in loaded]  # keep user’s selection order

    if len(ordered_names) < 2:
        console.print("[bold red]Need at least two readable files to append.[/bold red]")
        return

    # Tiny peek for context
    console.print("\n[bold blue]Preview (first 5 rows) of first file:[/bold blue]")
    console.print(loaded[ordered_names[0]].head())

    # Decide schema (NO sorting; preserve order)
    union_ordered, common_set, _per_file_cols = inspect_columns(loaded, ordered_names)
    mode, selected_cols = choose_alignment_mode(
        union_ordered=union_ordered,
        common_set=common_set,
        first_cols=list(loaded[ordered_names[0]].columns)
    )

    if not selected_cols:
        console.print("[bold red]No columns selected; aborting.[/bold red]")
        return

    # Align all dataframes to the chosen schema (order preserved)
    aligned = align_dataframes(loaded, selected_cols)

    # Choose append behavior
    append_mode = select_append_mode()

    if append_mode.startswith("Just append"):
        # Simple concat, no dedup, preserve file order and selected column order
        combined = pd.concat([aligned[name] for name in ordered_names], ignore_index=True)
        console.print(f"[bold green]✅ Appended {len(ordered_names)} files (no dedup). Final row count: {len(combined)}[/bold green]")
        export_table(combined, folder, default_name="appended_raw")
        return

    # Check duplicates mode: ask for unique keys and de-duplicate
    while True:
        unique_columns = questionary.checkbox(
            "🔑 Select column(s) to define uniqueness:",
            choices=selected_cols  # these are already in the final order
        ).ask()
        if not unique_columns:
            console.print("[red]❌ You must select at least one unique column.[/red]")
            continue
        break

    # Start with the first file as base
    base = aligned[ordered_names[0]].drop_duplicates(subset=unique_columns)

    # Append loop in the chosen order
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

    console.print(f"[bold green]✅ Appending done with duplicate check. Final row count: {len(base)}[/bold green]")
    export_table(base, folder, default_name="appended_unique")

# ───────────────────────────── Entrypoint ─────────────────────────────

def main():
    console.print("[bold cyan]Append Tables[/bold cyan]")

    folder = ask_directory()
    files = select_multiple_data_files(folder)
    if not files:
        console.print("[red]Please select at least two files.[/red]")
        return

    append_with_schema_resolution(folder, files)

if __name__ == "__main__":
    main()
