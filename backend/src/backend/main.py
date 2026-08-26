import json
from io import BytesIO
from pathlib import Path
from typing import Annotated
from zipfile import BadZipFile

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status

from backend.cleaning import MissingAction, clean_dataframe
from backend.quality import build_quality_report

app = FastAPI(
    title="Data Analysis Desktop API",
    version="0.1.0",
)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
SUPPORTED_FILE_TYPES = {".csv", ".xlsx"}


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


def read_dataframe(filename: str, content: bytes) -> pd.DataFrame:
    suffix = Path(filename).suffix.lower()

    try:
        if suffix == ".csv":
            for encoding in ("utf-8-sig", "gb18030"):
                try:
                    return pd.read_csv(BytesIO(content), encoding=encoding)
                except UnicodeDecodeError:
                    continue

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CSV encoding is not supported. Use UTF-8 or GB18030.",
            )

        return pd.read_excel(BytesIO(content), engine="openpyxl")
    except (BadZipFile, KeyError, ValueError, pd.errors.ParserError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file could not be parsed.",
        ) from exc


async def load_uploaded_dataframe(file: UploadFile) -> tuple[str, pd.DataFrame]:
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()

    if suffix not in SUPPORTED_FILE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV and XLSX files are supported.",
        )

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    await file.close()

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is empty.",
        )

    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="The uploaded file exceeds the 20 MB limit.",
        )

    return filename, read_dataframe(filename, content)


def dataframe_preview(dataframe: pd.DataFrame) -> list[dict[str, object]]:
    return json.loads(dataframe.head(100).to_json(orient="records", date_format="iso"))


@app.post("/api/files/preview")
async def preview_file(
    file: Annotated[UploadFile, File()],
) -> dict[str, object]:
    filename, dataframe = await load_uploaded_dataframe(file)

    return {
        "filename": filename,
        "row_count": int(dataframe.shape[0]),
        "column_count": int(dataframe.shape[1]),
        "columns": [str(column) for column in dataframe.columns],
        "preview": dataframe_preview(dataframe),
        "quality": build_quality_report(dataframe),
    }


@app.post("/api/files/clean/preview")
async def preview_cleaning(
    file: Annotated[UploadFile, File()],
    missing_action: Annotated[MissingAction, Form()] = "none",
    trim_whitespace: Annotated[bool, Form()] = False,
    remove_line_breaks: Annotated[bool, Form()] = False,
) -> dict[str, object]:
    filename, dataframe = await load_uploaded_dataframe(file)
    cleaned, extracted, summary = clean_dataframe(
        dataframe,
        missing_action=missing_action,
        trim_whitespace=trim_whitespace,
        remove_line_breaks=remove_line_breaks,
    )

    return {
        "filename": filename,
        "original_row_count": int(dataframe.shape[0]),
        "cleaned_row_count": int(cleaned.shape[0]),
        "extracted_row_count": int(extracted.shape[0]),
        "columns": [str(column) for column in dataframe.columns],
        "cleaned_preview": dataframe_preview(cleaned),
        "extracted_preview": dataframe_preview(extracted),
        "cleaned_quality": build_quality_report(cleaned),
        "summary": summary,
    }
