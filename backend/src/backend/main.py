import json
from io import BytesIO
from pathlib import Path
from typing import Annotated
from urllib.parse import quote
from zipfile import BadZipFile

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from backend.analysis import AnalysisError, AnalysisMethod, run_analysis
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
from backend.gwrf import (
    GwrfError,
    GwrfFitMethod,
    optimize_gwrf_bandwidth,
    optimize_gwrf_parameters,
    run_gwrf,
)
from backend.quality import build_quality_report
from backend.reporting import (
    export_analysis_csv,
    export_analysis_xlsx,
    export_gwrf_csv,
    export_gwrf_xlsx,
    export_spatial_csv,
    export_spatial_xlsx,
)
from backend.resources import frontend_directory
from backend.spatial import (
    CoordinateType,
    SpatialAnalysisError,
    SpatialMethod,
    run_spatial_analysis,
)

app = FastAPI(
    title="Data Analysis Desktop API",
    version="1.0.0",
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


def parse_analysis_columns(raw_columns: str) -> list[str]:
    try:
        columns = json.loads(raw_columns)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Independent variables must be a JSON array.",
        ) from exc

    if not isinstance(columns, list) or not all(
        isinstance(column, str) for column in columns
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Independent variables must be a JSON array of column names.",
        )
    return columns


def parse_bandwidth_candidates(raw_candidates: str) -> list[int]:
    try:
        candidates = json.loads(raw_candidates)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="候选带宽必须是 JSON 整数数组。",
        ) from exc
    if not isinstance(candidates, list) or not all(
        isinstance(candidate, int) and not isinstance(candidate, bool)
        for candidate in candidates
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="候选带宽必须是 JSON 整数数组。",
        )
    return candidates


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


@app.post("/api/analysis/run")
async def analyze_file(
    file: Annotated[UploadFile, File()],
    method: Annotated[AnalysisMethod, Form()],
    dependent_column: Annotated[str, Form()],
    independent_columns: Annotated[str, Form()],
) -> dict[str, object]:
    _, dataframe = await load_uploaded_dataframe(file)
    try:
        return run_analysis(
            dataframe,
            method=method,
            dependent_column=dependent_column,
            independent_columns=parse_analysis_columns(independent_columns),
        )
    except AnalysisError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@app.post("/api/analysis/export")
async def export_analysis(
    file: Annotated[UploadFile, File()],
    method: Annotated[AnalysisMethod, Form()],
    dependent_column: Annotated[str, Form()],
    independent_columns: Annotated[str, Form()],
    output_format: Annotated[ExportFormat, Form()] = "xlsx",
) -> Response:
    filename, dataframe = await load_uploaded_dataframe(file)
    try:
        result = run_analysis(
            dataframe,
            method=method,
            dependent_column=dependent_column,
            independent_columns=parse_analysis_columns(independent_columns),
        )
    except AnalysisError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    stem = Path(filename).stem
    download_name = f"{stem}-analysis-dataex.{output_format}"
    if output_format == "xlsx":
        content = export_analysis_xlsx(result)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        content = export_analysis_csv(result)
        media_type = "text/csv; charset=utf-8"
    return Response(
        content=content,
        media_type=media_type,
        headers=build_download_headers(download_name),
    )


@app.post("/api/spatial/run")
async def analyze_spatial_file(
    file: Annotated[UploadFile, File()],
    method: Annotated[SpatialMethod, Form()],
    coordinate_type: Annotated[CoordinateType, Form()],
    x_column: Annotated[str, Form()],
    y_column: Annotated[str, Form()],
    dependent_column: Annotated[str, Form()],
    independent_columns: Annotated[str, Form()] = "[]",
    neighbors: Annotated[int, Form()] = 8,
) -> dict[str, object]:
    _, dataframe = await load_uploaded_dataframe(file)
    try:
        return run_spatial_analysis(
            dataframe,
            method=method,
            coordinate_type=coordinate_type,
            x_column=x_column,
            y_column=y_column,
            dependent_column=dependent_column,
            independent_columns=parse_analysis_columns(independent_columns),
            neighbors=neighbors,
        )
    except SpatialAnalysisError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@app.post("/api/spatial/export")
