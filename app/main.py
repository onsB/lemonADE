import io
from typing import Literal
from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.responses import FileResponse, Response
from openai import APIConnectionError
from pdfplumber.utils.exceptions import PdfminerException
from pydantic import BaseModel

import datetime as dt
from pathlib import Path

from app.agent import run_agent

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
app = FastAPI(title = "LemonADE")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


class Transaction(BaseModel):
    date: dt.date
    description: str
    amount: float
    kind: str
    page: int

class Summary(BaseModel):
    transaction_count: int
    total_spending: float
    opening_balance: float | None
    closing_balance: float | None
    reconciled: bool | None

class ParsedStatement(BaseModel):
    filename: str
    summary: Summary    
    transactions: list[Transaction]


@app.post("/statements/parse", response_model=ParsedStatement)
def parse_uploaded_statement(
    file: UploadFile,
    format: Literal["json", "csv"] = "json"
):
    content = file.file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File size exceeds the maximum limit (10 MB)")
    if not content.startswith(b"%PDF"):          # check the bytes, not the filename
        raise HTTPException(415, "Upload a PDF statement")

    try:
        out = run_agent(io.BytesIO(content))
    except PdfminerException as e:
        raise HTTPException(422, f"Could not read this statement: {e}")
    except APIConnectionError:
        raise HTTPException(503, "LLM server unreachable. Is LM Studio running?")

    if "df" not in out:
        raise HTTPException(422, "Could not read this statement")

    df = out["df"]
    summary = Summary(**out)

    if format == "csv":
        name = (file.filename or "statement").rsplit(".", 1)[0]
        return Response(df.to_csv(index=False, date_format="%Y-%m-%d"), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})

    df = df.assign(date=df["date"].dt.date, posted=df["posted"].dt.date)
    return ParsedStatement(filename=file.filename or "statement.pdf", 
                        summary=summary,
                        transactions=df.to_dict(orient="records"))

def main():
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)

if __name__ == "__main__":
    main()