import math
import warnings
from typing import Literal

import numpy as np
import pandas as pd
from esda.moran import Moran
from libpysal.weights import KNN
from mgwr.gwr import GWR
from mgwr.sel_bw import Sel_BW
from scipy import stats
from scipy.sparse import SparseEfficiencyWarning
from spreg import OLS, ML_Error, ML_Lag

from backend.analysis import safe_float
from backend.diagnostics import build_design_diagnostics, finalize_model_diagnostics
from backend.quality import is_missing

SpatialMethod = Literal["moran", "slm", "sem", "sdm", "gwr"]
CoordinateType = Literal["geographic", "projected"]


class SpatialAnalysisError(ValueError):
    pass


MORAN_RANDOM_SEED = 20260826


def _prepare_numeric(
    dataframe: pd.DataFrame, columns: list[str]
) -> tuple[pd.DataFrame, int]:
    if len(columns) != len(set(columns)):
        raise SpatialAnalysisError("Each selected column must be unique.")

    converted: dict[str, pd.Series] = {}
    for column in columns:
        if column not in dataframe.columns:
            raise SpatialAnalysisError(f"Column '{column}' does not exist.")
        original = dataframe[column]
        numeric = pd.to_numeric(original, errors="coerce")
        invalid = ~original.map(is_missing) & numeric.isna()
        if invalid.any():
            raise SpatialAnalysisError(
                f"Column '{column}' contains non-numeric values."
            )
        converted[column] = numeric

    prepared = pd.DataFrame(converted, index=dataframe.index).dropna()
    prepared.insert(0, "__source_row__", prepared.index.to_numpy() + 2)
    return prepared.reset_index(drop=True), int(len(dataframe) - len(prepared))


def _build_weights(
    coordinates: np.ndarray, coordinate_type: CoordinateType, neighbors: int
):
    count = len(coordinates)
    if not 1 <= neighbors < count:
        raise SpatialAnalysisError(
            f"The neighbor count must be between 1 and {count - 1}."
        )

    if coordinate_type == "geographic":
        longitude = coordinates[:, 0]
        latitude = coordinates[:, 1]
        if ((longitude < -180) | (longitude > 180)).any():
            raise SpatialAnalysisError("Longitude values must be between -180 and 180.")
        if ((latitude < -90) | (latitude > 90)).any():
            raise SpatialAnalysisError("Latitude values must be between -90 and 90.")

        lon_radians = np.radians(longitude)
        lat_radians = np.radians(latitude)
        # Chord distance on a unit sphere preserves great-circle nearest-neighbor order.
        weight_coordinates = np.column_stack(
            (
                np.cos(lat_radians) * np.cos(lon_radians),
                np.cos(lat_radians) * np.sin(lon_radians),
                np.sin(lat_radians),
            )
        )
    else:
        weight_coordinates = coordinates

    weights = KNN.from_array(weight_coordinates, k=neighbors)
    weights.transform = "r"
    return weights


def _moran_result(values: np.ndarray, weights: object) -> dict[str, object]:
    random_state = np.random.get_state()
    try:
        np.random.seed(MORAN_RANDOM_SEED)
        result = Moran(values, weights, permutations=999, two_tailed=True)
    finally:
        np.random.set_state(random_state)
    return {
        "i": safe_float(result.I),
        "expected_i": safe_float(result.EI),
        "z_score": safe_float(result.z_norm),
        "p_normal": safe_float(result.p_norm),
        "p_permutation": safe_float(result.p_sim),
        "permutations": 999,
        "random_seed": MORAN_RANDOM_SEED,
    }


