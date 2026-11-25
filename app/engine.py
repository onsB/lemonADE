import re

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


def find_columns(page_rows: list[Row], layout: Layout) -> tuple[dict[str, Span], int] | None:
    """Each column's (x0, x1) on this page, and the index of the last header row.
    None when the page has no transaction table."""
    # Look for the first few consecutive rows that hold every header together. Searching
    # the whole page instead would match e.g. "DATE" in "DATE DU RELEVÉ" near the top.
    for start in range(len(page_rows)):
        window = page_rows[start : start + HEADER_ROWS]
        found = {c.name: _find_header(window, c.header) for c in layout.columns}
        if all(found.values()):
            spans = {name: span for name, (span, _) in found.items()}
            last_header_row = start + max(offset for _, offset in found.values())
            return spans, last_header_row
    return None


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


def table_rows(page_rows: list[Row], layout: Layout) -> tuple[dict[str, Span], list[Row]] | None:
    """The column spans and the rows of this page's transaction table, cropped to the table.
    None when the page has no transaction table."""
    found = find_columns(page_rows, layout)
    if found is None:
        return None
    spans, last_header_row = found

    # Words right of the last column are a side panel, not part of the table.
    edge = max(x1 for _, x1 in spans.values()) + TABLE_MARGIN
    table = []
    for row in page_rows[last_header_row + 1 :]:
        words = [w for w in row.words if w.x0 <= edge]
        if not words:
            continue
        row = Row(row.page, words)
        if any(row.text.startswith(end) for end in layout.table_ends):
            break
        if table and row.words[0].top - table[-1].words[0].top > TABLE_GAP:
            break
        table.append(row)
    return spans, table


def split_cells(row: Row, spans: dict[str, Span]) -> dict[str, str]:
    """{"date": "9 mar", "posted": "10 mar", "description": "IGA #9999 VERDUN", "amount": "99,99 $"}.
    Every column in `spans` gets a key; empty string when the row has nothing there."""
    cells: dict[str, list[Word]] = {name: [] for name in spans}
    for word in row.words:
        cells[_column_for(word, spans, cells)].append(word)
    return {name: " ".join(w.text for w in words) for name, words in cells.items()}


def _column_for(word: Word, spans: dict[str, Span], cells: dict[str, list[Word]]) -> str:
    # Position alone isn't enough: e.g. RBC descriptions start under the posted-date header.
    # So a word must also look like the kind of value the column holds.
    for name in DATE_COLUMNS & spans.keys():
        # At most a day and a month, so a word like "MARCHE" right after the date stays text.
        if _looks_like_date(word.text) and _overlaps(word, spans[name]) and len(cells[name]) < 2:
            return name
    for name in MONEY_COLUMNS & spans.keys():
        if MONEY.fullmatch(word.text) and _overlaps(word, spans[name]):
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


def _overlaps(word: Word, span: Span) -> bool:
    return word.x0 <= span[1] + TABLE_MARGIN and word.x1 >= span[0] - TABLE_MARGIN


def extract(rows: list[Row], layout: Layout) -> tuple[pd.DataFrame, float, float]:
    """Transactions (date, posted, description, amount, page), opening balance, closing balance."""
    pass
