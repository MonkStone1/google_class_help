"""Production launcher — entry point of GoogleClassHelp.exe.

Responsibilities (see docs/prompt/GoogleClassHelp_Nuitka_Production_Prompt.md):

1. set up file logging in the user data directory (no console in release);
2. guarantee a single instance: a named Windows mutex makes a second launch
   activate the running dashboard instead of starting a second backend
   (ADR-0018);
3. publish the running instance (pid, port) in DATA_DIR/app.lock, so a second
   launch can find the dashboard even on a non-default port (ADR-0018);
4. start the FastAPI application with uvicorn, bound to 127.0.0.1 only;
5. pick the dashboard port: 8000 by default, otherwise the nearest free one;
6. wait until the backend is actually ready (poll /api/health);
7. bring the dashboard to the user: focus an already open dashboard window
   (no duplicate browser tab), otherwise open the default browser;
8. keep the app visible and controllable through a tray icon (open / exit)
   instead of dissolving into an invisible background process;
9. keep the backend alive and shut it down cleanly on exit;
10. surface fatal startup errors through the log file and a message box.

No console window is opened in the release build; nothing here may depend
on the current working directory or the project layout.
"""

import json
import logging
import os
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Callable
from logging.handlers import RotatingFileHandler

import uvicorn

from main import app
from path_config import DATA_DIR, LOGS_DIR, ensure_data_dirs

DEFAULT_PORT = 8000
# Ports tried in order for the dashboard (review §1.9). Binding success is
# confirmed by the server actually serving, never by a probe bind: a probe
# would close the socket and let another process grab the port (TOCTOU).
PORT_RANGE = 50
READY_TIMEOUT_SECONDS = 60
LOG_FILE_SIZE = 1_000_000
LOG_BACKUPS = 3

# Named mutex of the single-instance guard. Session-scoped on purpose: each
# interactive Windows session keeps its own dashboard.
MUTEX_NAME = "GoogleClassHelp-SingleInstance"
ERROR_ALREADY_EXISTS = 183

# Runtime state of the running instance, written once the port is known.
STATE_FILE = DATA_DIR / "app.lock"
# Handshake file: a second launch drops it, the owner picks it up and shows a
# tray notification (the two processes cannot talk to each other directly).
WAKE_FILE = DATA_DIR / "app.wake"

# Window titles of the dashboard: the frontend sets document.title from the
# active locale (see "app.title" in frontend/src/i18n.ts). Used to tell an
# already open dashboard window from unrelated browser windows.
DASHBOARD_WINDOW_TITLES = (
    "Classroom Dashboard",  # en
    "Дошка класу",  # uk
    "Доска класса",  # ru
)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259
SW_SHOW = 5
SW_RESTORE = 9

logger = logging.getLogger("launcher")

# Kept for the whole process lifetime: the guard holds as long as the handle
# (and the process) is alive, so it needs no cleanup on crash.
_mutex_handle: int | None = None


def _message_box(text: str) -> None:
    """Best-effort user-visible error dialog (GUI build has no console)."""
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, "GoogleClassHelp", 0x10)
    except Exception as exc:  # noqa: BLE001 - dialog is best-effort only
        logger.debug("Message box unavailable: %r", exc)


def setup_logging() -> None:
    ensure_data_dirs()
    handler = RotatingFileHandler(
        LOGS_DIR / "app.log",
        maxBytes=LOG_FILE_SIZE,
        backupCount=LOG_BACKUPS,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    logging.captureWarnings(True)


def _http_get_ok(url: str, timeout: float) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError):
        return False


def wait_until_ready(
    port: int,
    server: uvicorn.Server,
    server_thread: threading.Thread,
    timeout: float = READY_TIMEOUT_SECONDS,
) -> bool:
    """Wait for THIS server instance: uvicorn's own started flag first,
    then a real HTTP health check (guards against a partial bind)."""
    deadline = time.monotonic() + timeout
    url = f"http://127.0.0.1:{port}/api/health"
    while time.monotonic() < deadline:
        if not server_thread.is_alive():
            return False  # uvicorn died during startup (e.g. bind failure)
        if server.started and _http_get_ok(url, timeout=1.0):
            return True
        time.sleep(0.25)
    return False


