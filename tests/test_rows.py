from pathlib import Path

import pdfplumber
import pytest

import functools

import app
from app.rows import ROW_TOLERANCE, read_rows

STATEMENTS = sorted((Path(app.__file__).parents[1] / "data" / "statements").glob("*.pdf"))

@functools.cache
def rows_for(pdf):
    return read_rows(pdf)

@functools.cache
def upright_word_counts(pdf):
    """number of upright words on each page, read with pdfplummber directly"""
    with pdfplumber.open(pdf) as doc:
        return {
            p.page_number: len(p.filter(lambda o: o.get("upright", True)).extract_words(x_tolerance=1))
            for p in doc.pages
        }

@pytest.mark.parametrize("pdf", STATEMENTS, ids=lambda p: p.stem)
def test_no_words_lost(pdf):
    assert sum(len(r.words) for r in rows_for(pdf)) == sum(upright_word_counts(pdf).values())

@pytest.mark.parametrize("pdf", STATEMENTS, ids=lambda p: p.stem)
def test_every_page_with_text_has_rows(pdf):
    pages_with_text = {page for page, count in upright_word_counts(pdf).items() if count > 0}
    assert {r.page for r in rows_for(pdf)} == pages_with_text


