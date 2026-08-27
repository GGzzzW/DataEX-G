import math
import time
from typing import Literal

import numpy as np
import pandas as pd
from esda.moran import Moran
from libpysal.weights import KNN
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import GridSearchCV
from sklearn.neighbors import NearestNeighbors

from backend.analysis import safe_float
from backend.quality import is_missing

GwrfFitMethod = Literal["in_sample", "loocv"]
CoordinateType = Literal["geographic", "projected"]
RANDOM_SEED = 42
MORAN_RANDOM_SEED = 20260827


class GwrfError(ValueError):
    pass


def _prepare_numeric(
    dataframe: pd.DataFrame, columns: list[str]
) -> tuple[pd.DataFrame, int]:
    if len(columns) != len(set(columns)):
        raise GwrfError("坐标、因变量和自变量不能重复选择。")

    converted: dict[str, pd.Series] = {}
    for column in columns:
        if column not in dataframe.columns:
            raise GwrfError(f"字段“{column}”不存在。")
        original = dataframe[column]
        numeric = pd.to_numeric(original, errors="coerce")
        invalid = ~original.map(is_missing) & numeric.isna()
        if invalid.any():
            raise GwrfError(f"字段“{column}”包含非数值内容。")
        converted[column] = numeric

    prepared = pd.DataFrame(converted, index=dataframe.index).dropna()
    prepared.insert(0, "__source_row__", prepared.index.to_numpy() + 2)
    dropped = int(len(dataframe) - len(prepared))
    return prepared.reset_index(drop=True), dropped


def _validate_coordinates(
    coordinates: np.ndarray, coordinate_type: CoordinateType
) -> None:
    if not np.isfinite(coordinates).all():
        raise GwrfError("坐标中包含无穷值。")
    if coordinate_type == "geographic":
        if ((coordinates[:, 0] < -180) | (coordinates[:, 0] > 180)).any():
            raise GwrfError("经度必须位于 -180 到 180 之间。")
        if ((coordinates[:, 1] < -90) | (coordinates[:, 1] > 90)).any():
            raise GwrfError("纬度必须位于 -90 到 90 之间。")


def _neighbor_coordinates(
    coordinates: np.ndarray, coordinate_type: CoordinateType
) -> np.ndarray:
    if coordinate_type == "projected":
        return coordinates
    longitude = np.radians(coordinates[:, 0])
    latitude = np.radians(coordinates[:, 1])
    return np.column_stack(
        (
            np.cos(latitude) * np.cos(longitude),
            np.cos(latitude) * np.sin(longitude),
            np.sin(latitude),
        )
    )


def _bisquare(distances: np.ndarray) -> np.ndarray:
    distance_limit = float(np.max(distances))
    if distance_limit <= 0:
        return np.ones_like(distances, dtype=float)
    weights = np.square(1 - np.square(distances / distance_limit))
    weights[distances > distance_limit] = 0
    return weights


