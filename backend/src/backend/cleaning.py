import re
from typing import Literal

import pandas as pd

from backend.quality import is_missing

MissingAction = Literal["none", "drop_rows", "extract_rows", "fill_zero"]
LINE_BREAK_PATTERN = re.compile(r"[\r\n]+")


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


def clean_dataframe(
    dataframe: pd.DataFrame,
    *,
    missing_action: MissingAction,
    trim_whitespace: bool,
    remove_line_breaks: bool,
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

    return (
        cleaned,
        extracted,
        {
            "missing_action": missing_action,
            "missing_affected_row_count": int(affected_rows.sum()),
            "text_changed_cell_count": text_changed_cell_count,
            "extracted_row_numbers": extracted_row_numbers,
        },
    )
