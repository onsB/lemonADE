"""Turn any statement PDF into rows of positioned words, whatever the bank's layout."""

from dataclasses import dataclass

import pdfplumber

# Words whose vertical middles are this close (in points) share a row. A fixed value,
# because some PDFs report word heights that are far too small to derive it from.
ROW_TOLERANCE = 3.0


@dataclass
class Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float

    @property
    def middle(self) -> float:
        return (self.top + self.bottom) / 2


@dataclass
class Row:
    page: int
    words: list[Word]  # left to right

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


def read_rows(source) -> list[Row]:
    """Return every visual row in the PDF, top to bottom. `source` is a path or file object."""
    rows = []
    with pdfplumber.open(source) as pdf:
        for page in pdf.pages:
            upright = page.filter(lambda o: o.get("upright", True))  # drop rotated margin text
            words = [
                Word(w["text"], w["x0"], w["x1"], w["top"], w["bottom"])
                for w in upright.extract_words(x_tolerance=1)
            ]
            rows += _group_into_rows(words, page.page_number)
    return rows


def _group_into_rows(words: list[Word], page: int) -> list[Row]:
    groups: list[list[Word]] = []
    for word in sorted(words, key=lambda w: w.middle):
        if groups and word.middle - groups[-1][0].middle <= ROW_TOLERANCE:
            groups[-1].append(word)
        else:
            groups.append([word])

    return [Row(page, sorted(group, key=lambda w: w.x0)) for group in groups]
