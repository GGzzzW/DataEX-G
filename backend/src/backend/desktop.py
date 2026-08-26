import ctypes
import logging
import os
import socket
import sys
import threading
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import uvicorn
import webview

from backend.main import app
from backend.resources import frontend_directory

APP_NAME = "DataEX-G"
APP_TITLE = "DataEX-G"
MUTEX_NAME = "Local\\GGzzzW.DataEX-G"
LOGGER = logging.getLogger(__name__)


def local_data_directory() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    directory = base / APP_NAME
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def configure_logging() -> None:
    log_directory = local_data_directory() / "logs"
    log_directory.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=log_directory / "desktop.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        encoding="utf-8",
    )


def show_error(message: str) -> None:
    LOGGER.error(message)
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(0, message, APP_TITLE, 0x10)
    else:
        print(message, file=sys.stderr)


def acquire_single_instance() -> int | None:
    if sys.platform != "win32":
        return 1
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        return None
    if ctypes.windll.kernel32.GetLastError() == 183:
        ctypes.windll.kernel32.CloseHandle(handle)
        return None
    return int(handle)


def release_single_instance(handle: int | None) -> None:
    if sys.platform == "win32" and handle:
        ctypes.windll.kernel32.CloseHandle(handle)


def create_server() -> tuple[uvicorn.Server, socket.socket, int]:
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(("127.0.0.1", 0))
    server_socket.listen(2048)
    port = int(server_socket.getsockname()[1])
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
    return uvicorn.Server(config), server_socket, port


def wait_for_server(url: str, timeout_seconds: float = 15) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{url}/health", timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, URLError):
            time.sleep(0.1)
    raise RuntimeError("本地分析服务启动超时。")


def run_smoke_test(url: str) -> None:
    with urlopen(f"{url}/health", timeout=5) as response:
        if response.status != 200:
            raise RuntimeError("健康检查失败。")
    with urlopen(url, timeout=5) as response:
        page = response.read(4096)
        if response.status != 200 or b"<html" not in page.lower():
            raise RuntimeError("Vue 首页没有正确打包。")


def main() -> int:
    configure_logging()
    instance_handle = acquire_single_instance()
    if instance_handle is None:
        show_error("DataEX-G 已经在运行。")
        return 1

    if not (frontend_directory() / "index.html").is_file():
        show_error("没有找到前端页面，请先运行前端生产构建。")
        release_single_instance(instance_handle)
        return 1

    server, server_socket, port = create_server()
    server_thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [server_socket]},
        name="local-api",
        daemon=True,
    )
    server_thread.start()
    url = f"http://127.0.0.1:{port}"

    try:
        wait_for_server(url)
        if os.environ.get("DATA_ANALYSIS_DESKTOP_SMOKE_TEST") == "1":
            run_smoke_test(url)
            return 0

        webview.create_window(
            APP_TITLE,
            url,
            width=1280,
            height=820,
            min_size=(960, 640),
            background_color="#edf2ed",
        )
        webview.start(
            debug=False,
            private_mode=False,
            storage_path=str(local_data_directory() / "webview"),
        )
        return 0
    except (OSError, RuntimeError) as exc:
        show_error(f"程序启动失败：{exc}")
        return 1
    finally:
        server.should_exit = True
        server_thread.join(timeout=5)
        server_socket.close()
        release_single_instance(instance_handle)


if __name__ == "__main__":
    raise SystemExit(main())
