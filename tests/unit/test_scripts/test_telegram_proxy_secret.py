import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("action", ["run", "taskiq-worker", "taskiq-scheduler"])
@pytest.mark.parametrize(
    "proxy_url",
    ["", "[]", '["socks5://user:PRIVATE_PASSWORD@proxy.test:1080","http://backup.test:3128"]'],
)
def test_entrypoints_load_proxy_secret_without_printing_it(
    tmp_path: Path,
    action: str,
    proxy_url: str,
) -> None:
    bash = shutil.which("bash")
    assert bash is not None
    secret_file = tmp_path / "proxy_secret"
    secret_file.write_text(proxy_url)
    secret_file.chmod(0o600)
    output = tmp_path / "loaded_value"
    stub = tmp_path / ("granian" if action == "run" else "taskiq")
    stub.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        'test "${TELEGRAM_PROXY_URLS_FILE+x}" != x\n'
        'printf "%s" "$TELEGRAM_PROXY_URLS" > "$PROXY_TEST_OUTPUT"\n',
    )
    stub.chmod(0o700)
    result = subprocess.run(  # noqa: S603
        [bash, str(Path(__file__).resolve().parents[3] / "start_application.sh"), action],
        env={
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "TELEGRAM_PROXY_URLS_FILE": str(secret_file),
            "TELEGRAM_PROXY_URLS": '["socks5://stale.test:1080"]',
            "PROXY_TEST_OUTPUT": str(output),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert output.read_text() == proxy_url
    assert result.stdout == result.stderr == ""


def test_missing_proxy_secret_file_prevents_application_start(tmp_path: Path) -> None:
    bash = shutil.which("bash")
    assert bash is not None
    result = subprocess.run(  # noqa: S603
        [bash, str(Path(__file__).resolve().parents[3] / "start_application.sh"), "run"],
        env={"PATH": os.environ["PATH"], "TELEGRAM_PROXY_URLS_FILE": str(tmp_path / "missing")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "TELEGRAM_PROXY_URLS_FILE points to an unreadable file" in result.stderr
