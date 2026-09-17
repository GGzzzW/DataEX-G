from backend import desktop


def test_configure_webview_enables_downloads(monkeypatch) -> None:
    settings: dict[str, bool] = {"ALLOW_DOWNLOADS": False}
    monkeypatch.setattr(desktop.webview, "settings", settings)

    desktop.configure_webview()

    assert settings["ALLOW_DOWNLOADS"] is True
