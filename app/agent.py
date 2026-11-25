import pandas as pd
from langchain.agents import create_agent
from langchain.tools import tool

from app.engine import LayoutMismatch, extract, reconciliation_gap
from app.layout import LAYOUTS
from app.llm import build_llm
from app.parser import parse_statement, StatementParseError
from app.rows import read_rows

SYSTEM_PROMPT = """You are a helpful assistant that extracts information from bank statements.
You are given a PDF file of a bank statement. Your task is to call run_td_parser and to extract the transactions from the statement.
uour final output would be a short summary of the statement, including the number of transactions, total spending, opening and closing balances, and whether the statement reconciled.
"""


def read_with_known_layouts(source) -> dict | None:
    """Read the statement with every known layout, without the LLM. The layout that
    reconciles wins; if none does, the closest one that fits at all (e.g. CIBC, whose
    payments we skip). None when no known layout fits this statement."""
    rows = read_rows(source)
    best = None
    for layout in LAYOUTS:
        try:
            df, opening, closing = extract(rows, layout)
        except LayoutMismatch:
            continue  # another bank's statement
        gap = reconciliation_gap(df, opening, closing, layout)
        if best is None or abs(gap) < abs(best[0]):
            best = (gap, layout, df, opening, closing)
    if best is None:
        return None

    gap, layout, df, opening, closing = best
    df = df.assign(
        date=pd.to_datetime(df["date"]),
        posted=pd.to_datetime(df["posted"]),
        # the engine's amounts are positive when money goes out
        kind=df["amount"].map(lambda amount: "purchase" if amount > 0 else "credit"),
    )
    return {
        "transaction_count": len(df),
        "total_spending": round(df.loc[df["amount"] > 0, "amount"].sum(), 2),
        "opening_balance": opening,
        "closing_balance": closing,
        "reconciled": gap == 0,
        "layout": layout.name,
        "notes": f"Read with the {layout.name} layout" + ("" if gap == 0 else f", off by {gap:.2f} $"),
        "df": df,
    }


def run_agent(source) -> dict:
    # Known banks need no LLM: try the saved layouts first.
    if known := read_with_known_layouts(source):
        return known
    if hasattr(source, "seek"):
        source.seek(0)  # read_rows already read the uploaded file

    found = {}

    @tool
    def run_td_parser() -> dict:
        """Parse a credit card statement and report whether it reconciled."""
        try:
            df, opening, closing, spending = parse_statement(source)
        except StatementParseError as e:
            return {"error": str(e)}

        reconciled = round(opening + df["amount"].sum(), 2) == closing

        summary = {
            "transaction_count": len(df),
            "total_spending": round(spending, 2),
            "opening_balance": opening,
            "closing_balance": closing,
            "reconciled": reconciled,
        }
        found.update(summary, df=df)
        return summary


    agent = create_agent(build_llm(), tools=[run_td_parser], system_prompt=SYSTEM_PROMPT)
    result = agent.invoke(
        {"messages": [{"role": "user", "content": f"Please parse the statement and summarize it."}]},
        config={"recursion_limit": 10},
    )
    found["notes"] = result["messages"][-1].content
    return found


if __name__ == "__main__":
    out = run_agent("app/data/statements/TD_CASH_BACK_VISA_INFINITE__CARD_3226_Feb_06-2026.pdf")
    print(out)