def start_on_free_port(app) -> tuple[uvicorn.Server, threading.Thread, int]:
    """Start uvicorn on the first port it can actually bind (review §1.9).

    Replaces the old probe-then-bind dance (is_port_free + pick_port): a
    probe closes the socket, leaving a window for another process to take
    the port before uvicorn binds. Here the bind failure itself (the server
    thread dies) moves us to the next port, and readiness is confirmed by
    serving /api/health — no window, no TOCTOU.
    """
    for port in range(DEFAULT_PORT, DEFAULT_PORT + PORT_RANGE):
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host="127.0.0.1",
                port=port,
                log_config=None,  # uvicorn logs propagate to the root handler
                loop="asyncio",
                http="h11",
                ws="none",  # no websockets needed; keeps the build minimal
                lifespan="on",
                # Trusted-proxy headers are handled by backend/proxy.py, which
                # verifies the immediate peer against GC_DASHBOARD_TRUSTED_PROXIES
                # before believing X-Forwarded-Proto/Host.  Letting Uvicorn also
                # apply them would trust its own (loopback-by-default) list and
                # rewrite request.client before that check can run (§29).
                proxy_headers=False,
                forwarded_allow_ips=[],
            )
        )
        thread = threading.Thread(target=server.run, name="uvicorn-server", daemon=True)
        thread.start()
        # Short timeout here: the only expected failure is a bind error,
        # which kills the thread almost immediately.
        if wait_until_ready(port, server, thread, timeout=5.0):
            return server, thread, port  # the port is really being served
        server.should_exit = True
        thread.join(timeout=5)
        logger.warning("Port %s is not bindable, trying the next one.", port)
    raise RuntimeError(
        f"No bindable port found in the range {DEFAULT_PORT}-{DEFAULT_PORT + PORT_RANGE - 1}"
    )


def acquire_single_instance() -> bool:
    """Create the named mutex; False means another instance owns it.

    A mutex (unlike a pid file) cannot go stale: Windows releases it when the
    owning process dies, so a crash never locks the user out of the app.
    """
    global _mutex_handle
    try:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_bool,
            ctypes.c_wchar_p,
        ]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        error = ctypes.get_last_error()
        if not handle:
            logger.warning("CreateMutexW failed (error %s); guard disabled.", error)
            return True
        _mutex_handle = handle
        return error != ERROR_ALREADY_EXISTS
    except Exception as exc:  # noqa: BLE001 - non-Windows development runs
        logger.warning("Single-instance guard unavailable: %r", exc)
        return True


def release_single_instance() -> None:
    """Drop the guard handle (process exit would do this anyway)."""
    global _mutex_handle
    if _mutex_handle is None:
        return
    try:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle(ctypes.c_void_p(_mutex_handle))
    except Exception as exc:  # noqa: BLE001 - best effort
        logger.debug("CloseHandle failed: %r", exc)
    _mutex_handle = None


def read_state() -> dict | None:
    """Read the running instance's pid/port; None when missing or unreadable."""
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return state if isinstance(state, dict) else None


