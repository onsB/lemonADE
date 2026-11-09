from langchain.agents import create_agent
from langchain.tools import tool

from app.llm import build_llm
from app.parser import parse_statement, StatementParseError

SYSTEM_PROMPT = """You are a helpful assistant that extracts information from bank statements.
You are given a PDF file of a bank statement. Your task is to call run_td_parser and to extract the transactions from the statement.
uour final output would be a short summary of the statement, including the number of transactions, total spending, opening and closing balances, and whether the statement reconciled.
"""


def run_agent(source) -> dict:
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
