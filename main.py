"""Desktop entry point: Flask on an ephemeral localhost port + a PyWebView window.

Flask runs on a daemon thread; the PyWebView window is the main thread. Closing
the window returns from webview.start(), after which the server is shut down.

Phase 2B summary (the desktop UI layer; backend Phase 2A is byte-untouched):
  WHAT WAS BUILT — a vanilla no-build SPA (hand-written HTML/CSS/JS, hash router)
  served same-origin by Flask via the new `app/ui.py` blueprint, registered HERE
  after create_app() so app/__init__.py and every Phase 2A module stay frozen.
  Screens: login/first-run, dashboard, datasets, import, targets (per dataset),
  results, change-password. Aesthetic: dark data-terminal, monospace for all data,
  4-state confidence pill, gate trace rendered as labeled rows (never raw JSON).

  API MISMATCHES handled (each also tagged `API-MISMATCH:` in the JS):
    #1  no HTML served by Phase 2A  -> new ui_bp serves index.html + assets at /.
    #2  no stats endpoint           -> dashboard derives from datasets+targets.
    #3  /api/targets is global      -> filtered by dataset_id client-side.
    #4  add-target phone must exist  -> picker from /datasets/<id>/phone-numbers;
                                        dataset_id sent as a number.
    #5  confidence has 4 states     -> "Insufficient data" gets its own pill.
    #6  analyze omits dataset name  -> joined client-side via /targets+/datasets.
    #7  401 is overloaded           -> redirect to login EXCEPT on login &
                                        change-password, where 401 shows inline.
    #8  freq_contacts + areas_conf  -> both rendered (contacts table + area pill).
    #9  near_tie / alternatives     -> surfaced as a tag + list (display only).
    #10 logout unused in brief      -> logout control in the top nav.
    #11 content-type guard (415)    -> JSON calls set the header; import uses
                                        FormData and lets the browser set it.
    #12 bcrypt 72-byte limit (400)  -> surfaced inline on setup/change-password.

  DEVIATIONS: none from the agreed plan.
  FOLLOW-UPS (out of scope, flagged): re-analysis history/trend, cross-dataset
  target search, CSV/PDF export, multi-account, light theme.
"""

from __future__ import annotations

import json
import os
import platform
import sys
import tempfile
import threading
import time
import urllib.request

from werkzeug.serving import make_server

from app import create_app
from app.ui import bp as ui_bp

_DOTNET_MISSING_MSG = (
    "Nexuslink's desktop window needs the .NET Desktop Runtime, which was not "
    "found on this machine.\n"
    "Install it once and relaunch:\n"
    "  winget install --id Microsoft.DotNet.DesktopRuntime.8.arm64 "
    "--accept-package-agreements --accept-source-agreements\n"
    "(The app's data and analysis are unaffected; this only provides the WebView "
    "host.)"
)


