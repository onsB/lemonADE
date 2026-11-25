import re
from itertools import groupby

import pandas as pd

from app.layout import Layout
from app.rows import Row, Word

# A table's header can be spread over a few rows, e.g. "DATE DE" above "L'OPÉRATION".
HEADER_ROWS = 3
# Words closer than this (in points) belong to the same header label, e.g. "MONTANT (EN $)".
LABEL_GAP = 4.0
# How far (in points) a value may stick out past its column header, e.g. "999,99 $" under "Dépôts ($)".
TABLE_MARGIN = 5.0
# A vertical gap this big (in points) ends the table, e.g. before a tear-off payment slip.
# Rows inside a table are about 8 to 12 points apart.
TABLE_GAP = 40.0

Span = tuple[float, float]

# What kind of value each column holds. Any other column ("description", "category") is text.
DATE_COLUMNS = {"date", "posted"}
MONEY_COLUMNS = {"amount", "withdrawal", "deposit", "balance"}

# Month names; statements print them whole or cut short ("mar", "DÉC", "sept").
# Banks also write June and July as "JUN" and "JUL".
MONTHS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "jun": 6, "juillet": 7, "jul": 7, "août": 8, "aout": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}
# One word of an amount: "-9", "999,99", "(12,34", "$", "$)". A thousands space splits amounts.
MONEY = re.compile(r"[-(]?\d[\d,.]*\)?|\$\)?")


def find_columns(page_rows: list[Row], layout: Layout, start: int = 0) -> tuple[dict[str, Span], int] | None:
    """Each column's (x0, x1) for the first table header at or after row `start`, and the
    index of the last header row. None when there is no further transaction table."""
    for i in range(start, len(page_rows)):
        if found := _header_at(page_rows, i, layout):
            return found
    return None


def _header_at(page_rows: list[Row], start: int, layout: Layout) -> tuple[dict[str, Span], int] | None:
    """The table header that begins exactly at row `start`, if there is one."""
    # A header can span a few consecutive rows, but all of its labels must be together.
    # Searching the whole page instead would match e.g. "DATE" in "DATE DU RELEVÉ" near the top.
    window = page_rows[start : start + HEADER_ROWS]
    found = {c.name: _find_header(window, c.header) for c in layout.columns}
    if not all(found.values()):
        return None
    offsets = [offset for _, offset in found.values()]
    if min(offsets) != 0:
        return None  # it begins on a later row, so it's not this row's header
    return {name: span for name, (span, _) in found.items()}, start + max(offsets)


def _find_header(window: list[Row], header: str) -> tuple[Span, int] | None:
    """The span of the label starting with `header`, and which row of the window it is on."""
    for offset, row in enumerate(window):
        for i, word in enumerate(row.words):
            if word.text == header:
                return _label_span(row.words[i:]), offset
    return None


def _label_span(words: list[Word]) -> Span:
    """Extend the first word over the words that follow it closely on the same row."""
    end = words[0].x1
    for word in words[1:]:
        if word.x0 - end > LABEL_GAP:
            break
        end = word.x1
    return words[0].x0, end


def tables(page_rows: list[Row], layout: Layout) -> list[tuple[dict[str, Span], list[Row]]]:
    """Every transaction table on this page: its column spans and its rows, cropped to the table.
    Empty when the page has none."""
    found_tables = []
    start = 0
    while found := find_columns(page_rows, layout, start):
        spans, last_header_row = found
        rows, start = _table_body(page_rows, last_header_row + 1, spans, layout)
        found_tables.append((spans, rows))
    return found_tables


def _table_body(page_rows: list[Row], start: int, spans: dict[str, Span], layout: Layout) -> tuple[list[Row], int]:
    """The rows of one table from row `start`, and the index of the row where the table ended."""
    # Words right of the last column are a side panel, not part of the table.
    edge = max(x1 for _, x1 in spans.values()) + TABLE_MARGIN
    table: list[Row] = []
    for i in range(start, len(page_rows)):
        if _header_at(page_rows, i, layout):
            return table, i  # the next table starts here
        words = [w for w in page_rows[i].words if w.x0 <= edge]
        if not words:
            continue
        row = Row(page_rows[i].page, words)
        if any(row.text.startswith(end) for end in layout.table_ends):
            return table, i + 1
        if table and row.words[0].top - table[-1].words[0].top > TABLE_GAP:
            return table, i
        table.append(row)
    return table, len(page_rows)


def split_cells(row: Row, spans: dict[str, Span]) -> dict[str, str]:
    """{"date": "9 mar", "posted": "10 mar", "description": "IGA #9999 VERDUN", "amount": "99,99 $"}.
    Every column in `spans` gets a key; empty string when the row has nothing there."""
    cells: dict[str, list[Word]] = {name: [] for name in spans}
    for word in _join_amounts(row.words):
        cells[_column_for(word, spans, cells)].append(word)
    return {name: " ".join(w.text for w in words) for name, words in cells.items()}


