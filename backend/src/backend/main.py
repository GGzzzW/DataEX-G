import json
from io import BytesIO
from pathlib import Path
from typing import Annotated
from zipfile import BadZipFile

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile, status

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


@app.post("/api/files/preview")
async def preview_file(
    file: Annotated[UploadFile, File()],
) -> dict[str, object]:
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

    dataframe = read_dataframe(filename, content)
    preview = json.loads(
        dataframe.head(100).to_json(orient="records", date_format="iso")
    )

    return {
        "filename": filename,
        "row_count": int(dataframe.shape[0]),
        "column_count": int(dataframe.shape[1]),
        "columns": [str(column) for column in dataframe.columns],
        "preview": preview,
        "quality": build_quality_report(dataframe),
    }
