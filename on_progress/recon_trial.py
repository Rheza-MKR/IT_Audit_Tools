import os
from pathlib import Path
from typing import List, Dict

import pandas as pd
from dateutil.parser import parse           # robust date-time parser
import questionary
from rich.console import Console
import math, numbers, re


console = Console()


# ────────────────────────── helpers ──────────────────────────
def _ask_directory() -> Path:
    """Loop until the user enters an existing directory path."""
    while True:
        dir_path = Path(questionary.text("Enter the audit directory path:").ask()).expanduser()
        if dir_path.is_dir():
            return dir_path
        console.print(f"[bold red]Directory '{dir_path}' does not exist – try again.[/bold red]")


def _pick_one(msg: str, choices: List[str]) -> str:
    """Questionary single-choice helper."""
    return questionary.select(msg, choices=choices).ask()


def _pick_many(msg: str, choices: List[str]) -> List[str]:
    """Questionary multi-choice helper."""
    return questionary.checkbox(msg, choices=choices).ask()


def _month_signature(dt: pd.Timestamp) -> str:
    """Return the pattern that must appear in the month file name, e.g. '01 - JAN'."""
    return dt.strftime("%m - %b").upper()[:6]   # '01 - JAN'


def _load_csv_safely(path: Path) -> pd.DataFrame:
    """Basic CSV reader with UTF-8 fallback only (audit data usually clean)."""
    try:
        return pd.read_csv(path, on_bad_lines="skip", low_memory=False)
    except Exception as e:
        console.print(f"[bold red]Failed to read {path.name}: {e}[/bold red]")
        raise

def _month_signature(dt) -> str:
    """Return the month pattern (e.g. '01 - JAN'); handle NaT safely."""
    if pd.isna(dt):
        return "MISSING"          # or return None / "" if you prefer
    return dt.strftime("%m - %b").upper()[:6]

def split_debit_credit(df: pd.DataFrame,
                       amount_col: str = "Amount",
                       flag_col: str = "Debit or Credit") -> pd.DataFrame:
    """
    Add debit / credit columns while preserving every original column.
    Automatically clean 'platform fee debit' by removing 2500 debit rows and adjusting the next credit.
    """
    df = df.copy()

    # Normalise the flag column to upper-case for safe comparison
    df[flag_col] = df[flag_col].astype(str).str.upper().str.strip()

    # Create new columns
    df["debit"] = df.apply(lambda r: r[amount_col] if r[flag_col] == "DEBIT" else pd.NA, axis=1)
    df["credit"] = df.apply(lambda r: r[amount_col] if r[flag_col] == "CREDIT" else pd.NA, axis=1)

    # Ensure all missing values are explicitly set to <NA>
    df["debit"] = (
        df["debit"]
        .astype("object")
        .where(pd.notna(df["debit"]), pd.NA)
        .replace({float('nan'): pd.NA})
    )

    df["credit"] = (
        df["credit"]
        .astype("object")
        .where(pd.notna(df["credit"]), pd.NA)
        .replace({float('nan'): pd.NA})
    )

    # Clean Platform Fee Debit
    # Look for debit 2500 followed immediately by credit
    platform_fee_mask = df["debit"].fillna(0).astype(float) == 2500

    rows_to_drop = []
    for idx in df[platform_fee_mask].index:
        if idx + 1 in df.index and pd.notna(df.loc[idx + 1, "credit"]):
            # Decrease the next credit by 2500
            df.at[idx + 1, "credit"] = float(df.at[idx + 1, "credit"]) - 2500
            # Mark current row for deletion
            rows_to_drop.append(idx)

    # Drop the platform fee debit rows
    df = df.drop(index=rows_to_drop).reset_index(drop=True)

    # Move new columns to the front for readability
    cols = [c for c in ["debit", "credit"] if c in df.columns] + [c for c in df.columns if c not in ("debit", "credit")]
    return df[cols]

