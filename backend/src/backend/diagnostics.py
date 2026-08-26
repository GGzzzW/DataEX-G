import math
import warnings
from collections.abc import Iterable

import numpy as np
import pandas as pd
from statsmodels.stats.outliers_influence import variance_inflation_factor


def _finite_float(value: object) -> float | None:
    converted = float(value)
    return converted if math.isfinite(converted) else None


def _append_unique(messages: list[str], message: str) -> None:
    if message and message not in messages:
        messages.append(message)


def build_design_diagnostics(
    dataframe: pd.DataFrame, columns: list[str]
) -> dict[str, object]:
    values = dataframe[columns].to_numpy(dtype=float)
    parameter_count = len(columns) + 1
    diagnostic_warnings: list[str] = []

    standard_deviations = np.std(values, axis=0, ddof=0)
    nonzero_scales = standard_deviations[standard_deviations > 0]
    scale_ratio = (
        float(np.max(nonzero_scales) / np.min(nonzero_scales))
        if len(nonzero_scales) > 1
        else 1.0
    )
    if scale_ratio >= 1000:
        _append_unique(
            diagnostic_warnings,
            "自变量的数值尺度相差超过 1000 倍，建议仅对自变量进行 Z-score 标准化。",
        )

    standardized = np.divide(
        values - np.mean(values, axis=0),
        standard_deviations,
        out=np.zeros_like(values, dtype=float),
        where=standard_deviations != 0,
    )
    standardized_design = np.column_stack((np.ones(len(values)), standardized))
    raw_design = np.column_stack((np.ones(len(values)), values))
    rank = int(np.linalg.matrix_rank(standardized_design))
    condition_number = float(np.linalg.cond(standardized_design))
    raw_condition_number = float(np.linalg.cond(raw_design))
    if rank < parameter_count:
        _append_unique(
            diagnostic_warnings,
            "设计矩阵不满秩，部分自变量可能完全重复或可由其他变量线性组合得到。",
        )
    elif condition_number >= 30:
        _append_unique(
            diagnostic_warnings,
            "标准化后的设计矩阵条件数较高，结果可能受到多重共线性影响。",
        )
    if raw_condition_number >= 1_000_000:
        _append_unique(
            diagnostic_warnings,
            "原始尺度条件数超过 100 万，模型可能发生数值不稳定；建议仅标准化自变量。",
        )

    vif_rows = []
    design_with_constant = np.column_stack((np.ones(len(values)), values))
    for index, column in enumerate(columns, start=1):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=RuntimeWarning)
                vif_value = float(
                    variance_inflation_factor(design_with_constant, index)
                )
        except (ValueError, np.linalg.LinAlgError, ZeroDivisionError):
            vif_value = math.inf
        vif_rows.append({"column": column, "vif": _finite_float(vif_value)})

    finite_vifs = [row["vif"] for row in vif_rows if row["vif"] is not None]
    max_vif = max(finite_vifs, default=None)
    infinite_vif = any(row["vif"] is None for row in vif_rows)
    if infinite_vif or (max_vif is not None and max_vif >= 10):
        _append_unique(
            diagnostic_warnings,
            "检测到严重多重共线性（VIF ≥ 10 或无穷大），系数和显著性可能不稳定。",
        )
    elif max_vif is not None and max_vif >= 5:
        _append_unique(
            diagnostic_warnings,
            "检测到较强多重共线性（VIF ≥ 5），建议检查变量选择。",
        )

    return {
        "converged": True,
        "valid_inference": rank == parameter_count,
        "rank": rank,
        "parameter_count": parameter_count,
        "condition_number": _finite_float(condition_number),
        "raw_condition_number": _finite_float(raw_condition_number),
        "scale_ratio": _finite_float(scale_ratio),
        "max_vif": max_vif,
        "vif": vif_rows,
        "warnings": diagnostic_warnings,
    }


def finalize_model_diagnostics(
    diagnostics: dict[str, object],
    *,
    converged: bool,
    inference_arrays: Iterable[object],
    captured_warnings: Iterable[str] = (),
    model_warning: str | None = None,
) -> dict[str, object]:
    messages = list(diagnostics["warnings"])
    for message in captured_warnings:
        _append_unique(messages, f"模型运行警告：{message}")
    if model_warning:
        _append_unique(messages, f"模型警告：{model_warning}")
    if not converged:
        _append_unique(
            messages,
            "模型未收敛；当前系数、标准误、p 值和置信区间不能作为可靠结论。",
        )

    finite_inference = True
    for values in inference_arrays:
        try:
            if not np.isfinite(np.asarray(values, dtype=float)).all():
                finite_inference = False
                break
        except (TypeError, ValueError):
            finite_inference = False
            break
    if not finite_inference:
        _append_unique(
            messages,
            "部分估计值或推断统计量不是有限数值，通常表示矩阵求逆失败或数值溢出。",
        )

    diagnostics["converged"] = converged
    diagnostics["valid_inference"] = bool(
        diagnostics["valid_inference"] and converged and finite_inference
    )
    diagnostics["warnings"] = messages
    return diagnostics