async def export_spatial_analysis(
    file: Annotated[UploadFile, File()],
    method: Annotated[SpatialMethod, Form()],
    coordinate_type: Annotated[CoordinateType, Form()],
    x_column: Annotated[str, Form()],
    y_column: Annotated[str, Form()],
    dependent_column: Annotated[str, Form()],
    independent_columns: Annotated[str, Form()] = "[]",
    neighbors: Annotated[int, Form()] = 8,
    output_format: Annotated[ExportFormat, Form()] = "xlsx",
) -> Response:
    filename, dataframe = await load_uploaded_dataframe(file)
    try:
        result = run_spatial_analysis(
            dataframe,
            method=method,
            coordinate_type=coordinate_type,
            x_column=x_column,
            y_column=y_column,
            dependent_column=dependent_column,
            independent_columns=parse_analysis_columns(independent_columns),
            neighbors=neighbors,
            include_full_local_results=True,
        )
    except SpatialAnalysisError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    stem = Path(filename).stem
    download_name = f"{stem}-spatial-dataex.{output_format}"
    if output_format == "xlsx":
        content = export_spatial_xlsx(result)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        content = export_spatial_csv(result)
        media_type = "text/csv; charset=utf-8"
    return Response(
        content=content,
        media_type=media_type,
        headers=build_download_headers(download_name),
    )


@app.post("/api/gwrf/optimize-parameters")
async def optimize_gwrf_file_parameters(
    file: Annotated[UploadFile, File()],
    dependent_column: Annotated[str, Form()],
    independent_columns: Annotated[str, Form()],
) -> dict[str, object]:
    _, dataframe = await load_uploaded_dataframe(file)
    try:
        return optimize_gwrf_parameters(
            dataframe,
            dependent_column=dependent_column,
            independent_columns=parse_analysis_columns(independent_columns),
        )
    except GwrfError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@app.post("/api/gwrf/optimize-bandwidth")
async def optimize_gwrf_file_bandwidth(
    file: Annotated[UploadFile, File()],
    coordinate_type: Annotated[CoordinateType, Form()],
    x_column: Annotated[str, Form()],
    y_column: Annotated[str, Form()],
    dependent_column: Annotated[str, Form()],
    independent_columns: Annotated[str, Form()],
    bandwidth_candidates: Annotated[str, Form()],
    n_estimators: Annotated[int, Form()] = 200,
    max_depth: Annotated[int | None, Form()] = 10,
    min_samples_split: Annotated[int, Form()] = 5,
) -> dict[str, object]:
    _, dataframe = await load_uploaded_dataframe(file)
    try:
        return optimize_gwrf_bandwidth(
            dataframe,
            coordinate_type=coordinate_type,
            x_column=x_column,
            y_column=y_column,
            dependent_column=dependent_column,
            independent_columns=parse_analysis_columns(independent_columns),
            bandwidth_candidates=parse_bandwidth_candidates(bandwidth_candidates),
            n_estimators=n_estimators,
            max_depth=None if max_depth == 0 else max_depth,
            min_samples_split=min_samples_split,
        )
    except GwrfError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@app.post("/api/gwrf/run")
