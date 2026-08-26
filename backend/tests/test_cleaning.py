from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)

CLEANING_CSV = b'name,note,score\n" Alice ","hello\nworld",\nBob," ok ",10\n'


def test_quality_report_detects_text_issues() -> None:
    response = client.post(
        "/api/files/preview",
        files={"file": ("issues.csv", CLEANING_CSV, "text/csv")},
    )

    assert response.status_code == 200
    quality = response.json()["quality"]
    assert quality["whitespace_cell_count"] == 2
    assert quality["line_break_cell_count"] == 1

    name_report = quality["columns"][0]
    assert name_report["whitespace_row_numbers"] == [1]
    note_report = quality["columns"][1]
    assert note_report["whitespace_row_numbers"] == [2]
    assert note_report["line_break_row_numbers"] == [1]


def test_cleaning_can_extract_missing_rows_and_clean_text() -> None:
    response = client.post(
        "/api/files/clean/preview",
        files={"file": ("issues.csv", CLEANING_CSV, "text/csv")},
        data={
            "missing_action": "extract_rows",
            "trim_whitespace": "true",
            "remove_line_breaks": "true",
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["original_row_count"] == 2
    assert result["cleaned_row_count"] == 1
    assert result["extracted_row_count"] == 1
    assert result["cleaned_preview"] == [{"name": "Bob", "note": "ok", "score": 10.0}]
    assert result["extracted_preview"] == [
        {"name": "Alice", "note": "hello world", "score": None}
    ]
    assert result["summary"] == {
        "missing_action": "extract_rows",
        "missing_affected_row_count": 1,
        "text_changed_cell_count": 3,
        "extracted_row_numbers": [1],
    }


def test_cleaning_can_fill_missing_values_with_zero() -> None:
    response = client.post(
        "/api/files/clean/preview",
        files={"file": ("values.csv", b"name,score\nAlice,\n", "text/csv")},
        data={"missing_action": "fill_zero"},
    )

    assert response.status_code == 200
    assert response.json()["cleaned_preview"] == [{"name": "Alice", "score": 0.0}]
