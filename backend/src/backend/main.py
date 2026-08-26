import json
from io import BytesIO
from pathlib import Path
from typing import Annotated
from urllib.parse import quote
from zipfile import BadZipFile

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response

from backend.cleaning import (
    ExportFormat,
    ExportTable,
    MissingAction,
    StandardizationError,
    StandardizationMethod,
    clean_dataframe,
    export_csv,
    export_xlsx,
)
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


def build_download_headers(filename: str) -> dict[str, str]:
    fallback = "data-dataex" + Path(filename).suffix.lower()
    encoded = quote(filename)
    return {
        "Content-Disposition": (
            f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{encoded}"
        )
    }


def parse_standardization_columns(raw_columns: str) -> list[str]:
    try:
        columns = json.loads(raw_columns)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Standardization columns must be a JSON array.",
        ) from exc

    if not isinstance(columns, list) or not all(
        isinstance(column, str) for column in columns
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Standardization columns must be a JSON array of column names.",
        )
    return columns


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
    standardization_method: Annotated[StandardizationMethod, Form()] = "none",
    standardization_columns: Annotated[str, Form()] = "[]",
) -> dict[str, object]:
    filename, dataframe = await load_uploaded_dataframe(file)
    try:
        cleaned, extracted, summary = clean_dataframe(
            dataframe,
            missing_action=missing_action,
            trim_whitespace=trim_whitespace,
            remove_line_breaks=remove_line_breaks,
            standardization_method=standardization_method,
            standardization_columns=parse_standardization_columns(
                standardization_columns
            ),
        )
    except StandardizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

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


@app.post("/api/files/clean/export")
async def export_cleaning(
    file: Annotated[UploadFile, File()],
    missing_action: Annotated[MissingAction, Form()] = "none",
    trim_whitespace: Annotated[bool, Form()] = False,
    remove_line_breaks: Annotated[bool, Form()] = False,
    output_format: Annotated[ExportFormat, Form()] = "xlsx",
    table: Annotated[ExportTable, Form()] = "cleaned",
    standardization_method: Annotated[StandardizationMethod, Form()] = "none",
    standardization_columns: Annotated[str, Form()] = "[]",
) -> Response:
    filename, dataframe = await load_uploaded_dataframe(file)
    try:
        cleaned, extracted, _ = clean_dataframe(
            dataframe,
            missing_action=missing_action,
            trim_whitespace=trim_whitespace,
            remove_line_breaks=remove_line_breaks,
            standardization_method=standardization_method,
            standardization_columns=parse_standardization_columns(
                standardization_columns
            ),
        )
    except StandardizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    stem = Path(filename).stem

    if output_format == "xlsx":
        download_name = f"{stem}-dataex.xlsx"
        return Response(
            content=export_xlsx(cleaned, extracted),
            media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            headers=build_download_headers(download_name),
        )

    selected = cleaned if table == "cleaned" else extracted
    qualifier = "" if table == "cleaned" else "-empty"
    download_name = f"{stem}{qualifier}-dataex.csv"
    return Response(
        content=export_csv(selected),
        media_type="text/csv; charset=utf-8",
        headers=build_download_headers(download_name),
    )