MISSING = "__MISSING__"
def _norm_col(series: pd.Series) -> pd.Series:
    """
    Return a *string* version of `series` suitable for exact matching.
    • pure numbers → strip commas, drop trailing .00
    • date-like strings → YYYY-MM-DD
    • everything else → stripped text
    • all nulls → ""
    """
    def _clean(val):
        if val is None:
            return ""
        if isinstance(val, (float, numbers.Number)) and math.isnan(val):
            return ""
        txt = str(val).strip()
        if txt.lower() in {"", "nan", "nat", "none", "<na>"}:
            return ""
        txt = re.sub(r"^[^0-9\-]+", "", txt)       # keep minus sign & digits
        # ---- NUMERIC? (digits, commas, optional decimal) --------------------

        if "." in txt and "," in txt and txt.index('.')<txt.index(','):
            txt = txt.replace(".", "")      # remove thousand separators
            txt = txt.replace(",", ".")     # convert decimal comma to period

        no_commas = txt.replace(",", "")
        if re.fullmatch(r"-?\d+(\.\d+)?", no_commas):
            if no_commas.endswith(".00"):
                no_commas = no_commas[:-3]
            
            elif no_commas.endswith(".0"):
                no_commas = no_commas[:-2]
            return no_commas

        # ---- DATE-LIKE?  (contains letters or / or -) -----------------------
        if any(ch.isalpha() for ch in txt) or "/" in txt or "-" in txt:
            try:
                dt = parse(txt, dayfirst=False, fuzzy=False)
                return dt.strftime("%Y-%m-%d")
            except (ValueError, OverflowError):
                pass

        # ---- fallback: plain text ------------------------------------------
        return txt

    # Vectorise with .map
    return series.map(_clean)

def _ask_strip_config(col_name: str) -> dict | None:
    """
    Ask whether to strip substrings from a text column.
    Returns
    -------
    dict | None
        {
            'patterns'   : [list of substrings to remove],
            'ignore_case': bool,
            'alpha_only' : bool   # NEW – keep only A-Z afterwards?
        }
        or None if the user declines.
    """
    if not questionary.confirm(
            f"Column '{col_name}' looks textual – remove specific substrings?",
            default=False).ask():
        return None

    pats = questionary.text(
        "Enter substrings to remove (comma-separated):"
    ).ask()
    patterns = [p.strip() for p in pats.split(",") if p.strip()]
    if not patterns:
        return None

    ignore_case = questionary.confirm(
        "Ignore case when searching for these substrings?",
        default=True).ask()

    alpha_only = questionary.confirm(
        "After stripping, keep alphabetic characters only (A-Z)?",
        default=False).ask()

    return {
        "patterns": patterns,
        "ignore_case": ignore_case,
        "alpha_only": alpha_only          # ← NEW flag
    }


def _apply_strip(series: pd.Series, cfg: dict) -> pd.Series:
    """Apply the configured substring removal (+ optional alpha-filter)."""
    flags = re.IGNORECASE if cfg["ignore_case"] else 0

    def _strip(val: str) -> str:
        s = str(val)
        for pat in cfg["patterns"]:
            s = re.sub(re.escape(pat), "", s, flags=flags)
        if len(s)>23:
            s = s[:23]
        if cfg["alpha_only"]:
            s = re.sub(r"[^A-Za-z]", "", s)
        return s.strip().upper()

    return series.map(_strip)

