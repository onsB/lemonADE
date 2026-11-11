import pandas as pd

from app.layout import Layout
from app.rows import Row, Word

# A table's header can be spread over a few rows, e.g. "DATE DE" above "L'OPÉRATION".
HEADER_ROWS = 3
# Words closer than this (in points) belong to the same header label, e.g. "MONTANT (EN $)".
LABEL_GAP = 4.0

Span = tuple[float, float]


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


def extract(rows: list[Row], layout: Layout) -> tuple[pd.DataFrame, float, float]:
    """Transactions (date, posted, description, amount, page), opening balance, closing balance."""
    pass
