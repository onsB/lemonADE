"""Score the layouts against every statement: which layout reads it, and does it add up?

Run with:  uv run python -m app.score
"""

import re
import time
from collections import Counter
from pathlib import Path

from app.engine import best_fit
from app.layout import LAYOUTS, Layout
from app.rows import read_rows

STATEMENTS = Path(__file__).parents[1] / "data" / "statements"


def score(layouts: list[Layout], folder: Path = STATEMENTS) -> list[dict]:
    """One result per statement: the layout that fits best (None if none does), its
    transaction count, and its reconciliation gap (0.0 when it adds up)."""
    results = []
    for pdf in sorted(folder.glob("*.pdf")):
        fit = best_fit(read_rows(pdf), layouts)
        results.append({
            "statement": _masked(pdf.stem),
            "layout": fit.layout.name if fit else None,
            "transactions": len(fit.df) if fit else 0,
            "gap": fit.gap if fit else None,
        })
    return results


def _masked(name: str) -> str:
    """File names can hold account digits, so hide long digit runs."""
    return re.sub(r"\d{4,}", lambda m: "#" * len(m.group()), name)


def main():
    start = time.time()
    results = score(LAYOUTS)

    for r in results:
        status = "no layout fits" if r["layout"] is None else "✓ adds up" if r["gap"] == 0 else f"⚠ off by {r['gap']:.2f}"
        print(f"{r['statement'][:45]:45}  {r['layout'] or '—':16} {r['transactions']:3} transactions  {status}")

    read = Counter(r["layout"] for r in results if r["layout"])
    added_up = Counter(r["layout"] for r in results if r["gap"] == 0)
    print()
    for name in read:
        print(f"{name:16} {added_up[name]}/{read[name]} add up")
    unread = sum(r["layout"] is None for r in results)
    total_added_up = sum(added_up.values())
    print(f"\n{total_added_up}/{len(results)} statements add up, {unread} unread, {time.time() - start:.0f}s")


if __name__ == "__main__":
    main()
