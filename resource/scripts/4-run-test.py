import shutil
import subprocess
import sys

from utils import get_project_root


def run_test() -> int:
    project_root = get_project_root()
    coverage_target = str(project_root / "src")

    uv = shutil.which("uv")
    cmd_prefix = [uv] if uv else [sys.executable, "-m", "uv"]

    sync = subprocess.run(cmd_prefix + ["sync", "--group", "dev", "--no-install-project"], cwd=project_root)
    if sync.returncode != 0:
        return sync.returncode

    result = subprocess.run(
        cmd_prefix + ["run", "pytest", "-v", f"--cov={coverage_target}", "--cov-report=term-missing"],
        cwd=project_root,
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(run_test())