async def analyze_gwrf_file(
    file: Annotated[UploadFile, File()],
    coordinate_type: Annotated[CoordinateType, Form()],
    x_column: Annotated[str, Form()],
    y_column: Annotated[str, Form()],
    dependent_column: Annotated[str, Form()],
    independent_columns: Annotated[str, Form()],
    bandwidth: Annotated[int, Form()],
    fit_method: Annotated[GwrfFitMethod, Form()] = "in_sample",
    n_estimators: Annotated[int, Form()] = 200,
    max_depth: Annotated[int | None, Form()] = 10,
    min_samples_split: Annotated[int, Form()] = 5,
    optimize_parameters: Annotated[bool, Form()] = False,
    optimize_bandwidth: Annotated[bool, Form()] = False,
    bandwidth_candidates: Annotated[str, Form()] = "[]",
    calculate_shap: Annotated[bool, Form()] = False,
    calculate_shap_interactions: Annotated[bool, Form()] = False,
    shap_interaction_columns: Annotated[str, Form()] = "[]",
) -> dict[str, object]:
    _, dataframe = await load_uploaded_dataframe(file)
    try:
        return run_gwrf(
            dataframe,
            coordinate_type=coordinate_type,
            x_column=x_column,
            y_column=y_column,
            dependent_column=dependent_column,
            independent_columns=parse_analysis_columns(independent_columns),
            bandwidth=bandwidth,
            fit_method=fit_method,
            n_estimators=n_estimators,
            max_depth=None if max_depth == 0 else max_depth,
            min_samples_split=min_samples_split,
            optimize_parameters=optimize_parameters,
            optimize_bandwidth=optimize_bandwidth,
            bandwidth_candidates=parse_bandwidth_candidates(bandwidth_candidates),
            calculate_shap=calculate_shap,
            calculate_shap_interactions=calculate_shap_interactions,
            shap_interaction_columns=parse_analysis_columns(shap_interaction_columns),
        )
    except GwrfError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@app.post("/api/gwrf/export")
async def export_gwrf_analysis(
    file: Annotated[UploadFile, File()],
    coordinate_type: Annotated[CoordinateType, Form()],
    x_column: Annotated[str, Form()],
    y_column: Annotated[str, Form()],
    dependent_column: Annotated[str, Form()],
    independent_columns: Annotated[str, Form()],
    bandwidth: Annotated[int, Form()],
    fit_method: Annotated[GwrfFitMethod, Form()] = "in_sample",
    n_estimators: Annotated[int, Form()] = 200,
    max_depth: Annotated[int | None, Form()] = 10,
    min_samples_split: Annotated[int, Form()] = 5,
    optimize_parameters: Annotated[bool, Form()] = False,
    optimize_bandwidth: Annotated[bool, Form()] = False,
    bandwidth_candidates: Annotated[str, Form()] = "[]",
    calculate_shap: Annotated[bool, Form()] = False,
    calculate_shap_interactions: Annotated[bool, Form()] = False,
    shap_interaction_columns: Annotated[str, Form()] = "[]",
    output_format: Annotated[ExportFormat, Form()] = "xlsx",
) -> Response:
    filename, dataframe = await load_uploaded_dataframe(file)
    try:
        result = run_gwrf(
            dataframe,
            coordinate_type=coordinate_type,
            x_column=x_column,
            y_column=y_column,
            dependent_column=dependent_column,
            independent_columns=parse_analysis_columns(independent_columns),
            bandwidth=bandwidth,
            fit_method=fit_method,
            n_estimators=n_estimators,
            max_depth=None if max_depth == 0 else max_depth,
            min_samples_split=min_samples_split,
            optimize_parameters=optimize_parameters,
            optimize_bandwidth=optimize_bandwidth,
            bandwidth_candidates=parse_bandwidth_candidates(bandwidth_candidates),
            calculate_shap=calculate_shap,
            calculate_shap_interactions=calculate_shap_interactions,
            shap_interaction_columns=parse_analysis_columns(shap_interaction_columns),
            include_full_local_results=True,
        )
    except GwrfError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    stem = Path(filename).stem
    download_name = f"{stem}-gwrf-dataex.{output_format}"
    if output_format == "xlsx":
        content = export_gwrf_xlsx(result)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        content = export_gwrf_csv(result)
        media_type = "text/csv; charset=utf-8"
    return Response(
        content=content,
        media_type=media_type,
        headers=build_download_headers(download_name),
    )


STATIC_DIRECTORY = frontend_directory()
if STATIC_DIRECTORY.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIRECTORY, html=True), name="frontend")