# ────────────────────────── main function ──────────────────────────
def audit_check() -> Dict[str, pd.DataFrame]:
    # 1 ─── choose directory & main items ────────────────────────────────────────
    audit_dir = _ask_directory()

    # make sure expected 'source' directory exists
    source_dir = audit_dir / "source"
    while not source_dir.is_dir():
        console.print("[bold red]Directory must contain a sub-folder named 'source'.[/bold red]")
        audit_dir = _ask_directory()
        source_dir = audit_dir / "source"

    main_csvs = [f.name for f in audit_dir.glob("*.csv")]
    if not main_csvs:
        console.print("[bold red]No CSV found in audit directory![/bold red]")
        return {}

    if len(main_csvs) > 1:
        main_file_name = _pick_one("Multiple CSVs found – pick the main table:", main_csvs)
    else:
        main_file_name = main_csvs[0]

    main_df = _load_csv_safely(audit_dir / main_file_name)


    # 3 ─── date column & month signature ───────────────────────────────────────
    date_col = _pick_one("Which column holds the transaction date?", list(main_df.columns))
    # parse dates (ignore time) – error coercion yields NaT which is fine
    main_df[date_col] = pd.to_datetime(
        main_df[date_col]
            .astype(str)
            .str.split()
            .str[0]
            .where(lambda s: ~s.isin(["", "nan", "NaN", "None"]), other=pd.NA),
        errors="coerce",
        dayfirst=False,                # keep default; adjust if needed
    )
    print (main_df.head())
    if main_df[date_col].isna().all():
        console.print("[bold red]Could not parse ANY dates – aborting.[/bold red]")
        return {}

    main_df = main_df.dropna(subset=[date_col])
    main_df["_month_sig"] = main_df[date_col].apply(_month_signature)
    print (main_df.head())
    
    def select_columns_in_order(columns, prompt):
        """
        Let the user pick columns one-by-one; return them in the order selected.
        """
        ordered = []
        remaining = list(columns)  # copy so we can pop

        console.print(f"[bold cyan]{prompt}[/bold cyan]")
        while remaining:
            choice = questionary.select(
                "Select next column (or '<Done>' to finish):",
                choices=remaining + ["<Done>"]
            ).ask()

            if choice == "<Done>":
                break   # exit the loop

            ordered.append(choice)
            remaining.remove(choice)

        # ensure at least one column was selected
        if not ordered:
            console.print("[bold red]You must select at least one column.[/bold red]")
            return select_columns_in_order(columns, prompt)

        return ordered

    # 4 ─── matching column(s) between main & source ────────────────────────────
    match_cols_main = select_columns_in_order(list(main_df.columns), "Select column(s) in the desired order:")
    if not match_cols_main:
        console.print("[bold red]Need at least one matching column.[/bold red]")
        return {}
    else:
        print(match_cols_main)

    strip_cfg: dict[str, dict] = {}

    for col in match_cols_main:
        if re.search(r"name|description", col, flags=re.I) \
        and pd.api.types.is_string_dtype(main_df[col]):
            cfg = _ask_strip_config(col)
            if cfg:
                strip_cfg[col] = cfg
                main_df[col] = _apply_strip(main_df[col], cfg)
    print(main_df[match_cols_main].head())
    print(strip_cfg)

    same_columns_for_all = questionary.confirm(
        "Will ALL month files use the SAME column names for matching?", default=True
    ).ask()
    match_cols_src=None
    strip_cfg_src: dict[str, dict] = {}

    # 5 ─── containers for audit results ────────────────────────────────────────
    verified_flag = []
    unmatched_rows = []
    duplicate_issues = []

    # 6 ─── iterate month by month to avoid reopening files many times ──────────
    for month_sig, month_chunk in main_df.groupby("_month_sig"):
        # locate month file(s)
        month_files = [f for f in source_dir.glob(f"*{month_sig}*.csv")]
        if not month_files:
            console.print(f"[bold red]No source file found for month pattern '{month_sig}'.[/bold red]")
            verified_flag.extend([False] * len(month_chunk))
            unmatched_rows.append(month_chunk)
            continue
        elif len(month_files) > 1:
            pick = _pick_one(f"Multiple source files for {month_sig} – pick one:", [f.name for f in month_files])
            source_path = source_dir / pick
        else:
            source_path = month_files[0]

        source_df = _load_csv_safely(source_path)
        source_df = split_debit_credit(source_df)

        # choose columns in source (either same as main or ask)
        if match_cols_src and same_columns_for_all:
            print(match_cols_src)
        else : 
            match_cols_src = select_columns_in_order(list(source_df.columns), f"Select matching column(s) for source file '{source_path.name}':")
            if not match_cols_src:
                console.print("[bold red]No columns chosen – skipping this source file.[/bold red]")
                verified_flag.extend([False] * len(month_chunk))
                unmatched_rows.append(month_chunk)
                continue
            else: 
                print(match_cols_src)

        if same_columns_for_all and strip_cfg_src:
            print(strip_cfg_src)
            for i,j in strip_cfg_src.items():
                source_df[i] = _apply_strip(source_df[i], j)
        else:
            if not same_columns_for_all:
                strip_cfg_src: dict[str, dict] = {}
            for col in match_cols_src:
                print(f"Checking column '{col}' for stripping...")
                if re.search(r"name|description", col, flags=re.I):
                    print(f"Column '{col}' looks like a name or description.")
                    cfg = None
                    if not strip_cfg_src.get(col):
                        cfg = _ask_strip_config(col)
                    if cfg:
                        strip_cfg_src[col] = cfg
                        print(f"strip_cfg_src: {strip_cfg_src}")
                        source_df[col] = _apply_strip(source_df[col], strip_cfg_src.get(col))
        
        print(source_df[match_cols_src].head())

        # 1️⃣ build keys WITHOUT forcing to string
        left_keys  = month_chunk[match_cols_main].copy()
        right_keys = source_df[match_cols_src].copy()

        MISSING = "__MISSING__"
        for c in left_keys.columns:
            if not strip_cfg.get(c):
                print(f"Normalising column '{c}' in left keys...")
                left_keys[c] = _norm_col(left_keys[c]).replace({"": MISSING})

        for c in right_keys.columns:
            if not strip_cfg_src.get(c):
                print(f"Normalising column '{c}' in right keys...")
                right_keys[c] = _norm_col(right_keys[c]).replace({"": MISSING})

        # 2️⃣ Make tuple keys
        left_tuples  = left_keys.apply(tuple, axis=1)
        right_tuples = right_keys.apply(tuple, axis=1)

        print(left_tuples.head())
        print(right_tuples.head())

        # 3️⃣ Existence check
        month_verified = left_tuples.isin(right_tuples)
        verified_flag.extend(month_verified.tolist())
        right_keys.to_csv(audit_dir / f"check/right_keys{month_sig}.csv", index=False)  # save for debugging

        matched_cnt   = int(month_verified.sum())
        unmatched_cnt = int((~month_verified).sum())
        console.print(
            f"[green]✓ {month_sig}  Matched: {matched_cnt:,}  "
            f"Unmatched: {unmatched_cnt:,}[/green]"
        )

        # 4️⃣ Unmatched rows
        unmatched_rows.append(month_chunk.loc[~month_verified].copy())

        # 5️⃣ Duplicate keys inside the source
        dup_mask = right_keys.duplicated(keep=False)
        if dup_mask.any():
            duplicate_issues.append(source_df.loc[dup_mask].copy())

    # 7 ─── assemble final DataFrames ───────────────────────────────────────────
    main_df["verified_in_source"] = verified_flag
    unmatched_df = pd.concat(unmatched_rows, ignore_index=True) if unmatched_rows else pd.DataFrame()
    duplicates_df = pd.concat(duplicate_issues, ignore_index=True) if duplicate_issues else pd.DataFrame()

    # 8 ─── optional exports ───────────────────────────────────────────────────
    def _maybe_export(df: pd.DataFrame, default_name: str):
        if df.empty:
            console.print(f"[italic]{default_name} is empty – nothing to export.[/italic]")
            return
        if questionary.confirm(f"Export '{default_name}' to disk?", default=False).ask():
            fmt = _pick_one("Choose export format:", ["CSV", "XLSX"])
            fname = questionary.text(f"Enter file name (without extension) [{default_name}]:",
                                     default=default_name).ask()
            out_path = audit_dir / f"{fname}.{ 'csv' if fmt=='CSV' else 'xlsx'}"
            if fmt == "CSV":
                df.to_csv(out_path, index=False)
            else:
                df.to_excel(out_path, index=False)
            console.print(f"[green]Saved to {out_path}[/green]")

    _maybe_export(main_df, "main_verified")
    _maybe_export(unmatched_df, "unmatched_rows")
    _maybe_export(duplicates_df, "duplicated_entry_issue")

    return {
        "main_verified": main_df,
        "unmatched": unmatched_df,
        "duplicates": duplicates_df
    }


# ────────────────────────── run standalone ──────────────────────────
if __name__ == "__main__":
    audit_check()
