"""FastAPI application exposing the GS1 element-string parser."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .gs1 import GS1ParseError, parse

app = FastAPI(
    title="GS1 Element String Parser",
    version="1.2.0",
    description=(
        "Parses GS1 input into structured, ordered AI elements. Accepts raw "
        "scan strings (FNC1 / ASCII 29 separated) and GS1 Digital Link URIs "
        "(http/https, AI/value pairs in path and query string). Supports AI "
        "01 (GTIN), 10 (batch/lot), 17 (expiry date), 21 (serial number) and "
        "the weight-AI family 310n (net weight, kg) and 320n (net weight, lb), "
        "where n is the number of implied decimal places."
    ),
)


class ParseRequest(BaseModel):
    data: str = Field(
        ...,
        title="Raw scan string or GS1 Digital Link URI",
        description=(
            "Either a raw GS1 element string as scanned (variable-length "
            "fields separated by ASCII 29, encoded in JSON as \u001d), or a "
            "GS1 Digital Link URI beginning with http:// or https://. "
            "Digital Link values are percent-decoded as UTF-8; path segments "
            "must form AI/value pairs; each AI may appear only once across "
            "path and query string. Weight identifiers 310n (kg) and 320n "
            "(lb) take n (0-9) implied decimal places and a fixed 6-digit "
            "value; the response adds decimal_value and unit for them."
        ),
        examples=[
            "01095011015300031725013110ABC12321SN0001",
            "https://id.gs1.org/01/09501101530003/17/250131?10=ABC123&21=SN0001",
            "01095011015300033102001234",
            "https://id.gs1.org/01/09501101530003/3201/029000",
        ],
    )


class Element(BaseModel):
    ai: str = Field(description="Application identifier, e.g. '01'")
    name: str = Field(description="Short element name, e.g. 'GTIN'")
    value: str = Field(description="Field value without AI and separators")
    offset: int = Field(description="Byte offset of the AI within the input")
    decimal_value: float | None = Field(
        default=None,
        description=(
            "Weight value with the n implied decimal places applied "
            "(310n = kg, 320n = lb); absent for other AIs"
        ),
    )
    unit: str | None = Field(
        default=None,
        description="Measurement unit ('kg' for 310n, 'lb' for 320n); absent for other AIs",
    )


class ParseResponse(BaseModel):
    elements: list[Element]


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/parse", response_model=ParseResponse, response_model_exclude_none=True)
def parse_scan(req: ParseRequest) -> ParseResponse:
    try:
        elements = parse(req.data)
    except GS1ParseError as exc:
        raise HTTPException(status_code=422, detail=exc.to_dict()) from exc
    return ParseResponse(elements=[Element(**vars(e)) for e in elements])
