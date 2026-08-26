import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def dataframe_csv(dataframe: pd.DataFrame) -> bytes:
    return dataframe.to_csv(index=False, lineterminator="\n").encode()


def post_analysis(
    dataframe: pd.DataFrame,
    *,
    method: str,
    dependent: str,
    independent_columns: str,
):
    return client.post(
        "/api/analysis/run",
        files={"file": ("analysis.csv", dataframe_csv(dataframe), "text/csv")},
        data={
            "method": method,
            "dependent_column": dependent,
            "independent_columns": independent_columns,
        },
    )


@pytest.mark.parametrize("method", ["pearson", "spearman"])
def test_correlation_methods(method: str) -> None:
    dataframe = pd.DataFrame({"x": [1, 2, 3, 4, 5], "y": [2, 4, 6, 8, 10]})

    response = post_analysis(
        dataframe,
        method=method,
        dependent="y",
        independent_columns='["x"]',
    )

    assert response.status_code == 200
    result = response.json()
    assert result["kind"] == "correlation"
    assert result["correlation"]["coefficient"] == pytest.approx(1.0)
    assert result["correlation"]["p_value"] == pytest.approx(0.0, abs=1e-10)


def test_ols_regression() -> None:
    x = np.arange(1, 21, dtype=float)
    y = 1.0 + 2.0 * x + np.array([(-1) ** index * 0.2 for index in range(20)])
    dataframe = pd.DataFrame({"x": x, "y": y})

    response = post_analysis(
        dataframe,
        method="ols",
        dependent="y",
        independent_columns='["x"]',
    )

    assert response.status_code == 200
    result = response.json()
    coefficient = next(
        item for item in result["regression"]["coefficients"] if item["term"] == "x"
    )
    assert coefficient["estimate"] == pytest.approx(2.0, abs=0.01)
    assert result["regression"]["metrics"]["r_squared"] > 0.99
    assert result["diagnostics"]["converged"] is True
    assert result["diagnostics"]["valid_inference"] is True


def test_logistic_regression() -> None:
    dataframe = pd.DataFrame(
        {
            "x": list(range(20)),
            "outcome": [0, 0, 0, 1, 0, 0, 1, 0, 1, 0, 1, 1, 0, 1, 1, 0, 1, 1, 1, 1],
        }
    )

    response = post_analysis(
        dataframe,
        method="logistic",
        dependent="outcome",
        independent_columns='["x"]',
    )

    assert response.status_code == 200
    result = response.json()
    assert result["regression"]["binary_mapping"] == {"0": 0, "1": 1}
    assert result["regression"]["coefficients"][1]["effect_ratio"] is not None


def test_negative_binomial_regression() -> None:
    random = np.random.default_rng(42)
    x = np.arange(40, dtype=float)
    mean = np.exp(1.0 + 0.03 * x)
    dispersion = 2.0
    counts = random.negative_binomial(dispersion, dispersion / (dispersion + mean))
    dataframe = pd.DataFrame({"x": x, "count": counts})

    response = post_analysis(
        dataframe,
        method="negative_binomial",
        dependent="count",
        independent_columns='["x"]',
    )

    assert response.status_code == 200
    result = response.json()
    terms = [item["term"] for item in result["regression"]["coefficients"]]
    assert terms == ["const", "x", "alpha"]
    assert result["observations"] == 40


def test_logistic_requires_binary_outcome() -> None:
    dataframe = pd.DataFrame({"x": range(8), "outcome": range(8)})

    response = post_analysis(
        dataframe,
        method="logistic",
        dependent="outcome",
        independent_columns='["x"]',
    )

    assert response.status_code == 400
    assert "exactly two outcome values" in response.json()["detail"]


def test_regression_warns_about_perfect_collinearity() -> None:
    dataframe = pd.DataFrame(
        {"x1": range(12), "x2": [2 * value for value in range(12)], "y": range(12)}
    )
    response = post_analysis(
        dataframe,
        method="ols",
        dependent="y",
        independent_columns='["x1", "x2"]',
    )

    assert response.status_code == 200
    diagnostics = response.json()["diagnostics"]
    assert diagnostics["valid_inference"] is False
    assert diagnostics["rank"] < diagnostics["parameter_count"]
    assert diagnostics["warnings"]


@pytest.mark.parametrize("output_format", ["csv", "xlsx"])
def test_export_analysis(output_format: str) -> None:
    dataframe = pd.DataFrame(
        {"x": range(10), "y": [1 + 2 * value for value in range(10)]}
    )
    response = client.post(
        "/api/analysis/export",
        files={"file": ("analysis.csv", dataframe_csv(dataframe), "text/csv")},
        data={
            "method": "ols",
            "dependent_column": "y",
            "independent_columns": '["x"]',
            "output_format": output_format,
        },
    )

    assert response.status_code == 200
    assert (
        f"analysis-analysis-dataex.{output_format}"
        in response.headers["content-disposition"]
    )
    assert response.content
