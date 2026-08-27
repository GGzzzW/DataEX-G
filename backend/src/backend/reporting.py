from io import BytesIO

import pandas as pd


def analysis_tables(result: dict[str, object]) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary_rows = [
        {"item": "method", "value": result["method"]},
        {"item": "observations", "value": result["observations"]},
        {"item": "dropped_rows", "value": result["dropped_rows"]},
        {"item": "dependent_column", "value": result["dependent_column"]},
        {
            "item": "independent_columns",
            "value": ", ".join(result["independent_columns"]),
        },
    ]

    correlation = result.get("correlation")
    if correlation:
        summary_rows.extend(
            {"item": key, "value": value} for key, value in correlation.items()
        )
        detail = pd.DataFrame([correlation])
    else:
        regression = result["regression"]
        summary_rows.extend(
            {"item": key, "value": value}
            for key, value in regression["metrics"].items()
        )
        detail = pd.DataFrame(regression["coefficients"])

    diagnostics = result.get("diagnostics")
    if diagnostics:
        summary_rows.extend(
            {"item": key, "value": diagnostics[key]}
            for key in (
                "converged",
                "valid_inference",
                "rank",
                "parameter_count",
                "condition_number",
                "raw_condition_number",
                "scale_ratio",
                "max_vif",
            )
        )
        summary_rows.extend(
            {"item": f"warning_{index}", "value": message}
            for index, message in enumerate(diagnostics["warnings"], start=1)
        )

    return pd.DataFrame(summary_rows), detail


def export_analysis_csv(result: dict[str, object]) -> bytes:
    _, detail = analysis_tables(result)
    return detail.to_csv(index=False, lineterminator="\n").encode("utf-8-sig")


def export_analysis_xlsx(result: dict[str, object]) -> bytes:
    summary, detail = analysis_tables(result)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="summary", index=False)
        detail.to_excel(writer, sheet_name="coefficients", index=False)
        diagnostics = result.get("diagnostics")
        if diagnostics and diagnostics["vif"]:
            pd.DataFrame(diagnostics["vif"]).to_excel(
                writer, sheet_name="vif", index=False
            )
    return output.getvalue()


def spatial_tables(result: dict[str, object]) -> dict[str, pd.DataFrame]:
    weights = result["weights"]
    summary_rows = [
        {"item": "method", "value": result["method"]},
        {"item": "observations", "value": result["observations"]},
        {"item": "dropped_rows", "value": result["dropped_rows"]},
        {"item": "coordinate_type", "value": result["coordinate_type"]},
        {"item": "x_column", "value": result["x_column"]},
        {"item": "y_column", "value": result["y_column"]},
        {"item": "dependent_column", "value": result["dependent_column"]},
        {
            "item": "independent_columns",
            "value": ", ".join(result["independent_columns"]),
        },
        {"item": "weights_type", "value": weights["type"]},
        {"item": "neighbors", "value": weights["neighbors"]},
        {"item": "weights_transformation", "value": weights["transformation"]},
        {"item": "connected_components", "value": weights["components"]},
    ]

    tables: dict[str, pd.DataFrame] = {}
    if result.get("moran"):
        summary_rows.extend(
            {"item": key, "value": value} for key, value in result["moran"].items()
        )
        tables["moran"] = pd.DataFrame(
            [{"item": key, "value": value} for key, value in result["moran"].items()]
        )
    elif result.get("regression"):
        regression = result["regression"]
        summary_rows.extend(
            {"item": key, "value": value}
            for key, value in regression["metrics"].items()
        )
        tables["coefficients"] = pd.DataFrame(regression["coefficients"])
        if regression["spatial_impacts"]:
            tables["spatial_impacts"] = pd.DataFrame(regression["spatial_impacts"])
    else:
        gwr = result["gwr"]
        summary_rows.append({"item": "bandwidth", "value": gwr["bandwidth"]})
        summary_rows.extend(
            {"item": key, "value": value} for key, value in gwr["metrics"].items()
        )
        tables["coefficient_summary"] = pd.DataFrame(gwr["coefficient_summaries"])
        tables["local_results"] = pd.DataFrame(gwr["local_preview"])

    residual_moran = result.get("residual_moran")
    if residual_moran:
        summary_rows.extend(
            {"item": f"residual_moran_{key}", "value": value}
            for key, value in residual_moran.items()
        )
        tables["residual_moran"] = pd.DataFrame(
            [{"item": key, "value": value} for key, value in residual_moran.items()]
        )

    model_selection = result.get("model_selection")
    if model_selection:
        summary_rows.append(
            {
                "item": "model_selection_recommendation",
                "value": model_selection["recommendation"],
            }
        )
        baseline_moran = model_selection["baseline_residual_moran"]
        if baseline_moran:
            summary_rows.extend(
                {"item": f"baseline_residual_moran_{key}", "value": value}
                for key, value in baseline_moran.items()
            )
        selection_rows = list(model_selection["tests"])
        if selection_rows:
            selection_table = pd.DataFrame(selection_rows)
            selection_table["recommendation"] = model_selection["recommendation"]
            tables["model_selection"] = selection_table

    diagnostics = result["diagnostics"]
    diagnostic_rows = [
        {"item": key, "value": diagnostics[key]}
        for key in (
            "converged",
            "valid_inference",
            "rank",
            "parameter_count",
            "condition_number",
            "raw_condition_number",
            "scale_ratio",
            "max_vif",
        )
    ]
    diagnostic_rows.extend(
        {"item": f"warning_{index}", "value": message}
        for index, message in enumerate(diagnostics["warnings"], start=1)
    )
    tables["summary"] = pd.DataFrame(summary_rows)
    tables["diagnostics"] = pd.DataFrame(diagnostic_rows)
    if diagnostics["vif"]:
        tables["vif"] = pd.DataFrame(diagnostics["vif"])
    return tables


