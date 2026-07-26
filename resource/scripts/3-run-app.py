import shutil
import subprocess
import sys

from utils import env_value, get_project_root, load_env


def run_app() -> int:
    load_env()
    project_root = get_project_root()
    port = env_value("APP_PORT", "8081")
    host = env_value("APP_HOST", "0.0.0.0")

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