def write_state(port: int) -> None:
    payload = {"pid": os.getpid(), "port": port, "started": time.time()}
    try:
        STATE_FILE.write_text(json.dumps(payload), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not write %s: %r", STATE_FILE, exc)


def remove_state() -> None:
    try:
        STATE_FILE.unlink()
    except OSError:
        pass


def _is_process_alive(pid: int) -> bool:
    """os.kill(pid, 0) is unusable on Windows: it terminates the process."""
    try:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.OpenProcess.argtypes = [
            ctypes.c_uint32,
            ctypes.c_bool,
            ctypes.c_uint32,
        ]
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(
                ctypes.c_void_p(handle), ctypes.byref(code)
            ):
                return False
            return code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel32.CloseHandle(ctypes.c_void_p(handle))
    except Exception as exc:  # noqa: BLE001 - non-Windows development runs
        logger.debug("Process liveness check failed: %r", exc)
        return False


def drop_stale_state() -> None:
    """We own the mutex, so anything left behind is from an earlier run."""
    # A handshake dropped by a launch that raced with a hard kill must not
    # turn into a tray notification on this start.
    consume_wake()
    state = read_state()
    if state is None:
        return
    pid = state.get("pid")
    if isinstance(pid, int) and pid != os.getpid() and _is_process_alive(pid):
        # Possible on a developer machine (uvicorn started by hand): the port
        # record is still ours to overwrite.
        logger.info("Overwriting state file of live pid %s.", pid)
    else:
        logger.info("Removing stale state file %s.", STATE_FILE)
    remove_state()


def _find_dashboard_window() -> int | None:
    """Return the HWND of a visible window titled like the dashboard."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        handles: list[int] = []
        titles = tuple(title.lower() for title in DASHBOARD_WINDOW_TITLES)

        def _collect(hwnd: int, _param: int) -> bool:
            length = user32.GetWindowTextLengthW(hwnd)
            if not length:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            text = buffer.value.lower()
            if any(title in text for title in titles):
                handles.append(hwnd)
            return True

        callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(
            _collect
        )
        user32.EnumWindows(callback, 0)

        for hwnd in handles:
            if user32.IsWindowVisible(hwnd):
                return hwnd
        return None
    except Exception as exc:  # noqa: BLE001 - non-Windows development runs
        logger.debug("Window lookup unavailable: %r", exc)
        return None


def _focus_dashboard_window() -> bool:
    """Bring an already open dashboard window to the front (no new tab).

    Only the browser's active tab is part of a window title, so a background
    or pinned tab of a multi-tab window cannot be detected here. That case
    falls back to opening the URL, and the frontend presence (see ADR-0018)
    hands the focus back to the tab that already owns the dashboard.
    """
    hwnd = _find_dashboard_window()
    if hwnd is None:
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        else:
            user32.ShowWindow(hwnd, SW_SHOW)
        if user32.SetForegroundWindow(hwnd):
            logger.info("Focused the dashboard window already open (hwnd %s).", hwnd)
            return True
        # SetForegroundWindow can be refused when we did not just receive
        # foreground rights; this older API is more permissive.
        user32.SwitchToThisWindow(hwnd, True)
        logger.info("Switched to the dashboard window already open (hwnd %s).", hwnd)
        return True
    except Exception as exc:  # noqa: BLE001 - best effort
        logger.debug("Could not focus the dashboard window: %r", exc)
        return False


def open_dashboard(url: str) -> None:
    """Focus the dashboard if it is already open, otherwise open a browser."""
    if _focus_dashboard_window():
        return
    logger.info("Opening the browser at %s", url)
    webbrowser.open(url, new=2, autoraise=True)


def request_wake() -> None:
    """Ask the running instance to notify the user via its tray icon."""
    try:
        WAKE_FILE.write_text("1", encoding="utf-8")
    except OSError as exc:
        logger.debug("Could not write the wake file: %r", exc)


def consume_wake() -> bool:
    if not WAKE_FILE.exists():
        return False
    try:
        WAKE_FILE.unlink()
    except OSError:
        pass
    return True


def _tray_image():
    """Small in-memory icon: no extra asset has to be bundled into the build."""
    from PIL import Image, ImageDraw

    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (4, 4, size - 4, size - 4), radius=14, fill=(26, 115, 232, 255)
    )
    draw.rectangle((16, 18, 48, 46), outline=(255, 255, 255, 255), width=4)
    draw.line((16, 28, 48, 28), fill=(255, 255, 255, 255), width=3)
    return image


class TrayIcon:
    """Tray icon that keeps the background app visible and controllable.

    Any pystray/Pillow failure degrades to "no tray icon": the launcher must
    also work in a build without those packages (they are optional there).
    """

    TITLE = "GoogleClassHelp"

    def __init__(self, url: str, on_exit: Callable[[], None]) -> None:
        self._url = url
        self._on_exit = on_exit
        self._icon = None

    def start(self) -> None:
        try:
            import pystray
        except Exception as exc:  # noqa: BLE001 - optional dependency
            logger.info("Tray icon unavailable: %r", exc)
            return
        try:
            menu = pystray.Menu(
                pystray.MenuItem("Open dashboard", self._open, default=True),
                pystray.MenuItem("Exit", self._exit),
            )
            self._icon = pystray.Icon(self.TITLE, _tray_image(), self.TITLE, menu)
            self._icon.run_detached()  # must precede setting `visible`
            self._icon.visible = True
            logger.info("Tray icon is shown.")
        except Exception as exc:  # noqa: BLE001 - never break the dashboard
            logger.warning("Could not show the tray icon: %r", exc)
            self._icon = None

    def notify(self, message: str) -> None:
        if self._icon is None:
            return
        try:
            self._icon.notify(message, self.TITLE)
        except Exception as exc:  # noqa: BLE001 - notifications are optional
            logger.debug("Tray notification failed: %r", exc)

    def stop(self) -> None:
        if self._icon is None:
            return
        try:
            self._icon.stop()
        except Exception as exc:  # noqa: BLE001 - best effort
            logger.debug("Tray icon stop failed: %r", exc)
        self._icon = None

    def _open(self) -> None:
        open_dashboard(self._url)

    def _exit(self) -> None:
        logger.info("Exit requested from the tray icon.")
        self._on_exit()


def activate_running_instance() -> int:
    """Handle a second launch: activate the running dashboard, never start one.

    The mutex proves the other process owns the backend; the state file tells
    us which port it listens on.
    """
    state = read_state() or {}
    try:
        port = int(state.get("port", DEFAULT_PORT))
    except (TypeError, ValueError):
        port = DEFAULT_PORT
    url = f"http://127.0.0.1:{port}"

    # The owner may still be starting up (mutex taken before the port is
    # ready): give it a short grace period instead of failing the launch.
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if _http_get_ok(f"{url}/api/health", timeout=1.0):
            break
        time.sleep(0.25)
    else:
        logger.error("A running instance does not answer on port %s.", port)
        _message_box(
            "GoogleClassHelp is already running, but the dashboard does not "
            f"answer on port {port}.\n"
            f"Details: see the log file at {LOGS_DIR}\\app.log"
        )
        return 1

    logger.info("Dashboard already running on port %s; activating it.", port)
    request_wake()  # let the owner confirm via its tray icon
    open_dashboard(url)
    return 0


def run() -> int:
    logger.info("Starting GoogleClassHelp (data dir: %s)", DATA_DIR)

    if not acquire_single_instance():
        return activate_running_instance()

    drop_stale_state()
    try:
        server, server_thread, port = start_on_free_port(app)
    except RuntimeError as exc:
        logger.error("%s", exc)
        release_single_instance()
        _message_box(
            "GoogleClassHelp failed to start (no free port).\n"
            f"Details: see the log file at {LOGS_DIR}\\app.log"
        )
        return 1
    url = f"http://127.0.0.1:{port}"
    logger.info("Uvicorn listening on 127.0.0.1:%s", port)

    # From here on the instance is discoverable by a second launch.
    write_state(port)

    exit_requested = threading.Event()
    tray = TrayIcon(url, exit_requested.set)
    tray.start()

    open_dashboard(url)

    try:
        while server_thread.is_alive() and not exit_requested.wait(0.5):
            if consume_wake():
                tray.notify("GoogleClassHelp is already running - dashboard restored.")
    except KeyboardInterrupt:
        logger.info("Interrupt received; shutting down.")
    finally:
        from background_sync import stop as stop_background_sync

        stop_background_sync()  # stop the scheduler before executors die
        server.should_exit = True
        server_thread.join(timeout=10)
        tray.stop()
        remove_state()
        release_single_instance()
        if server_thread.is_alive():
            logger.warning("Uvicorn thread did not stop within timeout.")
        else:
            logger.info("Backend stopped; exiting cleanly.")
    return 0


def main() -> int:
    setup_logging()
    try:
        return run()
    except Exception:  # noqa: BLE001 - no console: the log is the only trace
        logger.error("Fatal error:\n%s", traceback.format_exc())
        _message_box(
            "GoogleClassHelp crashed unexpectedly.\n"
            f"Details: see the log file at {LOGS_DIR}\\app.log"
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
