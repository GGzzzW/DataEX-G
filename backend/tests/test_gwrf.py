from io import BytesIO

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def gwrf_dataframe() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    rows = 14
    x1 = np.linspace(1, 7, rows)
    x2 = rng.normal(3, 0.8, rows)
    return pd.DataFrame(
        {
            "lon": np.linspace(116.1, 116.8, rows),
            "lat": np.linspace(39.7, 40.2, rows) + rng.normal(0, 0.02, rows),
            "x1": x1,
            "x2": x2,
            "target": 2.5 * x1 - 1.2 * x2 + rng.normal(0, 0.2, rows),
        }
    )


def post_gwrf(
    fit_method: str = "in_sample",
    endpoint: str = "/api/gwrf/run",
    *,
    optimize_parameters: bool = False,
    calculate_shap: bool = True,
    calculate_shap_interactions: bool = False,
):
    dataframe = gwrf_dataframe()
    return client.post(
        endpoint,
        files={"file": ("gwrf.csv", dataframe.to_csv(index=False), "text/csv")},
        data={
            "coordinate_type": "geographic",
            "x_column": "lon",
            "y_column": "lat",
            "dependent_column": "target",
            "independent_columns": '["x1", "x2"]',
            "bandwidth": "8",
            "fit_method": fit_method,
            "n_estimators": "10",
            "max_depth": "5",
            "min_samples_split": "2",
            "optimize_parameters": str(optimize_parameters).lower(),
            "calculate_shap": str(calculate_shap).lower(),
            "calculate_shap_interactions": str(calculate_shap_interactions).lower(),
            "shap_interaction_columns": '["x1", "x2"]',
        },
    )


@pytest.mark.parametrize("fit_method", ["in_sample", "loocv"])
def test_gwrf_fit_methods(fit_method: str) -> None:
    response = post_gwrf(fit_method)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["fit_method"] == fit_method
    assert result["observations"] == 14
    assert result["metrics"]["pseudo_r_squared"] is not None
    assert result["metrics"]["rmse"] >= 0
    assert len(result["importance_summary"]) == 2
    assert len(result["local_preview"]) == 14
    assert {"shap_x1", "shap_x2", "importance_x1", "importance_x2"} <= set(
        result["local_preview"][0]
    )
    assert result["residual_moran"]["permutations"] == 999


def test_gwrf_export_contains_explanation_tables() -> None:
    response = post_gwrf("loocv", "/api/gwrf/export")
    assert response.status_code == 200, response.text
    workbook = BytesIO(response.content)
    assert {"summary", "relative_importance", "local_results", "residual_moran"} == set(
        pd.ExcelFile(workbook).sheet_names
    )


def test_gwrf_can_skip_shap_completely() -> None:
    response = post_gwrf(calculate_shap=False)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["shap_calculated"] is False
    assert result["shap_interactions_calculated"] is False
    assert not any(key.startswith("shap_") for key in result["local_preview"][0])


def test_gwrf_calculates_only_selected_shap_interactions() -> None:
    response = post_gwrf(calculate_shap=True, calculate_shap_interactions=True)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["shap_interactions_calculated"] is True
    interaction_keys = {
        key for key in result["local_preview"][0] if key.startswith("shap_interaction_")
    }
    assert interaction_keys == {"shap_interaction_x1__x2"}


def test_gwrf_can_optimize_random_forest_parameters() -> None:
    response = post_gwrf(optimize_parameters=True)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["parameters_optimized"] is True
    assert result["rf_parameters"]["n_estimators"] == 10
    assert result["rf_parameters"]["max_depth"] in {5, None}


def test_gwrf_parameter_optimization_is_a_separate_step() -> None:
    dataframe = gwrf_dataframe()
    response = client.post(
        "/api/gwrf/optimize-parameters",
        files={"file": ("gwrf.csv", dataframe.to_csv(index=False), "text/csv")},
        data={
            "dependent_column": "target",
            "independent_columns": '["x1", "x2"]',
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["cv_folds"] == 3
    assert len(result["search_results"]) == 12
    assert result["search_results"][0]["rank"] == 1
    assert result["best_parameters"] == {
        key: result["search_results"][0][key]
        for key in ("n_estimators", "max_depth", "min_samples_split")
    }


def test_gwrf_selects_bandwidth_by_loocv_rmse() -> None:
    dataframe = gwrf_dataframe()
    response = client.post(
        "/api/gwrf/run",
        files={"file": ("gwrf.csv", dataframe.to_csv(index=False), "text/csv")},
        data={
            "coordinate_type": "geographic",
            "x_column": "lon",
            "y_column": "lat",
            "dependent_column": "target",
            "independent_columns": '["x1", "x2"]',
            "bandwidth": "5",
            "fit_method": "in_sample",
            "n_estimators": "10",
            "max_depth": "5",
            "min_samples_split": "2",
            "optimize_bandwidth": "true",
            "bandwidth_candidates": "[5, 8]",
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    search = result["bandwidth_search"]
    assert result["bandwidth_optimized"] is True
    assert result["bandwidth"] in {5, 8}
    assert [item["bandwidth"] for item in search] == [5, 8]
    assert all(item["loocv_rmse"] >= 0 for item in search)
    assert (
        result["bandwidth"]
        == min(search, key=lambda item: item["loocv_rmse"])["bandwidth"]
    )


def test_gwrf_rejects_full_bandwidth_for_loocv() -> None:
    dataframe = gwrf_dataframe()
    response = client.post(
        "/api/gwrf/run",
        files={"file": ("gwrf.csv", dataframe.to_csv(index=False), "text/csv")},
        data={
            "coordinate_type": "geographic",
            "x_column": "lon",
            "y_column": "lat",
            "dependent_column": "target",
            "independent_columns": '["x1", "x2"]',
            "bandwidth": str(len(dataframe)),
            "fit_method": "loocv",
        },
    )
    assert response.status_code == 400
    assert "LOOCV" in response.json()["detail"]
