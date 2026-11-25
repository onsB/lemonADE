import pandas as pd
from langchain.agents import create_agent
from langchain.tools import tool

from app.engine import best_fit
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
    fit = best_fit(read_rows(source), LAYOUTS)
    if fit is None:
        return None

    df, layout, gap = fit.df, fit.layout, fit.gap
    df = df.assign(
        date=pd.to_datetime(df["date"]),
        posted=pd.to_datetime(df["posted"]),
        # the engine's amounts are positive when money goes out
        kind=df["amount"].map(lambda amount: "purchase" if amount > 0 else "credit"),
    )
    return {
        "transaction_count": len(df),
        "total_spending": round(df.loc[df["amount"] > 0, "amount"].sum(), 2),
        "opening_balance": fit.opening,
        "closing_balance": fit.closing,
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
