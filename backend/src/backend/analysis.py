import math
import warnings
from typing import Literal

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

from backend.diagnostics import build_design_diagnostics, finalize_model_diagnostics
from backend.quality import is_missing

AnalysisMethod = Literal[
    "ols",
    "negative_binomial",
    "pearson",
    "spearman",
    "logistic",
]


class AnalysisError(ValueError):
    pass


def safe_float(value: object) -> float | None:
    converted = float(value)
    return converted if math.isfinite(converted) else None


def prepare_numeric_data(
    dataframe: pd.DataFrame,
    columns: list[str],
) -> tuple[pd.DataFrame, int]:
    if len(columns) != len(set(columns)):
        raise AnalysisError("Each selected column must be unique.")

    numeric_data: dict[str, pd.Series] = {}
    for column in columns:
        if column not in dataframe.columns:
            raise AnalysisError(f"Column '{column}' does not exist.")

        original = dataframe[column]
        numeric = pd.to_numeric(original, errors="coerce")
        invalid_mask = ~original.map(is_missing) & numeric.isna()
        if invalid_mask.any():
            raise AnalysisError(f"Column '{column}' contains non-numeric values.")
        numeric_data[column] = numeric

    prepared = pd.DataFrame(numeric_data).dropna()
    return prepared, int(len(dataframe) - len(prepared))


def run_correlation(
    dataframe: pd.DataFrame,
    *,
    method: AnalysisMethod,
    dependent_column: str,
    independent_columns: list[str],
) -> dict[str, object]:
    if len(independent_columns) != 1:
        raise AnalysisError("Pearson and Spearman require exactly two columns.")

    x_column = independent_columns[0]
    prepared, dropped_rows = prepare_numeric_data(
        dataframe, [dependent_column, x_column]
    )
    if len(prepared) < 3:
        raise AnalysisError("At least 3 complete observations are required.")
    if prepared[dependent_column].nunique() < 2 or prepared[x_column].nunique() < 2:
        raise AnalysisError("Correlation is undefined for a constant column.")

    if method == "pearson":
        result = stats.pearsonr(prepared[x_column], prepared[dependent_column])
    else:
        result = stats.spearmanr(prepared[x_column], prepared[dependent_column])

    return {
        "kind": "correlation",
        "method": method,
        "observations": len(prepared),
        "dropped_rows": dropped_rows,
        "dependent_column": dependent_column,
        "independent_columns": independent_columns,
        "correlation": {
            "coefficient": safe_float(result.statistic),
            "p_value": safe_float(result.pvalue),
        },
        "regression": None,
        "diagnostics": None,
    }


def build_coefficients(
    results: object, method: AnalysisMethod
) -> list[dict[str, object]]:
    try:
        confidence_intervals = results.conf_int()
    except (ValueError, np.linalg.LinAlgError):
        confidence_intervals = pd.DataFrame(
            math.nan, index=results.params.index, columns=[0, 1]
        )
    coefficients = []
    for term in results.params.index:
        estimate = safe_float(results.params[term])
        effect_ratio = None
        if method in {"logistic", "negative_binomial"} and term != "alpha":
            try:
                effect_ratio = safe_float(math.exp(float(results.params[term])))
            except OverflowError:
                effect_ratio = None

        coefficients.append(
            {
                "term": str(term),
                "estimate": estimate,
                "standard_error": safe_float(results.bse[term]),
                "statistic": safe_float(results.tvalues[term]),
                "p_value": safe_float(results.pvalues[term]),
                "confidence_low": safe_float(confidence_intervals.loc[term, 0]),
                "confidence_high": safe_float(confidence_intervals.loc[term, 1]),
                "effect_ratio": effect_ratio,
            }
        )
    return coefficients


def run_regression(
    dataframe: pd.DataFrame,
    *,
    method: AnalysisMethod,
    dependent_column: str,
    independent_columns: list[str],
) -> dict[str, object]:
    if not independent_columns:
        raise AnalysisError("Select at least one independent variable.")
    if dependent_column in independent_columns:
        raise AnalysisError(
            "The dependent variable cannot also be an independent variable."
        )

    prepared, dropped_rows = prepare_numeric_data(
        dataframe, [dependent_column, *independent_columns]
    )
    minimum_observations = len(independent_columns) + 3
    if len(prepared) < minimum_observations:
        raise AnalysisError(
            f"At least {minimum_observations} complete observations are required."
        )

    for column in independent_columns:
        if prepared[column].nunique() < 2:
            raise AnalysisError(f"Independent variable '{column}' is constant.")

    y = prepared[dependent_column]
    binary_mapping: dict[str, int] | None = None
    if method == "negative_binomial":
        if (y < 0).any() or not (y % 1 == 0).all():
            raise AnalysisError(
                "Negative binomial regression requires non-negative integer counts."
            )
    elif method == "logistic":
        unique_values = sorted(y.unique().tolist())
        if len(unique_values) != 2:
            raise AnalysisError(
                "Logistic regression requires exactly two outcome values."
            )
        binary_mapping = {str(unique_values[0]): 0, str(unique_values[1]): 1}
        y = y.map({unique_values[0]: 0, unique_values[1]: 1})

    x = sm.add_constant(prepared[independent_columns], has_constant="add")
    diagnostics = build_design_diagnostics(prepared, independent_columns)
    try:
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            if method == "ols":
                results = sm.OLS(y, x).fit()
            elif method == "negative_binomial":
                results = sm.NegativeBinomial(y, x).fit(disp=False, maxiter=200)
            else:
                results = sm.Logit(y, x).fit(disp=False, maxiter=200)
    except Exception as exc:
        raise AnalysisError(
            "The model could not converge. Check sample size, variable variation, and collinearity."
        ) from exc

    mle_results = getattr(results, "mle_retvals", None)
    converged = bool(mle_results.get("converged", True)) if mle_results else True
    diagnostics = finalize_model_diagnostics(
        diagnostics,
        converged=converged,
        inference_arrays=(results.params, results.bse, results.pvalues),
        captured_warnings=(str(item.message) for item in captured),
    )

    metrics = {
        "r_squared": safe_float(getattr(results, "rsquared", math.nan)),
        "adjusted_r_squared": safe_float(getattr(results, "rsquared_adj", math.nan)),
        "pseudo_r_squared": safe_float(getattr(results, "prsquared", math.nan)),
        "aic": safe_float(getattr(results, "aic", math.nan)),
        "bic": safe_float(getattr(results, "bic", math.nan)),
        "log_likelihood": safe_float(getattr(results, "llf", math.nan)),
    }

    return {
        "kind": "regression",
        "method": method,
        "observations": len(prepared),
        "dropped_rows": dropped_rows,
        "dependent_column": dependent_column,
        "independent_columns": independent_columns,
        "correlation": None,
        "regression": {
            "coefficients": build_coefficients(results, method),
            "metrics": metrics,
            "binary_mapping": binary_mapping,
        },
        "diagnostics": diagnostics,
    }


def run_analysis(
    dataframe: pd.DataFrame,
    *,
    method: AnalysisMethod,
    dependent_column: str,
    independent_columns: list[str],
) -> dict[str, object]:
    if method in {"pearson", "spearman"}:
        return run_correlation(
            dataframe,
            method=method,
            dependent_column=dependent_column,
            independent_columns=independent_columns,
        )
    return run_regression(
        dataframe,
        method=method,
        dependent_column=dependent_column,
        independent_columns=independent_columns,
    )