def _grid_search_parameters(
    x: pd.DataFrame,
    y: pd.Series,
    *,
    n_estimators: int,
    max_depth: int | None,
    min_samples_split: int,
) -> tuple[dict[str, int | None], list[dict[str, object]]]:
    if len(x) < 6:
        raise GwrfError("自动调参至少需要 6 条完整观测。")
    estimator_values = sorted({max(10, n_estimators // 2), n_estimators})
    depth_values = list(
        dict.fromkeys([max_depth, max_depth * 2 if max_depth is not None else 20, None])
    )
    split_values = sorted({2, min_samples_split})
    grid = GridSearchCV(
        RandomForestRegressor(
            random_state=RANDOM_SEED,
            bootstrap=True,
            n_jobs=1,
        ),
        {
            "n_estimators": estimator_values,
            "max_depth": depth_values,
            "min_samples_split": split_values,
        },
        cv=3,
        scoring="neg_mean_squared_error",
        n_jobs=-1,
    )
    grid.fit(x, y)
    best_parameters = {
        "n_estimators": int(grid.best_params_["n_estimators"]),
        "max_depth": (
            int(grid.best_params_["max_depth"])
            if grid.best_params_["max_depth"] is not None
            else None
        ),
        "min_samples_split": int(grid.best_params_["min_samples_split"]),
    }
    search_results = []
    for index, parameters in enumerate(grid.cv_results_["params"]):
        mean_mse = -float(grid.cv_results_["mean_test_score"][index])
        search_results.append(
            {
                "n_estimators": int(parameters["n_estimators"]),
                "max_depth": (
                    int(parameters["max_depth"])
                    if parameters["max_depth"] is not None
                    else None
                ),
                "min_samples_split": int(parameters["min_samples_split"]),
                "cv_rmse": safe_float(math.sqrt(max(mean_mse, 0))),
                "rank": int(grid.cv_results_["rank_test_score"][index]),
            }
        )
    search_results.sort(key=lambda item: int(item["rank"]))
    return best_parameters, search_results


def optimize_gwrf_parameters(
    dataframe: pd.DataFrame,
    *,
    dependent_column: str,
    independent_columns: list[str],
) -> dict[str, object]:
    if not independent_columns:
        raise GwrfError("请至少选择一个自变量。")
    prepared, dropped_rows = _prepare_numeric(
        dataframe, [dependent_column, *independent_columns]
    )
    if len(prepared) < 6:
        raise GwrfError("随机森林参数寻优至少需要 6 条变量完整的观测。")
    x = prepared[independent_columns]
    y = prepared[dependent_column]
    if (
        not np.isfinite(x.to_numpy(dtype=float)).all()
        or not np.isfinite(y.to_numpy(dtype=float)).all()
    ):
        raise GwrfError("所选变量中包含无穷值。")
    if y.nunique() < 2:
        raise GwrfError("因变量为常量，无法进行参数寻优。")
    for column in independent_columns:
        if x[column].nunique() < 2:
            raise GwrfError(f"自变量“{column}”为常量。")

    best_parameters, search_results = _grid_search_parameters(
        x,
        y,
        n_estimators=200,
        max_depth=10,
        min_samples_split=5,
    )
    return {
        "observations": len(prepared),
        "dropped_rows": dropped_rows,
        "dependent_column": dependent_column,
        "independent_columns": independent_columns,
        "best_parameters": best_parameters,
        "search_results": search_results,
        "cv_folds": 3,
        "scoring": "negative_mean_squared_error",
    }


def _residual_moran(
    residuals: np.ndarray, coordinates: np.ndarray
) -> dict[str, object]:
    neighbors = min(5, len(coordinates) - 1)
    weights = KNN.from_array(coordinates, k=neighbors)
    weights.transform = "r"
    random_state = np.random.get_state()
    try:
        np.random.seed(MORAN_RANDOM_SEED)
        moran = Moran(residuals, weights, permutations=999, two_tailed=True)
    finally:
        np.random.set_state(random_state)
    return {
        "i": safe_float(moran.I),
        "expected_i": safe_float(moran.EI),
        "z_score": safe_float(moran.z_sim),
        "p_normal": safe_float(moran.p_norm),
        "p_permutation": safe_float(moran.p_sim),
        "permutations": 999,
        "random_seed": MORAN_RANDOM_SEED,
    }


def _select_bandwidth(
    x: pd.DataFrame,
    y: pd.Series,
    distance_coordinates: np.ndarray,
    *,
    candidates: list[int],
    parameters: dict[str, int | None],
) -> tuple[int, list[dict[str, object]]]:
    candidates = list(dict.fromkeys(candidates))
    if not candidates:
        raise GwrfError("请至少输入一个候选带宽。")
    minimum = max(3, int(parameters["min_samples_split"]))
    invalid = [
        candidate for candidate in candidates if not minimum <= candidate < len(x)
    ]
    if invalid:
        raise GwrfError(
            f"LOOCV 候选带宽必须位于 {minimum} 到 {len(x) - 1} 之间；"
            f"无效值：{', '.join(map(str, invalid))}。"
        )

    maximum = max(candidates)
    distances, indices = (
        NearestNeighbors(n_neighbors=maximum + 1)
        .fit(distance_coordinates)
        .kneighbors(distance_coordinates)
    )
    search_results: list[dict[str, object]] = []

    for candidate in candidates:
        started_at = time.monotonic()
        predictions: list[float] = []
        for row_index in range(len(x)):
            keep = indices[row_index] != row_index
            local_indices = indices[row_index][keep][:candidate]
            local_distances = distances[row_index][keep][:candidate]
            weights = _bisquare(local_distances)
            if np.count_nonzero(weights) < 2:
                weights = np.ones_like(weights)
            model = RandomForestRegressor(
                n_estimators=int(parameters["n_estimators"]),
                max_depth=parameters["max_depth"],
                min_samples_split=int(parameters["min_samples_split"]),
                random_state=RANDOM_SEED,
                bootstrap=True,
                oob_score=False,
                n_jobs=1,
            )
            model.fit(
                x.iloc[local_indices],
                y.iloc[local_indices],
                sample_weight=weights,
            )
            predictions.append(float(model.predict(x.iloc[[row_index]])[0]))
        rmse = math.sqrt(mean_squared_error(y, predictions))
        search_results.append(
            {
                "bandwidth": candidate,
                "loocv_rmse": safe_float(rmse),
                "elapsed_seconds": round(time.monotonic() - started_at, 3),
            }
        )

    best = min(search_results, key=lambda item: float(item["loocv_rmse"]))
    return int(best["bandwidth"]), search_results


def optimize_gwrf_bandwidth(
    dataframe: pd.DataFrame,
    *,
    coordinate_type: CoordinateType,
    x_column: str,
    y_column: str,
    dependent_column: str,
    independent_columns: list[str],
    bandwidth_candidates: list[int],
    n_estimators: int,
    max_depth: int | None,
    min_samples_split: int,
) -> dict[str, object]:
    if not independent_columns:
        raise GwrfError("请至少选择一个自变量。")
    selected = [x_column, y_column, dependent_column, *independent_columns]
    prepared, dropped_rows = _prepare_numeric(dataframe, selected)
    if len(prepared) < 6:
        raise GwrfError("GWRF 带宽寻优至少需要 6 条变量完整的观测。")
    if not 10 <= n_estimators <= 2000:
        raise GwrfError("决策树数量必须位于 10 到 2000 之间。")
    if max_depth is not None and not 1 <= max_depth <= 200:
        raise GwrfError("最大树深必须位于 1 到 200 之间，或留空表示不限制。")
    if min_samples_split < 2:
        raise GwrfError("最小分裂样本数必须大于或等于 2。")

    coordinates = prepared[[x_column, y_column]].to_numpy(dtype=float)
    _validate_coordinates(coordinates, coordinate_type)
    x = prepared[independent_columns]
    y = prepared[dependent_column]
    if (
        not np.isfinite(x.to_numpy(dtype=float)).all()
        or not np.isfinite(y.to_numpy(dtype=float)).all()
    ):
        raise GwrfError("所选变量中包含无穷值。")
    if y.nunique() < 2:
        raise GwrfError("因变量为常量，无法进行带宽寻优。")
    for column in independent_columns:
        if x[column].nunique() < 2:
            raise GwrfError(f"自变量“{column}”为常量。")

    parameters: dict[str, int | None] = {
        "n_estimators": n_estimators,
        "max_depth": max_depth,
        "min_samples_split": min_samples_split,
    }
    best_bandwidth, search_results = _select_bandwidth(
        x,
        y,
        _neighbor_coordinates(coordinates, coordinate_type),
        candidates=bandwidth_candidates,
        parameters=parameters,
    )
    return {
        "observations": len(prepared),
        "dropped_rows": dropped_rows,
        "best_bandwidth": best_bandwidth,
        "search_results": search_results,
        "rf_parameters": parameters,
    }


def run_gwrf(
    dataframe: pd.DataFrame,
    *,
    coordinate_type: CoordinateType,
    x_column: str,
    y_column: str,
    dependent_column: str,
    independent_columns: list[str],
    bandwidth: int,
    fit_method: GwrfFitMethod,
    n_estimators: int = 200,
    max_depth: int | None = 10,
    min_samples_split: int = 5,
    optimize_parameters: bool = False,
    optimize_bandwidth: bool = False,
    bandwidth_candidates: list[int] | None = None,
    calculate_shap: bool = False,
    calculate_shap_interactions: bool = False,
    shap_interaction_columns: list[str] | None = None,
    include_full_local_results: bool = False,
) -> dict[str, object]:
    if not independent_columns:
        raise GwrfError("请至少选择一个自变量。")
    selected = [x_column, y_column, dependent_column, *independent_columns]
    prepared, dropped_rows = _prepare_numeric(dataframe, selected)
    if len(prepared) < 6:
        raise GwrfError("GWRF 至少需要 6 条变量完整的观测。")
    if not optimize_bandwidth:
        if not 3 <= bandwidth <= len(prepared):
            raise GwrfError(f"带宽必须位于 3 到 {len(prepared)} 之间。")
        if fit_method == "loocv" and bandwidth >= len(prepared):
            raise GwrfError("LOOCV 带宽必须小于完整观测数。")
    if not 10 <= n_estimators <= 2000:
        raise GwrfError("决策树数量必须位于 10 到 2000 之间。")
    if max_depth is not None and not 1 <= max_depth <= 200:
        raise GwrfError("最大树深必须位于 1 到 200 之间，或留空表示不限制。")
    if min_samples_split < 2:
        raise GwrfError("最小分裂样本数必须大于或等于 2。")

    coordinates = prepared[[x_column, y_column]].to_numpy(dtype=float)
    _validate_coordinates(coordinates, coordinate_type)
    x = prepared[independent_columns]
    y = prepared[dependent_column]
    if (
        not np.isfinite(x.to_numpy(dtype=float)).all()
        or not np.isfinite(y.to_numpy(dtype=float)).all()
    ):
        raise GwrfError("所选变量中包含无穷值。")
    if y.nunique() < 2:
        raise GwrfError("因变量为常量，无法拟合 GWRF。")
    for column in independent_columns:
        if x[column].nunique() < 2:
            raise GwrfError(f"自变量“{column}”为常量。")

    interaction_columns = list(dict.fromkeys(shap_interaction_columns or []))
    if calculate_shap_interactions and not calculate_shap:
        raise GwrfError("计算 SHAP 交互效应前必须先启用 SHAP。")
    if calculate_shap_interactions:
        invalid_interaction_columns = [
            column
            for column in interaction_columns
            if column not in independent_columns
        ]
        if invalid_interaction_columns:
            raise GwrfError(
                "SHAP 交互变量必须来自已选择的自变量："
                + "、".join(invalid_interaction_columns)
            )
        if len(interaction_columns) < 2:
            raise GwrfError("计算 SHAP 交互效应至少需要选择两个变量。")

    parameters: dict[str, int | None] = {
        "n_estimators": n_estimators,
        "max_depth": max_depth,
        "min_samples_split": min_samples_split,
    }
    if optimize_parameters:
        parameters, _ = _grid_search_parameters(
            x,
            y,
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_split=min_samples_split,
        )

    distance_coordinates = _neighbor_coordinates(coordinates, coordinate_type)
    bandwidth_search: list[dict[str, object]] = []
    if optimize_bandwidth:
        bandwidth, bandwidth_search = _select_bandwidth(
            x,
            y,
            distance_coordinates,
            candidates=bandwidth_candidates or [],
            parameters=parameters,
        )
    if min_samples_split > bandwidth:
        raise GwrfError("最小分裂样本数不能大于最终带宽。")

    query_count = bandwidth if fit_method == "in_sample" else bandwidth + 1
    distances, indices = (
        NearestNeighbors(n_neighbors=query_count)
        .fit(distance_coordinates)
        .kneighbors(distance_coordinates)
    )

    predictions: list[float] = []
    local_r_squared: list[float | None] = []
    shap_rows: list[np.ndarray] = []
    interaction_rows: list[dict[str, float]] = []
    importance_rows: list[dict[str, float]] = []
    rng = np.random.default_rng(RANDOM_SEED)
    shap_module = None
    if calculate_shap:
        import shap as shap_module

    for row_index in range(len(prepared)):
        local_indices = indices[row_index]
        local_distances = distances[row_index]
        if fit_method == "loocv":
            keep = local_indices != row_index
            local_indices = local_indices[keep][:bandwidth]
            local_distances = local_distances[keep][:bandwidth]
        weights = _bisquare(local_distances)
        if np.count_nonzero(weights) < 2:
            weights = np.ones_like(weights)

        local_x = x.iloc[local_indices]
        local_y = y.iloc[local_indices]
        model = RandomForestRegressor(
            n_estimators=int(parameters["n_estimators"]),
            max_depth=parameters["max_depth"],
            min_samples_split=int(parameters["min_samples_split"]),
            random_state=RANDOM_SEED,
            bootstrap=True,
            n_jobs=-1,
        )
        model.fit(local_x, local_y, sample_weight=weights)

        target = x.iloc[[row_index]]
        prediction = float(model.predict(target)[0])
        predictions.append(prediction)
        local_predictions = model.predict(local_x)
        local_mean = float(np.average(local_y, weights=weights))
        residual_sum = float(np.sum(weights * np.square(local_y - local_predictions)))
        total_sum = float(np.sum(weights * np.square(local_y - local_mean)))
        local_r_squared.append(None if total_sum <= 0 else 1 - residual_sum / total_sum)

        base_mse = mean_squared_error(local_y, local_predictions, sample_weight=weights)
        importance: dict[str, float] = {}
        for column in independent_columns:
            permuted = local_x.copy()
            permuted[column] = rng.permutation(permuted[column].to_numpy())
            permuted_mse = mean_squared_error(
                local_y, model.predict(permuted), sample_weight=weights
            )
            importance[column] = float(permuted_mse - base_mse)
        importance_rows.append(importance)

        if shap_module is not None:
            explainer = shap_module.TreeExplainer(model)
            explanation = explainer(target)
            shap_rows.append(np.asarray(explanation.values).reshape(-1))
            if calculate_shap_interactions:
                interaction_values = np.asarray(
                    explainer.shap_interaction_values(target)
                )
                if interaction_values.ndim == 4:
                    interaction_values = interaction_values[..., 0]
                interaction_matrix = interaction_values[0]
                interactions: dict[str, float] = {}
                for left_index, left_column in enumerate(interaction_columns):
                    for right_column in interaction_columns[left_index + 1 :]:
                        x_left = independent_columns.index(left_column)
                        x_right = independent_columns.index(right_column)
                        interactions[f"{left_column}__{right_column}"] = float(
                            interaction_matrix[x_left, x_right]
                        )
                interaction_rows.append(interactions)

    prediction_array = np.asarray(predictions)
    residuals = y.to_numpy(dtype=float) - prediction_array
    rmse = math.sqrt(mean_squared_error(y, prediction_array))
    pseudo_r_squared = r2_score(y, prediction_array)

    importance_frame = pd.DataFrame(importance_rows)
    mean_importance = importance_frame.mean(axis=0)
    positive_importance = mean_importance.clip(lower=0)
    importance_total = float(positive_importance.sum())
    relative_importance = (
        positive_importance / importance_total * 100
        if importance_total > 0
        else positive_importance
    )
    importance_summary = [
        {
            "variable": column,
            "mean_permutation_importance": safe_float(mean_importance[column]),
            "relative_importance": safe_float(relative_importance[column]),
        }
        for column in relative_importance.sort_values(ascending=False).index
    ]

    shap_array = np.vstack(shap_rows) if shap_rows else None
    result_limit = (
        len(prepared) if include_full_local_results else min(100, len(prepared))
    )
    local_results: list[dict[str, object]] = []
    for row_index in range(result_limit):
        row: dict[str, object] = {
            "source_row": int(prepared.iloc[row_index]["__source_row__"]),
            x_column: safe_float(coordinates[row_index, 0]),
            y_column: safe_float(coordinates[row_index, 1]),
            "observed": safe_float(y.iloc[row_index]),
            "predicted": safe_float(prediction_array[row_index]),
            "residual": safe_float(residuals[row_index]),
            "local_r_squared": safe_float(local_r_squared[row_index]),
        }
        for column_index, column in enumerate(independent_columns):
            row[column] = safe_float(x.iloc[row_index][column])
            row[f"importance_{column}"] = safe_float(
                importance_frame.iloc[row_index][column]
            )
            if shap_array is not None:
                row[f"shap_{column}"] = safe_float(shap_array[row_index, column_index])
        if calculate_shap_interactions:
            for pair, value in interaction_rows[row_index].items():
                row[f"shap_interaction_{pair}"] = safe_float(value)
        local_results.append(row)

    return {
        "method": "gwrf",
        "fit_method": fit_method,
        "observations": len(prepared),
        "dropped_rows": dropped_rows,
        "coordinate_type": coordinate_type,
        "x_column": x_column,
        "y_column": y_column,
        "dependent_column": dependent_column,
        "independent_columns": independent_columns,
        "bandwidth": bandwidth,
        "bandwidth_optimized": optimize_bandwidth,
        "bandwidth_search": bandwidth_search,
        "shap_calculated": calculate_shap,
        "shap_interactions_calculated": calculate_shap_interactions,
        "shap_interaction_columns": interaction_columns,
        "rf_parameters": parameters,
        "parameters_optimized": optimize_parameters,
        "metrics": {
            "pseudo_r_squared": safe_float(pseudo_r_squared),
            "rmse": safe_float(rmse),
        },
        "residual_moran": _residual_moran(residuals, distance_coordinates),
        "importance_summary": importance_summary,
        "local_result_count": len(prepared),
        "local_preview": local_results,
    }
