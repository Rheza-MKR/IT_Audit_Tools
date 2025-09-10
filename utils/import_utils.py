import re
from pathlib import Path
import pandas as pd
import questionary
from rich.console import Console

console = Console()

# ───────────────────────── header detection ─────────────────────────

# --- value-like detectors -------------------------------------------------

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_NUM_RE  = re.compile(r"^-?\d{1,3}([,.\s]\d{3})*([.,]\d+)?$|^-?\d+([.]\d+)?$")   # 123, 1,234.56, -577000
_CARD_RE = re.compile(r"^\d{13,19}$")                                           # long IDs / card-like
_TZ_RE   = re.compile(r"UTC|GMT|\+\d{2}:?\d{2}$", re.I)

def _looks_numeric(s: str) -> bool:
    return bool(_NUM_RE.match(s))

def _looks_uuid(s: str) -> bool:
    return bool(_UUID_RE.match(s))

def _looks_cardlike(s: str) -> bool:
    return bool(_CARD_RE.match(s))

def _looks_datetimeish(s: str) -> bool:
    # quick n’ dirty: ISO date/time fragments or explicit TZ markers
    if _TZ_RE.search(s):
        return True
    # contain a yyyy-mm-dd pattern or time
    return bool(re.search(r"\b\d{4}-\d{2}-\d{2}\b", s)) or bool(re.search(r"\b\d{2}:\d{2}:\d{2}", s))

def _has_letters(s: str) -> bool:
    return bool(re.search(r"[A-Za-z]", s))

# --- smarter header detector ---------------------------------------------

def find_headers(path: Path, sheet_name: str | int = 0, max_rows: int = 30) -> int | None:
    """
    Heuristic header detector:
      • rewards rows with many non-null cells, high share of text, good uniqueness, and shortish labels
      • penalizes rows with many numeric/UUID/datetime/cardlike tokens (i.e., data rows)
    Returns 0-based row index, or None if nothing convincing is found.
    """
    try:
        block = pd.read_excel(path, sheet_name=sheet_name, header=None, nrows=max_rows)
    except Exception as e:
        console.print(f"[bold red]❌ Failed to preview Excel sheet: {e}[/bold red]")
        return None

    best_idx, best_score = None, float("-inf")

    for i, row in block.iterrows():
        vals = [str(x).strip() for x in row.tolist()]
        nn_vals = [v for v in vals if v not in ("", "nan", "None") and pd.notna(v)]
        n = len(nn_vals)
        if n == 0:
            continue

        textish = sum(_has_letters(v) for v in nn_vals) / n
        numeric = sum(_looks_numeric(v) for v in nn_vals) / n
        uuidish = sum(_looks_uuid(v) for v in nn_vals) / n
        cardish = sum(_looks_cardlike(v) for v in nn_vals) / n
        dtlike  = sum(_looks_datetimeish(v) for v in nn_vals) / n
        uniq    = len(set(nn_vals)) / n
        short   = sum(len(v) <= 35 for v in nn_vals) / n  # headers tend to be short labels

        # Score: more non-nulls + text + uniqueness, penalize value-like patterns
        score = (
            n * (1.0 + 1.6*textish + 0.5*uniq + 0.2*short)
            - n * (1.4*numeric + 1.0*dtlike + 1.2*uuidish + 0.8*cardish)
        )

        # Hard guards: if row looks too “value-like”, discard
        if textish < 0.35 and (numeric + dtlike + uuidish + cardish) > 0.40:
            continue

        if score > best_score:
            best_score, best_idx = score, i

    # If nothing convincing, return None (caller should fallback to header=0)
    if best_idx is None:
        console.print("[yellow]⚠ Could not confidently detect a header row; will fallback to header=0[/yellow]")
        return None

    console.print(f"[green]🔎 Header row auto-detected at index {best_idx}[/green]")
    return best_idx

# ───────────────────────── column cleaning ─────────────────────────

