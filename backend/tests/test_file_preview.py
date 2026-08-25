from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_preview_csv_file() -> None:
    response = client.post(
        "/api/files/preview",
        files={
            "file": (
                "people.csv",
                b"name,age\nAlice,20\nBob,\n",
                "text/csv",
            )
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["filename"] == "people.csv"
    assert result["row_count"] == 2
    assert result["column_count"] == 2
    assert result["columns"] == ["name", "age"]
    assert result["preview"] == [
        {"name": "Alice", "age": 20.0},
        {"name": "Bob", "age": None},
    ]
    assert result["quality"]["missing_cell_count"] == 1


def test_preview_rejects_unsupported_file_type() -> None:
    response = client.post(
        "/api/files/preview",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Only CSV and XLSX files are supported."}


def test_preview_reports_duplicates_missing_values_and_mixed_types() -> None:
    response = client.post(
        "/api/files/preview",
        files={
            "file": (
                "quality.csv",
                b"name,age\nAlice,20\nBob,unknown\nBob,unknown\n, \n",
                "text/csv",
            )
        },
    )

    assert response.status_code == 200
    quality = response.json()["quality"]
    assert quality["missing_cell_count"] == 2
    assert quality["duplicate_row_count"] == 1
    assert quality["duplicate_row_numbers"] == [2, 3]

    age_report = quality["columns"][1]
    assert age_report["missing_count"] == 1
    assert age_report["mixed_types"] is True
    assert age_report["detected_types"] == [
        {"type": "text", "count": 2, "examples": ["unknown", "unknown"]},
        {"type": "number", "count": 1, "examples": ["20"]},
    ]
