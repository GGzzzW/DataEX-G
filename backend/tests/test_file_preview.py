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
    assert response.json() == {
        "filename": "people.csv",
        "row_count": 2,
        "column_count": 2,
        "columns": ["name", "age"],
        "preview": [
            {"name": "Alice", "age": 20.0},
            {"name": "Bob", "age": None},
        ],
    }


def test_preview_rejects_unsupported_file_type() -> None:
    response = client.post(
        "/api/files/preview",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Only CSV and XLSX files are supported."}
