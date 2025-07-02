import os
import pandas as pd
from rich.console import Console
from rich.table import Table

console = Console()

# Folder containing the raw CSVs
DATA_DIR = "./audit_2024/source"

# ────────────────────────── helpers ──────────────────────────

def list_csv_files():
    """Return list of *.csv files in DATA_DIR."""
    return [f for f in os.listdir(DATA_DIR) if f.lower().endswith(".csv")]


def split_debit_credit(df: pd.DataFrame,
                       amount_col: str = "Amount",
                       flag_col: str = "Debit or Credit") -> pd.DataFrame:
    """Add debit / credit columns while preserving every original column."""
    df = df.copy()

    # normalise the flag column to upper‑case for safe comparison
    df[flag_col] = df[flag_col].astype(str).str.upper().str.strip()

    # create new columns
    df["debit"] = df.apply(lambda r: r[amount_col] if r[flag_col] == "DEBIT" else pd.NA, axis=1)
    df["credit"] = df.apply(lambda r: r[amount_col] if r[flag_col] == "CREDIT" else pd.NA, axis=1)

    # ensure all missing values are explicitly set to <NA>
    df["debit"] = df["debit"].astype("object").where(pd.notna(df["debit"]), pd.NA)
    df["credit"] = df["credit"].astype("object").where(pd.notna(df["credit"]), pd.NA)

    # move new columns to the front for readability
    cols = [c for c in ["debit", "credit"] if c in df.columns] + [c for c in df.columns if c not in ("debit", "credit")]
    return df[cols]


def show_preview(df: pd.DataFrame, n: int = 10):
    table = Table(show_header=True, header_style="bold magenta")
    for c in df.columns:
        table.add_column(c)
    for _, row in df.head(n).iterrows():
        table.add_row(*[str(val) if pd.notna(val) else "" for val in row])
    console.print(table)


# ────────────────────────── batch processor ──────────────────────────

def process_all_files():
    csv_files = list_csv_files()
    if not csv_files:
        console.print(f"[bold red]No CSV files found in {DATA_DIR}[/bold red]")
        return

    for file_name in csv_files:
        console.print(f"\n[cyan]Processing[/cyan] {file_name} …")
        path = os.path.join(DATA_DIR, file_name)
        try:
            df = pd.read_csv(path, on_bad_lines="skip", low_memory=False)
        except Exception as e:
            console.print(f"[bold red]Failed to read {file_name}: {e} — skipping.[/bold red]")
            continue

        # Required columns check
        missing = [col for col in ("Amount", "Debit or Credit") if col not in df.columns]
        if missing:
            console.print(f"[bold red]Missing column(s) {', '.join(missing)} in {file_name} — skipping.[/bold red]")
            continue

        out_df = split_debit_credit(df)

        # Show a quick preview
        show_preview(out_df)

        # Export automatically with suffix "_Processed"
        stem, ext = os.path.splitext(file_name)
        out_name = f"{stem}_Processed{ext}"
        out_path = os.path.join(DATA_DIR, out_name)
        out_df.to_csv(out_path, index=False, na_rep="<NA>")
        console.print(f"[green]✓ Saved processed file to {out_name}[/green]")


# ────────────────────────── entry‑point ──────────────────────────
if __name__ == "__main__":
    console.print("[bold cyan]Debit/Credit Splitter — Batch Mode[/bold cyan]")
    process_all_files()
