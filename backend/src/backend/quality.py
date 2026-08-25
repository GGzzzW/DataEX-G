import re
from collections import Counter, defaultdict
from datetime import date, datetime
from numbers import Number

import pandas as pd

NUMBER_PATTERN = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
DATE_PATTERNS = (
    re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:[ T].*)?$"),
    re.compile(r"^\d{1,2}[-/]\d{1,2}[-/]\d{4}(?:[ T].*)?$"),
    re.compile(r"^\d{4}年\d{1,2}月\d{1,2}日(?: .*)?$"),
)


def is_missing(value: object) -> bool:
    if isinstance(value, str):
        return not value.strip()
    return bool(pd.isna(value))


def detect_value_type(value: object) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, Number):
        return "number"
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return "datetime"
    if not isinstance(value, str):
        return "text"

    normalized = value.strip()
    if normalized.lower() in {"true", "false"}:
        return "boolean"
    if NUMBER_PATTERN.fullmatch(normalized):
        return "number"
    if any(pattern.fullmatch(normalized) for pattern in DATE_PATTERNS):
        return "datetime"
    return "text"


def analyze_column(name: object, series: pd.Series) -> dict[str, object]:
    type_counts: Counter[str] = Counter()
    examples: defaultdict[str, list[str]] = defaultdict(list)
    missing_count = 0

    for value in series.tolist():
        if is_missing(value):
            missing_count += 1
            continue

        value_type = detect_value_type(value)
        type_counts[value_type] += 1
        if len(examples[value_type]) < 3:
            examples[value_type].append(str(value))

    detected_types = [
        {
            "type": value_type,
            "count": count,
            "examples": examples[value_type],
        }
        for value_type, count in sorted(
            type_counts.items(), key=lambda item: (-item[1], item[0])
        )
    ]
    row_count = len(series)

    return {
        "name": str(name),
        "pandas_dtype": str(series.dtype),
        "missing_count": missing_count,
        "missing_ratio": round(missing_count / row_count, 4) if row_count else 0.0,
        "detected_types": detected_types,
        "mixed_types": len(type_counts) > 1,
    }


def build_quality_report(dataframe: pd.DataFrame) -> dict[str, object]:
    columns = [
        analyze_column(name, dataframe.iloc[:, position])
        for position, name in enumerate(dataframe.columns)
    ]
    duplicate_mask = dataframe.duplicated(keep=False)

    return {
        "missing_cell_count": sum(int(column["missing_count"]) for column in columns),
        "duplicate_row_count": int(dataframe.duplicated().sum()),
        "duplicate_row_numbers": [
            position + 1
            for position, is_duplicate in enumerate(duplicate_mask.tolist())
            if is_duplicate
        ],
        "columns": columns,
    }
