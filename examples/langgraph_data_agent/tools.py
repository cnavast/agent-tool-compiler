from pathlib import Path
import re
import sqlite3

from langchain_core.tools import tool

DB_PATH = Path(__file__).resolve().parent / "data" / "shipments.db"
BLOCKED_SQL = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE)\b", re.I)


@tool
def list_tables() -> str:
    """List available SQLite tables."""
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    return "\n".join(row[0] for row in rows)


@tool
def describe_table(table_name: str) -> str:
    """Describe a SQLite table's columns."""
    safe_name = re.sub(r"[^a-zA-Z0-9_]", "", table_name)
    with sqlite3.connect(DB_PATH) as conn:
        columns = conn.execute(f"PRAGMA table_info({safe_name})").fetchall()
    if not columns:
        return f"No table named {table_name}."
    return "\n".join(f"{col[1]} {col[2]}" for col in columns)


@tool
def run_sql(query: str) -> str:
    """Run a read-only SELECT query against the demo shipments database."""
    stripped = query.strip()
    if not stripped.lower().startswith("select"):
        return "SQL error: only SELECT queries are allowed."
    if BLOCKED_SQL.search(stripped):
        return "SQL error: blocked write or schema operation."
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute(stripped)
            rows = cursor.fetchall()
            columns = [description[0] for description in cursor.description or []]
    except Exception as exc:
        return f"SQL error: {exc}"
    if not rows:
        return "The query returned no rows."
    return render_markdown_table(columns, rows)


def render_markdown_table(columns: list[str], rows: list[tuple]) -> str:
    text_rows = [[format_cell(value) for value in row] for row in rows]
    text_columns = [format_cell(column) for column in columns]
    widths = [
        max(len(text_columns[index]), *(len(row[index]) for row in text_rows))
        for index in range(len(text_columns))
    ]
    header = "| " + " | ".join(pad(text_columns[index], widths[index]) for index in range(len(widths))) + " |"
    separator = "| " + " | ".join("-" * widths[index] for index in range(len(widths))) + " |"
    body = [
        "| " + " | ".join(pad(row[index], widths[index]) for index in range(len(widths))) + " |"
        for row in text_rows
    ]
    return "\n".join([header, separator, *body])


def format_cell(value) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ")


def pad(value: str, width: int) -> str:
    return value + (" " * (width - len(value)))
