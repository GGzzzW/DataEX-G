import re
from io import BytesIO
from typing import Literal

import pandas as pd

from backend.quality import is_missing

MissingAction = Literal["none", "drop_rows", "extract_rows", "fill_zero"]
ExportFormat = Literal["csv", "xlsx"]
ExportTable = Literal["cleaned", "extracted"]
StandardizationMethod = Literal["none", "min_max", "z_score"]
LINE_BREAK_PATTERN = re.compile(r"[\r\n]+")


class StandardizationError(ValueError):
    pass


def build_missing_mask(dataframe: pd.DataFrame) -> pd.DataFrame:
    return dataframe.map(is_missing)


def clean_text_value(
    value: object,
    *,
    trim_whitespace: bool,
    remove_line_breaks: bool,
) -> object:
    if not isinstance(value, str):
        return value

    cleaned = value.strip() if trim_whitespace else value
    if remove_line_breaks:
        cleaned = LINE_BREAK_PATTERN.sub(" ", cleaned)
    return cleaned


def clean_text_dataframe(
    dataframe: pd.DataFrame,
    *,
    trim_whitespace: bool,
    remove_line_breaks: bool,
) -> tuple[pd.DataFrame, int]:
    changed_cell_count = 0

    def transform(value: object) -> object:
        nonlocal changed_cell_count
        cleaned = clean_text_value(
            value,
            trim_whitespace=trim_whitespace,
            remove_line_breaks=remove_line_breaks,
        )
        if isinstance(value, str) and cleaned != value:
            changed_cell_count += 1
        return cleaned

    return dataframe.map(transform), changed_cell_count


def standardize_dataframe(
    dataframe: pd.DataFrame,
    *,
    method: StandardizationMethod,
    columns: list[str],
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    standardized = dataframe.copy()
    statistics: list[dict[str, object]] = []

    if method == "none":
        return standardized, statistics
    if not columns:
        raise StandardizationError("Select at least one numeric column to standardize.")

    for column in columns:
        if column not in standardized.columns:
            raise StandardizationError(f"Column '{column}' does not exist.")

        original = standardized[column]
        numeric = pd.to_numeric(original, errors="coerce")
        invalid_mask = ~original.map(is_missing) & numeric.isna()
        if invalid_mask.any():
            raise StandardizationError(
                f"Column '{column}' contains non-numeric values and cannot be standardized."
            )

        valid = numeric.dropna()
        if valid.empty:
            raise StandardizationError(
                f"Column '{column}' has no numeric values to standardize."
            )

        minimum = float(valid.min())
        maximum = float(valid.max())
        mean = float(valid.mean())
        standard_deviation = float(valid.std(ddof=0))

        if method == "min_max":
            denominator = maximum - minimum
            transformed = (
                numeric * 0 if denominator == 0 else (numeric - minimum) / denominator
            )
        else:
            transformed = (
                numeric * 0
                if standard_deviation == 0
                else (numeric - mean) / standard_deviation
            )

        standardized[column] = transformed.round(6)
        statistics.append(
            {
                "column": column,
                "minimum": minimum,
                "maximum": maximum,
                "mean": round(mean, 6),
                "standard_deviation": round(standard_deviation, 6),
            }
        )

    return standardized, statistics


def clean_dataframe(
    dataframe: pd.DataFrame,
    *,
    missing_action: MissingAction,
    trim_whitespace: bool,
    remove_line_breaks: bool,
    standardization_method: StandardizationMethod = "none",
    standardization_columns: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    missing_mask = build_missing_mask(dataframe)
    affected_rows = missing_mask.any(axis=1)
    extracted_row_numbers: list[int] = []
    extracted = dataframe.iloc[0:0].copy()
    cleaned = dataframe.copy()

    if missing_action == "drop_rows":
        cleaned = dataframe.loc[~affected_rows].copy()
    elif missing_action == "extract_rows":
        extracted = dataframe.loc[affected_rows].copy()
        extracted_row_numbers = [
            position + 1
            for position, has_missing in enumerate(affected_rows.tolist())
            if has_missing
        ]
        cleaned = dataframe.loc[~affected_rows].copy()
    elif missing_action == "fill_zero":
        cleaned = dataframe.mask(missing_mask, 0)

    text_changed_cell_count = 0
    if trim_whitespace or remove_line_breaks:
        cleaned, cleaned_change_count = clean_text_dataframe(
            cleaned,
            trim_whitespace=trim_whitespace,
            remove_line_breaks=remove_line_breaks,
        )
        extracted, extracted_change_count = clean_text_dataframe(
            extracted,
            trim_whitespace=trim_whitespace,
            remove_line_breaks=remove_line_breaks,
        )
        text_changed_cell_count = cleaned_change_count + extracted_change_count

    cleaned = cleaned.reset_index(drop=True)
    extracted = extracted.reset_index(drop=True)
    cleaned, standardization_statistics = standardize_dataframe(
        cleaned,
        method=standardization_method,
        columns=standardization_columns or [],
    )

    return (
        cleaned,
        extracted,
        {
            "missing_action": missing_action,
            "missing_affected_row_count": int(affected_rows.sum()),
            "text_changed_cell_count": text_changed_cell_count,
            "extracted_row_numbers": extracted_row_numbers,
            "standardization_method": standardization_method,
            "standardized_columns": standardization_columns or [],
            "standardization_statistics": standardization_statistics,
        },
    )


def export_csv(dataframe: pd.DataFrame) -> bytes:
    return dataframe.to_csv(index=False, lineterminator="\n").encode("utf-8-sig")


def export_xlsx(cleaned: pd.DataFrame, extracted: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        cleaned.to_excel(writer, sheet_name="cleaned_data", index=False)
        if not extracted.empty:
            extracted.to_excel(writer, sheet_name="missing_data", index=False)
    return output.getvalue()
