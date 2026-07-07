"""CSV input/output for column seed files and row seed aggregates."""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any


_COLUMN_FILE_RE = re.compile(
    r"^(?P<index>\d+)_(?P<name>[^.]+)\.csv$"
)


def write_column_seed(path: Path, values: list[Any]) -> None:
    """Write a column seed file: one value per line, no header."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, quoting=csv.QUOTE_ALL)
        for value in values:
            writer.writerow(["null" if value is None else str(value)])


def read_column_seed(path: Path) -> list[str]:
    """Read values from a column seed file, one value per line.

    Quotes added by QUOTE_ALL are stripped from each value.
    """
    with path.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        return [row[0].strip('"') if row else "" for row in reader]


def discover_column_files(table_dir: Path) -> list[tuple[int, str, Path]]:
    """Discover column seed files in ``table_dir`` and sort by numeric index."""
    files: list[tuple[int, str, Path]] = []
    if not table_dir.exists():
        return files
    for path in table_dir.iterdir():
        if not path.is_file():
            continue
        match = _COLUMN_FILE_RE.match(path.name)
        if not match:
            continue
        index = int(match.group("index"))
        files.append((index, match.group("name"), path))
    files.sort(key=lambda item: item[0])
    return files


def build_row_aggregate(
    table_dir: Path,
    *,
    first_ptag_info: tuple[int, str] | None = None,
) -> tuple[list[str], list[list[str]]]:
    """Build header and rows by cyclic-filling column seed files.

    If first_ptag_info is provided, inject a virtual ${device_code} column
    at the position corresponding to the first ptag index.
    """
    columns = discover_column_files(table_dir)
    if not columns and first_ptag_info is None:
        return [], []

    # Inject first ptag as a virtual column at the correct position
    if first_ptag_info is not None:
        ptag_index, ptag_name = first_ptag_info
        # Insert into columns list at the right position (sorted by index)
        columns_with_ptag: list[tuple[int, str, Path]] = []
        ptag_inserted = False
        for col_idx, col_name, col_path in columns:
            if not ptag_inserted and col_idx > ptag_index:
                columns_with_ptag.append((ptag_index, ptag_name, None))
                ptag_inserted = True
            columns_with_ptag.append((col_idx, col_name, col_path))
        if not ptag_inserted:
            columns_with_ptag.append((ptag_index, ptag_name, None))
        columns = columns_with_ptag

    column_values: list[list[str]] = []
    max_len = 0
    for idx, name, path in columns:
        if path is None:
            # Virtual first ptag column: all ${device_code}
            values = [f"${{device_code}}" for _ in range(1)]  # single row, replicated cyclically
        else:
            values = read_column_seed(path)
            max_len = max(max_len, len(values))
        column_values.append(values)

    # max_len is now the longest real column
    if max_len == 0:
        max_len = 1

    header = [name for _, name, _ in columns]

    rows: list[list[str]] = []
    for row_index in range(max_len):
        row = []
        for i, (idx, name, path) in enumerate(columns):
            if path is None:
                # First ptag: always ${device_code}
                value = "${device_code}"
            else:
                values = column_values[i]
                value = values[row_index % len(values)] if values else "null"
            row.append(value)
        rows.append(row)

    return header, rows


def write_row_aggregate(path: Path, header: list[str], rows: list[list[str]]) -> None:
    """Write a row seed aggregate CSV with ``header`` and ``rows``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, quoting=csv.QUOTE_ALL)
        writer.writerow(header)
        writer.writerows(rows)


def cleanup_table_seeds(output_dir: Path, db_name: str, table_name: str) -> None:
    """Remove a table's column seed directory and row aggregate CSV."""
    table_dir = output_dir / db_name / table_name
    aggregate = output_dir / db_name / f"{table_name}.csv"
    if table_dir.exists():
        for child in table_dir.iterdir():
            child.unlink()
        table_dir.rmdir()
    if aggregate.exists():
        aggregate.unlink()