def _standardize_col_name(name) -> str:
    """Strip, collapse whitespace, keep readable (no snake-case)."""
    s = str(name).replace("\n", " ").replace("\r", " ").replace("\t", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _ensure_unique_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure column names are unique (foo, foo.1, foo.2 ...)."""
    seen: dict[str, int] = {}
    new_cols = []
    for c in df.columns:
        base = str(c)
        n = seen.get(base, 0)
        if n == 0:
            new = base
        else:
            new = f"{base}.{n}"
        seen[base] = n + 1
        new_cols.append(new)
    df.columns = new_cols
    return df

def _drop_unnamed_and_empty_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Drop columns with names like 'Unnamed: *' (or blank) and columns that are entirely NaN.
    """
    keep = []
    for c in df.columns:
        name = str(c).strip()
        is_unnamed = (name == "") or re.match(r"^unnamed[:\s]*", name, flags=re.I)
        if is_unnamed:
            continue
        if df[c].isna().all():
            continue
        keep.append(c)
    return df[keep]

def _looks_like_sequential_index(s: pd.Series) -> bool:
    """
    True if s looks like a saved index column (0..N-1 or 1..N), ignoring NaNs.
    Uses safe Python int conversion instead of dtype casts.
    """
    if s is None or len(s) == 0:
        return False

    v = pd.to_numeric(s, errors="coerce")  # float series with NaNs
    v = v.dropna()
    if v.empty:
        return False

    # Must be whole numbers only (no fractions)
    if not ((v % 1) == 0).all():
        return False

    # Convert to Python ints safely (avoids pandas int casting issues)
    try:
        ints = [int(x) for x in v.tolist()]
    except Exception:
        return False

    # No duplicates allowed
    if len(ints) != len(set(ints)):
        return False

    n = len(s)            # full column length (including NaNs)
    mn, mx = min(ints), max(ints)
    setv = set(ints)

    return (
        (mn == 0 and mx == n - 1 and setv == set(range(0, n))) or
        (mn == 1 and mx == n and setv == set(range(1, n + 1)))
    )

def _auto_drop_index_like_first_column(df: pd.DataFrame) -> pd.DataFrame:
    """
    Automatically drop the first column if it looks like a saved index OR is empty.
    Never crash: on any error, keep the column.
    """
    if df.shape[1] == 0:
        return df
    try:
        first_name = str(df.columns[0]).strip()
        first_col = df.iloc[:, 0]
        is_empty = first_col.isna().all()
        name_indexy = (
            (first_name == "") or
            re.match(r"^unnamed[:\s]*", first_name, flags=re.I) or
            first_name.lower() in {"index", "idx", "row", "rows"}
        )
        if is_empty or name_indexy or _looks_like_sequential_index(first_col):
            return df.iloc[:, 1:].copy()
        return df
    except Exception:
        # If detection fails for any reason, keep the column
        return df

def _clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardize names, drop junk (unnamed/all-NaN), drop index-like first column,
    then re-run cleanup and ensure uniqueness.
    """
    # standardize names
    df = df.rename(columns={c: _standardize_col_name(c) for c in df.columns})
    # drop obvious junk
    df = _drop_unnamed_and_empty_columns(df)
    # auto-drop saved index first col if present
    df = _auto_drop_index_like_first_column(df)
    # in case the first col drop exposed another unnamed/empty col, clean again
    df = _drop_unnamed_and_empty_columns(df)
    # ensure unique names
    df = _ensure_unique_columns(df)
    return df

# ───────────────────────── main safe reader ─────────────────────────

def read_file_safely(path: Path) -> pd.DataFrame | None:
    try:
        ext = path.suffix.lower()
        if ext in (".xlsx", ".xls"):
            try:
                xl = pd.ExcelFile(path, engine="openpyxl")
            except Exception as e:
                console.print(f"[bold red]❌ Failed opening Excel file: {e}[/bold red]")
                return None

            sheet_name = xl.sheet_names[0]
            if len(xl.sheet_names) > 1:
                sheet_name = questionary.select("Select sheet:", choices=xl.sheet_names).ask()
                if not sheet_name:
                    console.print("[blue]No sheet selected. Exiting.[/blue]")
                    return None

            if questionary.confirm("Auto-detect the header row?", default=False).ask():
                header_row = find_headers(path, sheet_name=sheet_name)
            else:
                header_row = 0

            try:
                df = pd.read_excel(path, sheet_name=sheet_name, header=(header_row or 0), engine="openpyxl")
            except Exception as e:
                # last resort: read everything as text to bypass casting issues
                console.print(f"[yellow]⚠ {e} — retrying as text-only load[/yellow]")
                df = pd.read_excel(path, sheet_name=sheet_name, header=(header_row or 0), dtype=str, engine="openpyxl")

            return _clean_columns(df)

        elif ext == ".csv":
            for kwargs in (dict(), dict(sep=";"), dict(encoding="latin-1")):
                try:
                    df = pd.read_csv(path, on_bad_lines="skip", low_memory=False, **kwargs)
                    return _clean_columns(df)
                except Exception:
                    continue
            console.print("[bold red]❌ Could not read CSV with common fallbacks.[/bold red]")
            return None

        else:
            console.print(f"[bold red]❌ Unsupported file format: {path.suffix}[/bold red]")
            return None

    except Exception as e:
        console.print(f"[bold red]❌ Could not open {path.name}: {e}[/bold red]")
        return None
