from io import BytesIO

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def spatial_dataframe() -> pd.DataFrame:
    random = np.random.default_rng(12)
    x_coord = np.tile(np.arange(6, dtype=float), 6)
    y_coord = np.repeat(np.arange(6, dtype=float), 6)
    x1 = random.normal(size=36)
    x2 = random.normal(size=36)
    outcome = 3 + 1.5 * x1 - 0.7 * x2 + 0.15 * x_coord + random.normal(0, 0.2, 36)
    return pd.DataFrame(
        {"x_coord": x_coord, "y_coord": y_coord, "x1": x1, "x2": x2, "outcome": outcome}
    )


def post_spatial(method: str, independent_columns: str = '["x1", "x2"]'):
    dataframe = spatial_dataframe()
    return client.post(
        "/api/spatial/run",
        files={
            "file": (
                "spatial.csv",
                dataframe.to_csv(index=False).encode(),
                "text/csv",
            )
        },
        data={
            "method": method,
            "coordinate_type": "projected",
            "x_column": "x_coord",
            "y_column": "y_coord",
            "dependent_column": "outcome",
            "independent_columns": independent_columns,
            "neighbors": "4",
        },
    )


def test_moran_analysis() -> None:
    response = post_spatial("moran", "[]")
    assert response.status_code == 200
    result = response.json()
    assert result["kind"] == "moran"
    assert result["moran"]["i"] is not None
    assert result["weights"]["neighbors"] == 4
    assert result["diagnostics"]["valid_inference"] is True


@pytest.mark.parametrize("method", ["slm", "sem", "sdm"])
def test_spatial_regressions(method: str) -> None:
    response = post_spatial(method)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["kind"] == "spatial_regression"
    assert result["regression"]["coefficients"]
    assert result["regression"]["metrics"]["aic"] is not None
    assert "max_vif" in result["diagnostics"]
    assert result["residual_moran"]["i"] is not None
    assert len(result["model_selection"]["tests"]) == 5
    assert result["model_selection"]["recommendation"]
    if method in {"slm", "sdm"}:
        impacts = result["regression"]["spatial_impacts"]
        assert [item["term"] for item in impacts] == ["x1", "x2"]
        coefficients = {
            item["term"]: item["estimate"]
            for item in result["regression"]["coefficients"]
        }
        for impact in impacts:
            assert impact["direct"] + impact["indirect"] == pytest.approx(
                impact["total"]
            )
            lagged_x = coefficients.get(f"W_{impact['term']}", 0.0)
            assert impact["total"] == pytest.approx(
                (coefficients[impact["term"]] + lagged_x)
                / (1 - result["regression"]["metrics"]["rho"])
            )
    else:
        assert result["regression"]["spatial_impacts"] == []


def test_gwr_analysis() -> None:
    response = post_spatial("gwr")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["kind"] == "gwr"
    assert result["gwr"]["bandwidth"] >= 5
    assert len(result["gwr"]["coefficient_summaries"]) == 3
    assert len(result["gwr"]["local_preview"]) == 36
    assert "p_value_unadjusted_x1" in result["gwr"]["local_preview"][0]
    assert result["residual_moran"]["p_permutation"] is not None
    assert result["model_selection"]["available"] is True


def test_geographic_coordinate_validation() -> None:
    dataframe = spatial_dataframe()
    dataframe["x_coord"] = 200
    response = client.post(
        "/api/spatial/run",
        files={"file": ("bad.csv", dataframe.to_csv(index=False).encode(), "text/csv")},
        data={
            "method": "moran",
            "coordinate_type": "geographic",
            "x_column": "x_coord",
            "y_column": "y_coord",
            "dependent_column": "outcome",
            "independent_columns": "[]",
            "neighbors": "4",
        },
    )
    assert response.status_code == 400
    assert "Longitude" in response.json()["detail"]


@pytest.mark.parametrize("output_format", ["csv", "xlsx"])
def test_export_full_gwr_results(output_format: str) -> None:
    dataframe = spatial_dataframe()
    response = client.post(
        "/api/spatial/export",
        files={
            "file": (
                "spatial.csv",
                dataframe.to_csv(index=False).encode(),
                "text/csv",
            )
        },
        data={
            "method": "gwr",
            "coordinate_type": "projected",
            "x_column": "x_coord",
            "y_column": "y_coord",
            "dependent_column": "outcome",
            "independent_columns": '["x1", "x2"]',
            "neighbors": "4",
            "output_format": output_format,
        },
    )

    assert response.status_code == 200, response.text
    assert (
        f"spatial-spatial-dataex.{output_format}"
        in response.headers["content-disposition"]
    )
    if output_format == "csv":
        exported = pd.read_csv(BytesIO(response.content))
    else:
        workbook = pd.ExcelFile(BytesIO(response.content))
        assert {
            "summary",
            "diagnostics",
            "coefficient_summary",
            "local_results",
            "residual_moran",
            "model_selection",
        } <= set(workbook.sheet_names)
        exported = pd.read_excel(workbook, sheet_name="local_results")
    assert len(exported) == len(dataframe)
    assert "p_value_unadjusted_x1" in exported.columns


def test_export_slm_includes_impacts_and_diagnostics() -> None:
    dataframe = spatial_dataframe()
    response = client.post(
        "/api/spatial/export",
        files={
            "file": (
                "spatial.csv",
                dataframe.to_csv(index=False).encode(),
                "text/csv",
            )
        },
        data={
            "method": "slm",
            "coordinate_type": "projected",
            "x_column": "x_coord",
            "y_column": "y_coord",
            "dependent_column": "outcome",
            "independent_columns": '["x1", "x2"]',
            "neighbors": "4",
            "output_format": "xlsx",
        },
    )

    assert response.status_code == 200, response.text
    workbook = pd.ExcelFile(BytesIO(response.content))
    assert {"spatial_impacts", "residual_moran", "model_selection"} <= set(
        workbook.sheet_names
    )
    impacts = pd.read_excel(workbook, sheet_name="spatial_impacts")
    assert list(impacts["term"]) == ["x1", "x2"]