def _model_selection_diagnostics(
    prepared: pd.DataFrame,
    dependent_column: str,
    independent_columns: list[str],
    weights: object,
) -> dict[str, object]:
    y = prepared[[dependent_column]].to_numpy(dtype=float)
    x = prepared[independent_columns].to_numpy(dtype=float)
    try:
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            baseline = OLS(
                y,
                x,
                w=weights,
                spat_diag=True,
                moran=True,
                name_y=dependent_column,
                name_x=independent_columns,
            )
    except (
        FloatingPointError,
        RuntimeError,
        TypeError,
        ValueError,
        ZeroDivisionError,
        np.linalg.LinAlgError,
    ) as exc:
        return {
            "available": False,
            "baseline_residual_moran": None,
            "tests": [],
            "recommendation": "基础 OLS 空间诊断计算失败，请先处理共线性或数值尺度问题。",
            "warnings": [str(exc)],
        }

    test_definitions = [
        ("LM-Error", baseline.lm_error),
        ("LM-Lag", baseline.lm_lag),
        ("Robust LM-Error", baseline.rlm_error),
        ("Robust LM-Lag", baseline.rlm_lag),
        ("LM-SARMA", baseline.lm_sarma),
    ]
    tests = [
        {
            "name": name,
            "statistic": safe_float(result[0]),
            "p_value": safe_float(result[1]),
        }
        for name, result in test_definitions
    ]
    robust_error_p = float(baseline.rlm_error[1])
    robust_lag_p = float(baseline.rlm_lag[1])
    if robust_lag_p < 0.05 <= robust_error_p:
        recommendation = "稳健 LM-Lag 显著而稳健 LM-Error 不显著，优先考虑 SLM/SAR。"
    elif robust_error_p < 0.05 <= robust_lag_p:
        recommendation = "稳健 LM-Error 显著而稳健 LM-Lag 不显著，优先考虑 SEM。"
    elif robust_lag_p < 0.05 and robust_error_p < 0.05:
        recommendation = "两项稳健检验均显著，可能同时存在滞后和误差依赖；建议比较 SDM 等更完整设定。"
    else:
        recommendation = "两项稳健检验均不显著，当前证据不足以支持 SLM 或 SEM；可先保留 OLS 并结合理论判断。"

    moran_i, moran_z, moran_p = baseline.moran_res
    return {
        "available": True,
        "baseline_residual_moran": {
            "i": safe_float(moran_i),
            "z_score": safe_float(moran_z),
            "p_value": safe_float(moran_p),
        },
        "tests": tests,
        "recommendation": recommendation,
        "warnings": list(dict.fromkeys(str(item.message) for item in captured)),
    }


def _spatial_impacts(
    model: object, method: SpatialMethod, independent_columns: list[str]
) -> list[dict[str, object]]:
    if method not in {"slm", "sdm"}:
        return []

    estimates = {
        name: float(value)
        for name, value in zip(model.name_x, np.asarray(model.betas).reshape(-1))
    }
    rho = float(model.rho)
    denominator = 1 - rho
    if abs(denominator) < 1e-12:
        return [
            {"term": column, "direct": None, "indirect": None, "total": None}
            for column in independent_columns
        ]

    impacts = []
    for column in independent_columns:
        direct = estimates[column]
        lagged_x = estimates.get(f"W_{column}", 0.0) if method == "sdm" else 0.0
        total = (direct + lagged_x) / denominator
        impacts.append(
            {
                "term": column,
                "direct": safe_float(direct),
                "indirect": safe_float(total - direct),
                "total": safe_float(total),
            }
        )
    return impacts


def _coefficient_rows(model: object) -> list[dict[str, object]]:
    names = list(model.name_x)
    estimates = np.asarray(model.betas).reshape(-1)
    standard_errors = np.asarray(model.std_err).reshape(-1)
    statistics = list(model.z_stat)
    rows = []
    for index, name in enumerate(names):
        estimate = safe_float(estimates[index])
        standard_error = safe_float(standard_errors[index])
        statistic, p_value = statistics[index]
        confidence_low = (
            estimate - 1.96 * standard_error
            if estimate is not None and standard_error is not None
            else None
        )
        confidence_high = (
            estimate + 1.96 * standard_error
            if estimate is not None and standard_error is not None
            else None
        )
        rows.append(
            {
                "term": str(name),
                "estimate": estimate,
                "standard_error": standard_error,
                "statistic": safe_float(statistic),
                "p_value": safe_float(p_value),
                "confidence_low": confidence_low,
                "confidence_high": confidence_high,
            }
        )
    return rows


def _run_moran(
    prepared: pd.DataFrame,
    variable: str,
    weights: object,
    diagnostics: dict[str, object],
) -> dict[str, object]:
    values = prepared[variable].to_numpy(dtype=float)
    if np.unique(values).size < 2:
        raise SpatialAnalysisError("Moran's I is undefined for a constant variable.")
    return {
        "kind": "moran",
        "moran": _moran_result(values, weights),
        "regression": None,
        "gwr": None,
        "residual_moran": None,
        "model_selection": None,
        "diagnostics": diagnostics,
    }


