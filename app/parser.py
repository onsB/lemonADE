import pathlib
import re
import pdfplumber
import pandas as pd

class StatementParseError(ValueError):
    """The file is not a statement this parser understands."""

def parse_statement(source:pathlib.Path):
    """
    Parse a statement from a pdf file.
    """
    MONTHS = {"jan": 1, "fév": 2, "mar": 3, "avr": 4, "mai": 5, "juin": 6,
            "juil": 7, "aoû": 8, "sep": 9, "oct": 10, "nov": 11, "déc": 12}
    DATE = r"\d{1,2} [a-zéû]{3,4}"
    AMOUNT = r"-?\d{1,3}(?: \d{3})*,\d{2}"
    ROW = re.compile(rf"^(?P<date>{DATE})\s+(?P<posted>{DATE})\s+(?P<desc>.+?)\s+(?P<amount>{AMOUNT})(?: ?\$)?$")
    CONTINUATION = re.compile(r"[A-Z][A-Z \-]{2,25}")       # wrapped description, e.g. "MONTREAL"
    TABLE_END = re.compile(r"^(Sui|TOTAL|NOUVEAU SOLDE)")  # "Suite" (cropped) / totals end the table

    def to_amount(s: str) -> float:
        return float(s.replace("\xa0", "").replace(" ", "").replace(",", "."))

    rows, full_text = [], ""
    with pdfplumber.open(source) as pdf:
        for page in pdf.pages:
            page = page.filter(lambda o: o.get("upright", True))  # drop rotated margin text
            full_text += (page.extract_text(x_tolerance=1) or "") + "\n"
            hdr = page.search("MONTANT")
            if not hdr:
                continue  # no transaction table on this page
            # keep only the transaction column, below the header (drops the side panel)
            col = page.crop((0, hdr[0]["bottom"], hdr[0]["x1"] + 15, page.height))
            after_row = False  # a wrapped description can only directly follow a transaction
            for line in (col.extract_text(x_tolerance=1) or "").splitlines():
                line = line.replace("\xa0", " ").strip()
                if TABLE_END.match(line):
                    break
                if m := ROW.match(line):
                    rows.append(m.groupdict() | {"page": page.page_number})
                    after_row = True
                elif after_row and CONTINUATION.fullmatch(line):
                    rows[-1]["desc"] += " " + line
                    after_row = False
                else:
                    after_row = False

    # dates have no year: take it from "PÉRIODE DE RELEVÉ : du 07 jan 2026 au 06 fév 2026"
    period = re.search(rf"du ({DATE}) (\d{{4}}) au ({DATE}) (\d{{4}})", full_text)
    if not period or not rows:
        raise StatementParseError("No statement transaction table found in this PDF")
    end_month, end_year = MONTHS[period.group(3).split()[1]], int(period.group(4))

    def to_date(s: str) -> pd.Timestamp:
        day, mon = s.split()
        month = MONTHS[mon]
        year = end_year - 1 if month > end_month else end_year  # e.g. "28 déc" on a January statement
        return pd.Timestamp(year, month, int(day))

    df = pd.DataFrame(rows)
    df["date"] = df["date"].map(to_date)
    df["posted"] = df["posted"].map(to_date)
    df["amount"] = df["amount"].map(to_amount)
    df["kind"] = "purchase"
    df.loc[df["desc"].str.contains("PAIEMENT"), "kind"] = "payment"
    df.loc[df["desc"].str.contains("PRIME"), "kind"] = "reward"
    df.loc[df["desc"].str.contains("FRAIS"), "kind"] = "fee"
    df = df.rename(columns={"desc": "description"})[["date", "posted", "description", "amount", "kind", "page"]]

    # reconcile: previous balance + transactions must equal the new balance
    opening = to_amount(re.search(rf"SOLDE DU RELEVÉ PRÉCÉDENT ({AMOUNT})", full_text).group(1))
    closing = to_amount(re.search(rf"NOUVEAU SOLDE ({AMOUNT})", full_text).group(1))
    expenses = df[df["kind"].isin(["purchase", "fee"])]
    return(df, opening, closing, expenses["amount"].sum())