def _join_amounts(words: list[Word]) -> list[Word]:
    """Merge touching money-looking words into one, e.g. "(1" + "234,56" + "$)".
    Otherwise the thousands part of a right-aligned amount can stick out of its column."""
    joined: list[Word] = []
    for word in words:
        prev = joined[-1] if joined else None
        if prev and _looks_like_money(word.text) and _looks_like_money(prev.text) and word.x0 - prev.x1 <= LABEL_GAP:
            joined[-1] = Word(f"{prev.text} {word.text}", prev.x0, word.x1, prev.top, prev.bottom)
        else:
            joined.append(word)
    return joined


def _column_for(word: Word, spans: dict[str, Span], cells: dict[str, list[Word]]) -> str:
    # Position alone isn't enough: e.g. RBC descriptions start under the posted-date header.
    # So a word must also look like the kind of value the column holds.
    for name in DATE_COLUMNS & spans.keys():
        # At most a day and a month, so a word like "MARCHE" right after the date stays text.
        if _looks_like_date(word.text) and _overlaps(word, spans[name]) and len(cells[name]) < 2:
            return name
    for name in MONEY_COLUMNS & spans.keys():
        if _looks_like_money(word.text) and _overlaps(word, spans[name]):
            return name
    if "category" in spans and word.x0 >= spans["category"][0] - TABLE_MARGIN:
        return "category"
    return "description"


def month_number(text: str) -> int | None:
    """1 for "jan", "JANV." or "janvier"; None for words like "MARCHE" that only start like a month."""
    text = text.lower().rstrip(".")
    if len(text) < 3:
        return None
    return next((number for name, number in MONTHS.items() if name.startswith(text)), None)


def _looks_like_date(text: str) -> bool:
    """A day number or a month name."""
    return (text.isdigit() and len(text) <= 2) or month_number(text) is not None


def _looks_like_money(text: str) -> bool:
    """Every part looks like a piece of an amount, e.g. "-9 999,99 $"."""
    return all(MONEY.fullmatch(part) for part in text.split())


def _overlaps(word: Word, span: Span) -> bool:
    return word.x0 <= span[1] + TABLE_MARGIN and word.x1 >= span[0] - TABLE_MARGIN


def read_transactions(rows: list[Row], layout: Layout) -> list[dict]:
    """One dict of cells per transaction, plus its page, across every table page.
    Values are still text, e.g. {"date": "9 mar", ..., "amount": "-9 999,99 $", "page": 1}."""
    skip = [re.compile(pattern) for pattern in layout.skip]
    text_columns = [c.name for c in layout.columns if c.name not in DATE_COLUMNS | MONEY_COLUMNS]
    transactions: list[dict] = []
    last_date = ""  # for statements that only print the date on a day's first transaction

    page_tables = [
        (page, spans, table)
        for page, page_rows in groupby(rows, key=lambda r: r.page)
        for spans, table in tables(list(page_rows), layout)
    ]
    for page, spans, table in page_tables:
        current = None  # the transaction extra lines below it belong to ("below")
        pending: list[dict] = []  # extra lines waiting for the amount row under them ("above")

        for row in table:
            if any(p.search(row.text) for p in skip):
                continue
            cells = split_cells(row, spans)
            if cells.get("date"):
                last_date = cells["date"]
            has_amount = any(cells.get(name) for name in ("amount", "withdrawal", "deposit"))
            has_date = bool(cells.get("date")) or not layout.dates_repeat

            if layout.description_wraps == "below":
                if has_date and has_amount:
                    current = cells | {"date": cells.get("date") or last_date, "page": page}
                    transactions.append(current)
                elif current:
                    _add_text(current, [cells], text_columns)
                # anything before the first transaction (e.g. the previous balance) is dropped
            else:
                if has_amount:
                    transaction = cells | {"date": cells.get("date") or last_date, "page": page}
                    _add_text(transaction, pending, text_columns, before=True)
                    transactions.append(transaction)
                    pending = []
                else:
                    pending.append(cells)
    return transactions


def _add_text(transaction: dict, lines: list[dict], columns: list[str], before: bool = False) -> None:
    """Join the text columns of extra lines onto a transaction, before or after its own text."""
    for name in columns:
        extra = [line[name] for line in lines if line[name]]
        parts = extra + [transaction[name]] if before else [transaction[name]] + extra
        transaction[name] = " ".join(p for p in parts if p)


def extract(rows: list[Row], layout: Layout) -> tuple[pd.DataFrame, float, float]:
    """Transactions (date, posted, description, amount, page), opening balance, closing balance."""
    pass
