# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "playwright>=1.55.0",
# ]
# ///

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Locator, Page, sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIRECTORY = PROJECT_ROOT / "docs" / "software-copyright" / "images"
APP_URL = "http://127.0.0.1:8765"
EDGE_PATH = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")


def capture(locator: Locator, filename: str) -> None:
    locator.scroll_into_view_if_needed()
    locator.screenshot(path=OUTPUT_DIRECTORY / filename, animations="disabled")


def capture_cleaning(page: Page) -> None:
    cleaning_file = PROJECT_ROOT / "samples" / "cleaning-issues.csv"
    page.locator(".drop-zone input[type=file]").set_input_files(cleaning_file)
    page.locator(".selected-file button").click()
    page.get_by_role("heading", name="质量报告").wait_for()

    capture(page.locator(".upload-panel"), "01-file-selection.png")
    capture(page.locator(".summary-grid"), "02-quality-summary.png")
    capture(
        page.get_by_role("heading", name="质量报告")
        .locator("xpath=../..")
        .locator("xpath=.."),
        "03-quality-report.png",
    )

    cleaning_panel = page.locator(".cleaning-panel")
    cleaning_panel.locator('input[value="extract_rows"]').check()
    text_options = cleaning_panel.locator('.checkbox-list input[type="checkbox"]')
    text_options.nth(0).check()
    text_options.nth(1).check()
    cleaning_panel.locator('input[value="min_max"]').check()
    cleaning_panel.locator('.column-selector input[value="score"]').check()
    capture(cleaning_panel, "04-cleaning-rules.png")

    cleaning_panel.get_by_role("button", name="生成清洗预览").click()
    page.locator(".cleaning-result").wait_for()
    capture(page.locator(".cleaning-result"), "05-cleaning-result.png")


def capture_regression(page: Page) -> None:
    regression_file = PROJECT_ROOT / "samples" / "regression-analysis.csv"
    page.get_by_role("button", name="回归分析方法").click()
    page.locator(".analysis-file-picker input[type=file]").set_input_files(
        regression_file
    )
    page.locator(".analysis-file-summary").wait_for()

    page.locator(".variable-grid select").first.select_option("y_continuous")
    page.locator('.independent-selector input[value="x1"]').check()
    page.locator('.independent-selector input[value="x2"]').check()
    analysis_setup = (
        page.locator(".workspace-view").nth(0).locator("section.panel").nth(1)
    )
    capture(analysis_setup, "06-regression-settings.png")

    analysis_setup.get_by_role("button", name="运行分析").click()
    page.locator(".analysis-result").wait_for()
    capture(page.locator(".analysis-result"), "07-regression-result.png")


def capture_spatial(page: Page) -> None:
    spatial_file = PROJECT_ROOT / "samples" / "spatial-analysis.csv"
    page.get_by_role("button", name="空间分析").click()
    page.locator(".spatial-file-picker input[type=file]").set_input_files(spatial_file)
    page.locator(".spatial-summary-tags").first.wait_for()

    spatial_workspace = page.locator(".workspace-view").nth(1)
    settings = spatial_workspace.locator("section.panel").nth(1)
    settings.locator(".spatial-variable-grid select").nth(2).select_option("outcome")
    capture(settings, "08-spatial-settings.png")

    settings.get_by_role("button", name="运行空间分析").click()
    page.locator(".spatial-result").wait_for(timeout=30_000)
    capture(page.locator(".spatial-result"), "09-spatial-result.png")


def main() -> None:
    if not EDGE_PATH.is_file():
        raise RuntimeError(f"没有找到 Microsoft Edge：{EDGE_PATH}")

    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=EDGE_PATH,
            headless=True,
            args=["--disable-gpu"],
        )
        context = browser.new_context(
            viewport={"width": 1400, "height": 1000},
            device_scale_factor=1.25,
            locale="zh-CN",
        )
        page = context.new_page()
        page.goto(APP_URL, wait_until="networkidle")
        page.screenshot(
            path=OUTPUT_DIRECTORY / "00-main-interface.png",
            animations="disabled",
        )

        capture_cleaning(page)
        capture_regression(page)
        capture_spatial(page)

        context.close()
        browser.close()

    screenshots = sorted(OUTPUT_DIRECTORY.glob("*.png"))
    print(f"SCREENSHOTS={len(screenshots)}")
    for screenshot in screenshots:
        print(screenshot)


if __name__ == "__main__":
    main()
