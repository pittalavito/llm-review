import os
import shutil
import subprocess
import sys

from utils import env_value, get_project_root, load_env


def build_frontend(project_root) -> int:
    """Build the React frontend (ui/) into ui/dist so the backend can serve it
    at "/". Skipped when SKIP_UI_BUILD is set, when ui/ is missing, or when npm
    is unavailable — in those cases the backend still runs without the UI."""
    if os.environ.get("SKIP_UI_BUILD"):
        print("SKIP_UI_BUILD set — skipping frontend build.")
        return 0

    ui_dir = project_root / "ui"
    if not ui_dir.is_dir():
        print("WARNING: ui/ not found, skipping frontend build.")
        return 0

    npm = shutil.which("npm")
    if not npm:
        print("WARNING: npm not found, skipping frontend build.")
        return 0

    if not (ui_dir / "node_modules").is_dir():
        install = subprocess.run([npm, "install"], cwd=ui_dir)
        if install.returncode != 0:
            return install.returncode

    print("Building frontend (ui/ -> ui/dist)...")
    build = subprocess.run([npm, "run", "build"], cwd=ui_dir)
    return build.returncode


def run_app() -> int:
    load_env()
    project_root = get_project_root()
    port = env_value("APP_PORT", "8081")
    host = env_value("APP_HOST", "0.0.0.0")

    build_rc = build_frontend(project_root)
    if build_rc != 0:
        return build_rc

    uv = shutil.which("uv")
    if uv:
        cmd_prefix = [uv]
    else:
        cmd_prefix = [sys.executable, "-m", "uv"]

    sync = subprocess.run(cmd_prefix + ["sync"], cwd=project_root)
    if sync.returncode != 0:
        return sync.returncode

    result = subprocess.run(
        cmd_prefix + ["run", "uvicorn", "main:app", "--app-dir", "src", "--reload",
                      "--host", host, "--port", port],
        cwd=project_root,
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(run_app())