def _run_spatial_regression(
    prepared: pd.DataFrame,
    method: SpatialMethod,
    dependent_column: str,
    independent_columns: list[str],
    weights: object,
    diagnostics: dict[str, object],
) -> dict[str, object]:
    y = prepared[[dependent_column]].to_numpy(dtype=float)
    x = prepared[independent_columns].to_numpy(dtype=float)
    try:
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            warnings.filterwarnings("ignore", category=SparseEfficiencyWarning)
            if method == "sem":
                model = ML_Error(
                    y,
                    x,
                    weights,
                    method="LU",
                    name_y=dependent_column,
                    name_x=independent_columns,
                )
            else:
                model = ML_Lag(
                    y,
                    x,
                    weights,
                    slx_lags=1 if method == "sdm" else 0,
                    method="LU",
                    spat_impacts="simple",
                    name_y=dependent_column,
                    name_x=independent_columns,
                )
    except Exception as exc:
        raise SpatialAnalysisError(
            "The spatial model could not be estimated. Check variable scaling, "
            "collinearity, sample size, and the coordinate configuration."
        ) from exc

    diagnostics = finalize_model_diagnostics(
        diagnostics,
        converged=True,
        inference_arrays=(
            model.betas,
            model.std_err,
            [item[1] for item in model.z_stat],
        ),
        captured_warnings=(str(item.message) for item in captured),
        model_warning=(str(model.warning) if getattr(model, "warning", None) else None),
    )

    return {
        "kind": "spatial_regression",
        "moran": None,
        "gwr": None,
        "regression": {
            "coefficients": _coefficient_rows(model),
            "spatial_impacts": _spatial_impacts(model, method, independent_columns),
            "impact_method": "simple",
            "metrics": {
                "pseudo_r_squared": safe_float(model.pr2),
                "aic": safe_float(model.aic),
                "bic": safe_float(model.schwarz),
                "log_likelihood": safe_float(model.logll),
                "rho": safe_float(getattr(model, "rho", math.nan)),
                "lambda": safe_float(getattr(model, "lam", math.nan)),
            },
        },
        "residual_moran": _moran_result(np.asarray(model.u).reshape(-1), weights),
        "diagnostics": diagnostics,
    }


def _run_gwr(
    prepared: pd.DataFrame,
    dependent_column: str,
    independent_columns: list[str],
    x_column: str,
    y_column: str,
    coordinate_type: CoordinateType,
    diagnostics: dict[str, object],
    local_result_limit: int | None,
    weights: object,
) -> dict[str, object]:
    if len(prepared) > 5000:
        raise SpatialAnalysisError(
            "GWR is limited to 5,000 complete observations in this version."
        )

    coordinates = prepared[[x_column, y_column]].to_numpy(dtype=float)
    y = prepared[[dependent_column]].to_numpy(dtype=float)
    x = prepared[independent_columns].to_numpy(dtype=float)
    minimum_bandwidth = max(2 * (len(independent_columns) + 1) + 1, 5)
    if len(prepared) <= minimum_bandwidth:
        raise SpatialAnalysisError(
            f"GWR requires more than {minimum_bandwidth} complete observations."
        )

    try:
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            selector = Sel_BW(
                coordinates,
                y,
                x,
                fixed=False,
                spherical=coordinate_type == "geographic",
                n_jobs=1,
            )
            bandwidth = selector.search(bw_min=minimum_bandwidth)
            model = GWR(
                coordinates,
                y,
                x,
                bandwidth,
                fixed=False,
                spherical=coordinate_type == "geographic",
                n_jobs=1,
            ).fit()
    except Exception as exc:
        raise SpatialAnalysisError(
            "GWR could not be estimated. Check duplicate coordinates, variable "
            "scaling, collinearity, and sample size."
        ) from exc

    diagnostics = finalize_model_diagnostics(
        diagnostics,
        converged=True,
        inference_arrays=(model.params, model.bse, model.tvalues),
        captured_warnings=(str(item.message) for item in captured),
    )

    term_names = ["CONSTANT", *independent_columns]
    local_rows = []
    local_count = (
        len(prepared)
        if local_result_limit is None
        else min(len(prepared), local_result_limit)
    )
    for index in range(local_count):
        row = {
            "source_row": int(prepared.iloc[index]["__source_row__"]),
            x_column: safe_float(coordinates[index, 0]),
            y_column: safe_float(coordinates[index, 1]),
            "observed": safe_float(y[index, 0]),
            "predicted": safe_float(model.predy[index, 0]),
            "residual": safe_float(model.resid_response[index]),
            "local_r_squared": safe_float(model.localR2[index, 0]),
        }
        for term_index, term in enumerate(term_names):
            row[f"coefficient_{term}"] = safe_float(model.params[index, term_index])
            row[f"standard_error_{term}"] = safe_float(model.bse[index, term_index])
            row[f"t_value_{term}"] = safe_float(model.tvalues[index, term_index])
            row[f"p_value_unadjusted_{term}"] = safe_float(
                2 * stats.norm.sf(abs(model.tvalues[index, term_index]))
            )
        local_rows.append(row)

    summaries = []
    for index, term in enumerate(term_names):
        values = model.params[:, index]
        summaries.append(
            {
                "term": term,
                "mean": safe_float(np.mean(values)),
                "standard_deviation": safe_float(np.std(values, ddof=0)),
                "minimum": safe_float(np.min(values)),
                "median": safe_float(np.median(values)),
                "maximum": safe_float(np.max(values)),
            }
        )

    return {
        "kind": "gwr",
        "moran": None,
        "regression": None,
        "gwr": {
            "bandwidth": safe_float(bandwidth),
            "metrics": {
                "r_squared": safe_float(model.R2),
                "adjusted_r_squared": safe_float(model.adj_R2),
                "aic": safe_float(model.aic),
                "aicc": safe_float(model.aicc),
            },
            "coefficient_summaries": summaries,
            "local_result_count": len(prepared),
            "local_preview": local_rows,
        },
        "residual_moran": _moran_result(
            np.asarray(model.resid_response).reshape(-1), weights
        ),
        "diagnostics": diagnostics,
    }


