import io
from typing import Literal
from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from app.parser import parse_statement, StatementParseError

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
app = FastAPI(title = "LemonADE")

class Transaction(BaseModel):
    date: str
    description: str
    amount: float
    kind: str
    page: int

class Summary(BaseModel):
    transaction_count: int
    total_spending: float
    opening_balance: float
    closing_balance: float | None
    total_spending: float | None
    reconciled: bool | None

class ParsedStatement(BaseModel):
    filename: str
    summary: Summary    
    transactions: list[Transaction]


@app.post("/statements/parse", response_model=ParsedStatement)
async def parse_uploaded_statement(
    file: UploadFile,
    expenses_only: bool = False,
    format: Literal["json", "csv"] = "json"
):
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File size exceeds the maximum limit (10 MB)")
    if not content.startswith(b"%PDF"):          # check the bytes, not the filename
        raise HTTPException(415, "Upload a PDF statement")

    try:
        df, summary = parse_statement(io.BytesIO(content))
    except StatementParseError as e:
        raise HTTPException(422, str(e))

    if format == "csv":
        name = (file.filename or "statement").rsplit(".", 1)[0]
        return Response(df.to_csv(index=False, date_format="%Y-%m-%d"), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})

    df = df.assign(date=df["date"].dt.date, posted=df["posted"].dt.date)
    return ParsedStatement(filenam=file.filename or "statement.pdf", 
                        summary=Summary(**summary),
                        transactions=df.to_dict(orient="records"))

def main():
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)

if __name__ == "__main__":
    main()