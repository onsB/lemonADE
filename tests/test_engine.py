import datetime as dt
import functools
from pathlib import Path

import pytest

import app
from app.engine import LayoutMismatch, best_fit, extract, month_number, parse_amount, parse_date
from app.layout import LAYOUTS, RBC_VISA, TD_VISA
from app.parser import parse_statement
from app.rows import read_rows

STATEMENTS = sorted((Path(app.__file__).parents[1] / "data" / "statements").glob("*.pdf"))
TD_STATEMENTS = [p for p in STATEMENTS if p.name.startswith("TD_")]


@functools.cache
def rows_for(pdf):
    return read_rows(pdf)


@functools.cache
def fit_for(pdf):
    return best_fit(rows_for(pdf), LAYOUTS)


# --- on the real statements (skipped when data/statements is empty) ---

@pytest.mark.parametrize("pdf", STATEMENTS, ids=lambda p: p.stem)
def test_some_layout_fits(pdf):
    assert fit_for(pdf) is not None


@pytest.mark.parametrize("pdf", STATEMENTS, ids=lambda p: p.stem)
def test_transactions_add_up(pdf):
    fit = fit_for(pdf)
    if fit.layout.name == "CIBC Mastercard" and fit.gap != 0:
        pytest.xfail("CIBC payments are in a separate table that we skip on purpose")
    assert fit.gap == 0


@pytest.mark.parametrize("pdf", STATEMENTS, ids=lambda p: p.stem)
def test_other_layouts_dont_fit(pdf):
    """Each bank's statement must be rejected by every other bank's layout."""
    for layout in LAYOUTS:
        if layout is not fit_for(pdf).layout:
            with pytest.raises(LayoutMismatch):
                extract(rows_for(pdf), layout)


@pytest.mark.parametrize("pdf", TD_STATEMENTS, ids=lambda p: p.stem)
def test_td_matches_old_parser(pdf):
    """The old TD-only parser is the answer key: same transactions and balances."""
    old_df, old_opening, old_closing, _ = parse_statement(pdf)
    fit = fit_for(pdf)

    old = sorted(zip(old_df["date"].dt.date, old_df["posted"].dt.date, old_df["amount"].round(2)))
    new = sorted(zip(fit.df["date"], fit.df["posted"], fit.df["amount"].round(2)))
    assert new == old
    assert (fit.opening, fit.closing) == (old_opening, old_closing)


# --- small examples (run anywhere) ---

@pytest.mark.parametrize("text, expected", [
    ("99,99 $", 99.99),
    ("-1 234,56 $", -1234.56),   # minus, thousands space
    ("(1 234,56 $)", -1234.56),  # RBC writes negatives in parentheses
    ("", 0.0),
])
def test_parse_amount(text, expected):
    assert parse_amount(text, RBC_VISA) == expected


@pytest.mark.parametrize("text, expected", [
    ("mar", 3), ("MARS", 3), ("DÉC", 12), ("août", 8), ("sept", 9),
    ("JUN", 6), ("JUL", 7),               # how RBC and CIBC write June and July
    ("MARCHE", None), ("DECATHLON", None), ("SEPAQ", None),  # only start like a month
])
def test_month_number(text, expected):
    assert month_number(text) == expected


def test_parse_date_takes_the_year_from_the_statement_end():
    end = dt.date(2026, 1, 6)
    assert parse_date("3 jan", end) == dt.date(2026, 1, 3)
    assert parse_date("28 DÉC", end) == dt.date(2025, 12, 28)  # before the new year
    assert parse_date("jan 3", end) == dt.date(2026, 1, 3)     # month first, as CIBC writes it


def test_td_layout_is_valid():
    assert TD_VISA.model_validate_json(TD_VISA.model_dump_json()) == TD_VISA