def run_spatial_analysis(
    dataframe: pd.DataFrame,
    *,
    method: SpatialMethod,
    coordinate_type: CoordinateType,
    x_column: str,
    y_column: str,
    dependent_column: str,
    independent_columns: list[str],
    neighbors: int,
    include_full_local_results: bool = False,
) -> dict[str, object]:
    if x_column == y_column:
        raise SpatialAnalysisError(
            "The X/longitude and Y/latitude columns must differ."
        )
    if method != "moran" and not independent_columns:
        raise SpatialAnalysisError("Select at least one independent variable.")
    if dependent_column in independent_columns:
        raise SpatialAnalysisError(
            "The dependent variable cannot also be an independent variable."
        )

    selected_columns = list(
        dict.fromkeys([x_column, y_column, dependent_column, *independent_columns])
    )
    prepared, dropped_rows = _prepare_numeric(dataframe, selected_columns)
    minimum = max(neighbors + 1, len(independent_columns) + 4, 4)
    if len(prepared) < minimum:
        raise SpatialAnalysisError(
            f"At least {minimum} complete observations are required."
        )
    if not np.isfinite(prepared[selected_columns].to_numpy(dtype=float)).all():
        raise SpatialAnalysisError("Selected columns contain infinite values.")
    if prepared[[x_column, y_column]].drop_duplicates().shape[0] < neighbors + 1:
        raise SpatialAnalysisError("There are too few distinct coordinate pairs.")

    for column in independent_columns:
        if prepared[column].nunique() < 2:
            raise SpatialAnalysisError(f"Independent variable '{column}' is constant.")

    coordinate_duplicates = int(
        prepared.duplicated(subset=[x_column, y_column], keep=False).sum()
    )
    coordinates = prepared[[x_column, y_column]].to_numpy(dtype=float)
    weights = _build_weights(coordinates, coordinate_type, neighbors)
    if method == "moran":
        diagnostics: dict[str, object] = {
            "converged": True,
            "valid_inference": True,
            "rank": None,
            "parameter_count": None,
            "condition_number": None,
            "raw_condition_number": None,
            "scale_ratio": None,
            "max_vif": None,
            "vif": [],
            "warnings": [],
        }
    else:
        diagnostics = build_design_diagnostics(prepared, independent_columns)

    diagnostic_warnings = diagnostics["warnings"]
    if coordinate_duplicates:
        diagnostic_warnings.append(
            f"有 {coordinate_duplicates} 行使用重复坐标；KNN/GWR 结果可能受重合点影响。"
        )
    if weights.n_components > 1:
        diagnostic_warnings.append(
            f"空间权重包含 {weights.n_components} 个互不连通的分量，建议检查坐标或增大 K 值。"
        )

    if method == "moran":
        specific = _run_moran(prepared, dependent_column, weights, diagnostics)
    elif method == "gwr":
        specific = _run_gwr(
            prepared,
            dependent_column,
            independent_columns,
            x_column,
            y_column,
            coordinate_type,
            diagnostics,
            None if include_full_local_results else 100,
            weights,
        )
    else:
        specific = _run_spatial_regression(
            prepared,
            method,
            dependent_column,
            independent_columns,
            weights,
            diagnostics,
        )

    if method != "moran":
        specific["model_selection"] = _model_selection_diagnostics(
            prepared,
            dependent_column,
            independent_columns,
            weights,
        )

    return {
        "method": method,
        "observations": len(prepared),
        "dropped_rows": dropped_rows,
        "coordinate_type": coordinate_type,
        "x_column": x_column,
        "y_column": y_column,
        "dependent_column": dependent_column,
        "independent_columns": independent_columns,
        "weights": {
            "type": "knn",
            "neighbors": neighbors,
            "transformation": "row_standardized",
            "components": int(weights.n_components),
        },
        **specific,
    }