def export_spatial_csv(result: dict[str, object]) -> bytes:
    tables = spatial_tables(result)
    if "local_results" in tables:
        selected = tables["local_results"]
    elif "coefficients" in tables:
        selected = tables["coefficients"]
    elif "moran" in tables:
        selected = tables["moran"]
    else:
        selected = tables["summary"]

    diagnostics = result["diagnostics"]
    weights = result["weights"]
    metadata = {
        "report_method": result["method"],
        "report_observations": result["observations"],
        "report_dropped_rows": result["dropped_rows"],
        "report_coordinate_type": result["coordinate_type"],
        "report_neighbors": weights["neighbors"],
        "report_converged": diagnostics["converged"],
        "report_valid_inference": diagnostics["valid_inference"],
        "report_condition_number": diagnostics["condition_number"],
        "report_raw_condition_number": diagnostics["raw_condition_number"],
        "report_max_vif": diagnostics["max_vif"],
        "report_warnings": " | ".join(diagnostics["warnings"]),
    }
    residual_moran = result.get("residual_moran")
    if residual_moran:
        metadata.update(
            {
                "report_residual_moran_i": residual_moran["i"],
                "report_residual_moran_p_permutation": residual_moran["p_permutation"],
            }
        )
    model_selection = result.get("model_selection")
    if model_selection:
        metadata["report_model_recommendation"] = model_selection["recommendation"]
    exported = selected.copy()
    for column, value in reversed(metadata.items()):
        exported.insert(0, column, value)
    return exported.to_csv(index=False, lineterminator="\n").encode("utf-8-sig")


def export_spatial_xlsx(result: dict[str, object]) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, table in spatial_tables(result).items():
            table.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    return output.getvalue()


def gwrf_tables(result: dict[str, object]) -> dict[str, pd.DataFrame]:
    parameters = result["rf_parameters"]
    metrics = result["metrics"]
    summary_rows = [
        {"item": "method", "value": result["method"]},
        {"item": "fit_method", "value": result["fit_method"]},
        {"item": "observations", "value": result["observations"]},
        {"item": "dropped_rows", "value": result["dropped_rows"]},
        {"item": "coordinate_type", "value": result["coordinate_type"]},
        {"item": "x_column", "value": result["x_column"]},
        {"item": "y_column", "value": result["y_column"]},
        {"item": "dependent_column", "value": result["dependent_column"]},
        {
            "item": "independent_columns",
            "value": ", ".join(result["independent_columns"]),
        },
        {"item": "bandwidth", "value": result["bandwidth"]},
        {"item": "bandwidth_optimized", "value": result["bandwidth_optimized"]},
        {"item": "shap_calculated", "value": result["shap_calculated"]},
        {
            "item": "shap_interactions_calculated",
            "value": result["shap_interactions_calculated"],
        },
        {
            "item": "shap_interaction_columns",
            "value": ", ".join(result["shap_interaction_columns"]),
        },
        {"item": "parameters_optimized", "value": result["parameters_optimized"]},
        {"item": "n_estimators", "value": parameters["n_estimators"]},
        {"item": "max_depth", "value": parameters["max_depth"]},
        {"item": "min_samples_split", "value": parameters["min_samples_split"]},
        {"item": "pseudo_r_squared", "value": metrics["pseudo_r_squared"]},
        {"item": "rmse", "value": metrics["rmse"]},
    ]
    summary_rows.extend(
        {"item": f"residual_moran_{key}", "value": value}
        for key, value in result["residual_moran"].items()
    )
    tables = {
        "summary": pd.DataFrame(summary_rows),
        "relative_importance": pd.DataFrame(result["importance_summary"]),
        "local_results": pd.DataFrame(result["local_preview"]),
        "residual_moran": pd.DataFrame(
            [
                {"item": key, "value": value}
                for key, value in result["residual_moran"].items()
            ]
        ),
    }
    if result["bandwidth_search"]:
        tables["bandwidth_search"] = pd.DataFrame(result["bandwidth_search"])
    return tables


def export_gwrf_csv(result: dict[str, object]) -> bytes:
    return (
        pd.DataFrame(result["local_preview"])
        .to_csv(index=False, lineterminator="\n")
        .encode("utf-8-sig")
    )


def export_gwrf_xlsx(result: dict[str, object]) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, table in gwrf_tables(result).items():
            table.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    return output.getvalue()
