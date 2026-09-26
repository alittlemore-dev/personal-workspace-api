import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_run_loads_app_secret_from_file_and_unsets_file_reference(tmp_path: Path) -> None:
    secret_file = tmp_path / "app_secret_key"
    secret_file.write_text("test-personal-secret\n", encoding="utf-8")
    runtime_log = tmp_path / "runtime.log"
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    granian = binary_dir / "granian"
    granian.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n%s\\n' \"$APP_SECRET_KEY\" "
        '"${APP_SECRET_KEY_FILE-unset}" >"$FAKE_RUNTIME_LOG"\n',
        encoding="utf-8",
    )
    granian.chmod(0o755)
    environment = os.environ.copy()
    environment.pop("APP_SECRET_KEY", None)
    environment.update(
        {
            "APP_SECRET_KEY_FILE": str(secret_file),
            "FAKE_RUNTIME_LOG": str(runtime_log),
            "PATH": f"{binary_dir}:{environment['PATH']}",
        },
    )

    result = subprocess.run(  # noqa: S603
        ["/bin/bash", str(ROOT / "start_application.sh"), "run"],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert runtime_log.read_text(encoding="utf-8") == "test-personal-secret\nunset\n"


def test_run_loads_telegram_secrets_from_files(tmp_path: Path) -> None:
    token_file = tmp_path / "bot_token"
    token_file.write_text("123456:BOT_TOKEN\n", encoding="utf-8")
    webhook_file = tmp_path / "webhook_secret"
    webhook_file.write_text("WEBHOOK_SECRET\n", encoding="utf-8")
    service_file = tmp_path / "service_secret"
    service_file.write_text("SERVICE_SECRET\n", encoding="utf-8")
    runtime_log = tmp_path / "runtime.log"
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    granian = binary_dir / "granian"
    granian.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n%s\\n%s\\n%s\\n%s\\n%s\\n" "$TELEGRAM_BOT_TOKEN" '
        '"${TELEGRAM_BOT_TOKEN_FILE-unset}" "$TELEGRAM_WEBHOOK_SECRET" '
        '"${TELEGRAM_WEBHOOK_SECRET_FILE-unset}" "$TELEGRAM_SERVICE_SECRET" '
        '"${TELEGRAM_SERVICE_SECRET_FILE-unset}" >"$FAKE_RUNTIME_LOG"\n',
        encoding="utf-8",
    )
    granian.chmod(0o755)
    environment = os.environ.copy()
    environment.pop("TELEGRAM_BOT_TOKEN", None)
    environment.pop("TELEGRAM_WEBHOOK_SECRET", None)
    environment.pop("TELEGRAM_SERVICE_SECRET", None)
    environment.update(
        {
            "TELEGRAM_BOT_TOKEN_FILE": str(token_file),
            "TELEGRAM_WEBHOOK_SECRET_FILE": str(webhook_file),
            "TELEGRAM_SERVICE_SECRET_FILE": str(service_file),
            "FAKE_RUNTIME_LOG": str(runtime_log),
            "PATH": f"{binary_dir}:{environment['PATH']}",
        },
    )

    result = subprocess.run(  # noqa: S603
        ["/bin/bash", str(ROOT / "start_application.sh"), "run"],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert runtime_log.read_text(encoding="utf-8") == (
        "123456:BOT_TOKEN\nunset\nWEBHOOK_SECRET\nunset\nSERVICE_SECRET\nunset\n"
    )
