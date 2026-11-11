"""A small description of how one bank lays out its statements.

The generic engine reads any statement using one of these. For now they are written by
hand; later the LLM writes them. Labels are copied exactly as printed on the statement.
"""

from typing import Literal

from pydantic import BaseModel

ColumnName = Literal[
    "date", "posted", "description", "category", "amount", "withdrawal", "deposit", "balance"
]


class Column(BaseModel):
    name: ColumnName
    header: str  # a word in the column's header, as printed; the first match on the page wins


class Layout(BaseModel):
    name: str
    account: Literal["credit_card", "bank_account"]  # balance owed vs balance held
    columns: list[Column]  # either "amount", or "withdrawal" and "deposit"

    language: Literal["fr", "en"]  # language of the month names
    date_order: Literal["day_month", "month_day"]  # "6 mar" vs "jan 6"
    negative: Literal["minus", "parentheses", "none"]  # "-12,34" vs "(12,34 $)"; none = separate columns
    decimal: Literal[",", "."]

    description_wraps: Literal["below", "above"]  # extra description lines below or above the amount row
    dates_repeat: bool  # False when only a day's first transaction shows the date
    skip: list[str] = []  # regexes for lines inside the table that are not part of any description

    # Labels that start a row, as printed. The value is the first amount (or date) after the label.
    # Balances list every label the bank uses, e.g. a different one when the card is in credit.
    period: str  # the row that ends with the statement's end date, which gives the year
    opening_balance: list[str]
    closing_balance: list[str]
    table_ends: list[str]  # rows that end the transaction table on a page


TD_VISA = Layout(
    name="TD Visa",
    account="credit_card",
    columns=[
        Column(name="date", header="DATE"),
        Column(name="posted", header="PASSATION"),
        Column(name="description", header="DESCRIPTION"),
        Column(name="amount", header="MONTANT"),
    ],
    language="fr",
    date_order="day_month",
    negative="minus",
    decimal=",",
    description_wraps="below",
    dates_repeat=True,
    skip=[r"^DEVISE ETRANGERE", r"^@ TAUX DE CHANGE"],
    period="PÉRIODE DE RELEVÉ",
    opening_balance=["SOLDE DU RELEVÉ PRÉCÉDENT"],
    closing_balance=["NOUVEAU SOLDE"],
    table_ends=["Suite", "TOTAL", "NOUVEAU SOLDE"],
)

RBC_VISA = Layout(
    name="RBC Visa",
    account="credit_card",
    columns=[
        Column(name="date", header="DATE"),
        Column(name="posted", header="D'INSCRIPTION"),
        Column(name="description", header="DESCRIPTION"),
        Column(name="amount", header="MONTANT"),
    ],
    language="fr",
    date_order="day_month",
    negative="parentheses",
    decimal=",",
    description_wraps="below",
    dates_repeat=True,
    skip=[r"^\d{20,}$", r"^Devise étrangère"],  # reference number under every purchase
    period="Revelé du",  # sic: the bank's own spelling
    opening_balance=["SOLDE DE COMPTE PRÉCÉDENT"],
    closing_balance=["SOLDE DE COMPTE TOTAL", "SOLDE DE CRÉDIT"],  # the second when in credit
    table_ends=["SOLDE DE COMPTE TOTAL", "SOLDE DE CRÉDIT"],
)

RBC_CHEQUING = Layout(
    name="RBC chequing",
    account="bank_account",
    columns=[
        Column(name="date", header="Date"),
        Column(name="description", header="Description"),
        Column(name="withdrawal", header="Retraits"),
        Column(name="deposit", header="Dépôts"),
        Column(name="balance", header="Solde"),
    ],
    language="fr",
    date_order="day_month",
    negative="none",
    decimal=",",
    description_wraps="above",
    dates_repeat=False,
    skip=[r"^\d+ de \d+$", r"^Solde d'ouverture"],  # page number, opening row inside the table
    period="Du",
    opening_balance=["Votre solde d'ouverture"],
    closing_balance=["Votre solde de clôture"],
    table_ends=["Solde de clôture"],
)

CIBC_MASTERCARD = Layout(
    name="CIBC Mastercard",
    account="credit_card",
    columns=[
        Column(name="date", header="Date"),
        Column(name="posted", header="l’inscr."),  # curly apostrophe, as printed
        Column(name="description", header="Description"),
        Column(name="category", header="Catégories"),  # the bank's own spending category
        Column(name="amount", header="Montant"),
    ],
    language="fr",
    date_order="month_day",
    negative="minus",
    decimal=",",
    description_wraps="below",
    dates_repeat=True,
    skip=[r"^Ý$"],  # bonus-points icon drawn in a symbol font
    period="Opérations",  # "Opérations 17 janvier au 17 février 2026"
    opening_balance=["Solde antérieur"],
    closing_balance=["Solde total"],
    table_ends=["Total pour"],
)

LAYOUTS = [TD_VISA, RBC_VISA, RBC_CHEQUING, CIBC_MASTERCARD]