def _ensure_arm64_dotnet_runtime() -> None:
    """Make pywebview's WinForms/WebView2 backend load on Windows ARM64.

    pywebview tries the default pythonnet runtime (.NET Framework) first, but
    clr_loader ships no ARM64 build of its netfx shim, so that path dies with a
    bad-image error. pywebview then falls back to CoreCLR, which loads natively
    on ARM64 — but CoreCLR defaults to the Microsoft.NETCore.App framework, which
    does not contain WinForms, so `clr.AddReference('System.Windows.Forms')`
    raises FileNotFoundException. Here we pre-initialise pythonnet against the
    Microsoft.WindowsDesktop.App shared framework so WinForms resolves; pywebview
    then reuses this already-loaded runtime.

    No-op everywhere else by design — x64 Windows keeps its working .NET Framework
    path, and macOS/Linux don't use .NET at all (pywebview talks to WebKit there).
    """
    if sys.platform != "win32" or platform.machine().lower() != "arm64":
        return

    from clr_loader import get_coreclr
    from clr_loader.util.find import find_dotnet_root

    try:
        dotnet_root = find_dotnet_root()
    except RuntimeError:
        raise SystemExit(_DOTNET_MISSING_MSG)

    desktop_dir = dotnet_root / "shared" / "Microsoft.WindowsDesktop.App"
    versions = [p.name for p in desktop_dir.glob("*") if p.is_dir()] if desktop_dir.is_dir() else []
    if not versions:
        raise SystemExit(_DOTNET_MISSING_MSG)

    def _key(v: str) -> tuple[int, ...]:
        return tuple(int(part) for part in v.split(".") if part.isdigit())

    version = max(versions, key=_key)
    major = _key(version)[0]

    config = {
        "runtimeOptions": {
            "tfm": f"net{major}.0",
            "rollForward": "LatestMinor",
            "framework": {"name": "Microsoft.WindowsDesktop.App", "version": version},
        }
    }
    fd, config_path = tempfile.mkstemp(suffix=".runtimeconfig.json", prefix="nexuslink-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(config, f)

    import pythonnet

    # Set the runtime before pywebview imports `clr`, so its `try: import clr`
    # succeeds against CoreCLR + WindowsDesktop instead of the dead netfx path.
    pythonnet.set_runtime(get_coreclr(runtime_config=config_path))

    # pywebview's winforms/edgechromium backends do `from <namespace> import ...`
    # for several assemblies they never AddReference (Microsoft.Win32.SystemEvents,
    # System.Drawing, System.Diagnostics.Process). Under .NET Framework those
    # namespaces auto-resolved from the GAC; under CoreCLR each assembly must be
    # loaded explicitly or the import raises. Pre-reference them here (best-effort)
    # so the backend imports cleanly. References by simple name resolve from the
    # WindowsDesktop framework the runtime was started with.
    import clr

    for assembly in (
        "System.Windows.Forms",
        "System.Drawing",
        "System.Drawing.Common",
        "Microsoft.Win32.SystemEvents",
        "System.Diagnostics.Process",
    ):
        try:
            clr.AddReference(assembly)
        except Exception:  # noqa: BLE001 - a missing optional assembly must not abort startup
            pass

    _redirect_webview2_interop_to_netcore()
    _install_winforms_coreclr_shim()


def _redirect_webview2_interop_to_netcore() -> None:
    """Point pywebview at the .NET Core build of the WebView2 managed interop.

    pywebview bundles only the .NET Framework (net462) build of
    Microsoft.Web.WebView2.WinForms.dll, which derives from a WinForms Control
    that still exposes the legacy `System.Windows.Forms.ContextMenu` member. That
    type was removed in .NET Core/5+, so loading the control under CoreCLR throws
    `TypeLoadException`. We vendor the matching netcoreapp3.0 build of the two
    managed assemblies and redirect pywebview's `interop_dll_path` lookup to them.
    Only the two managed DLLs are redirected; the native WebView2Loader.dll (which
    pywebview already ships for win-arm64) and every other path fall through.
    """
    vendor_dir = os.path.join(
        os.path.dirname(os.path.realpath(__file__)), "vendor", "webview2", "netcoreapp3.0"
    )
    overrides = {
        name: os.path.join(vendor_dir, name)
        for name in ("Microsoft.Web.WebView2.Core.dll", "Microsoft.Web.WebView2.WinForms.dll")
    }
    if not all(os.path.exists(p) for p in overrides.values()):
        raise SystemExit(
            "Nexuslink's desktop window needs the vendored .NET Core WebView2 "
            f"interop DLLs, which are missing from:\n  {vendor_dir}\n"
            "Restore them from the repository (vendor/webview2/netcoreapp3.0/)."
        )

    import webview.util as _wv_util

    _original = _wv_util.interop_dll_path

    def _interop_dll_path(dll_name: str) -> str:
        override = overrides.get(dll_name)
        return override if override else _original(dll_name)

    # edgechromium does `from webview.util import interop_dll_path` only when the
    # backend loads (inside webview.start()), so patching the module attribute now
    # is picked up there.
    _wv_util.interop_dll_path = _interop_dll_path


def start_server(app, host: str = "127.0.0.1", port: int = 0):
    server = make_server(host, port, app, threaded=True)
    actual_port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, actual_port


def wait_until_ready(port: int, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/api/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url) as r:
                if r.status == 200:
                    return
        except Exception:
            pass
        # Back off on every non-success path (including a non-200 response),
        # so a server that is up but not yet returning 200 can't hot-loop the CPU.
        time.sleep(0.05)
    raise RuntimeError("server did not become ready in time")


def _patch_winforms_source(source: str) -> str:
    """Make pywebview's OpenFolderDialog class importable under CoreCLR.

    The class reflects, at class-definition time, over .NET Framework-internal
    WinForms types (`FileDialogNative+IFileDialog`, `+FOS`) that were removed in
    .NET Core/5+, so `Assembly.GetType(...)` returns None and the class body
    raises before the module finishes importing — taking the whole backend down
    even though the app never opens a native folder dialog. We substitute a
    null-object for those two now-absent types so the class body completes; its
    `show()` method is dead code here. No-op if a future pywebview stops using
    those internal types (the patterns simply won't match).
    """
    import re

    if "class OpenFolderDialog:" not in source or "_CORECLR_FOLDER_DIALOG_SHIM" in source:
        return source

    shim = (
        "class _CoreClrFolderDialogShim:\n"
        "    def __call__(self, *args, **kwargs):\n"
        "        return self\n"
        "    def __getattr__(self, name):\n"
        "        return self\n"
        "_CORECLR_FOLDER_DIALOG_SHIM = _CoreClrFolderDialogShim()\n\n\n"
    )
    source = source.replace("class OpenFolderDialog:", shim + "class OpenFolderDialog:", 1)
    for internal_type in ("IFileDialog", "FOS"):
        source = re.sub(
            r"windowsFormsAssembly\.GetType\(\s*'System\.Windows\.Forms\.FileDialogNative\+"
            + internal_type
            + r"'\s*\)",
            "(windowsFormsAssembly.GetType('System.Windows.Forms.FileDialogNative+"
            + internal_type
            + "') or _CORECLR_FOLDER_DIALOG_SHIM)",
            source,
        )
    return source


def _install_winforms_coreclr_shim() -> None:
    """Install a meta-path finder that source-patches pywebview's winforms module.

    Keeps the fix in-repo (no edits to the installed pywebview), so it is
    version-controlled and survives venv rebuilds.
    """
    import importlib.abc
    import importlib.machinery
    import importlib.util

    target_module = "webview.platforms.winforms"

    class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
        def find_spec(self, fullname, path, target=None):
            if fullname != target_module:
                return None
            real = importlib.machinery.PathFinder.find_spec(fullname, path)
            if real is None or real.origin is None:
                return None
            self._origin = real.origin
            return importlib.util.spec_from_loader(fullname, self, origin=real.origin)

        def create_module(self, spec):
            return None

        def exec_module(self, module):
            with open(self._origin, "r", encoding="utf-8") as f:
                source = f.read()
            module.__file__ = self._origin
            exec(compile(_patch_winforms_source(source), self._origin, "exec"), module.__dict__)

    if not any(isinstance(f, _Finder) for f in sys.meta_path):
        sys.meta_path.insert(0, _Finder())


def main() -> None:  # pragma: no cover - requires a display
    _ensure_arm64_dotnet_runtime()  # must run before pywebview imports `clr`
    import webview

    # pywebview cancels every download unless this is set (its default is False),
    # which silently no-ops the Export screen's .xlsx download inside the desktop
    # window even though the same flow works in a normal browser.
    webview.settings["ALLOW_DOWNLOADS"] = True

    app = create_app()
    app.register_blueprint(ui_bp)  # additive UI layer; Phase 2A factory untouched
    server, thread, port = start_server(app, port=0)
    wait_until_ready(port)
    try:
        webview.create_window("Nexuslink — CDR Analysis", f"http://127.0.0.1:{port}/")
        webview.start()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()  # release the listening socket FD (shutdown alone doesn't)


if __name__ == "__main__":  # pragma: no cover
    main()
