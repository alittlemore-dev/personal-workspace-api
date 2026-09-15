import os
import subprocess
from pathlib import Path


def write_executable(*, path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


class TestQueryPlanScriptLifecycle:
    def test_concurrent_cold_runs_own_distinct_services_and_always_report_cleanup(
        self,
        tmp_path: Path,
    ) -> None:
        fake_bin = tmp_path / "bin"
        fake_bin.mkdir()
        docker_log = tmp_path / "docker.log"
        report_root = tmp_path / "reports"
        env_file = tmp_path / "test.env"
        env_file.write_text(
            "\n".join(
                (
                    "DB_USER=postgres",
                    "DB_PASSWORD=postgres",
                    "DB_DRIVER=postgresql+psycopg",
                    "DB_HOST=127.0.0.1",
                    "DB_PORT=1",
                    "DB_NAME=query_script_test",
                    f"PERFORMANCE_REPORT_DIR={report_root}",
                ),
            ),
            encoding="utf-8",
        )
        write_executable(
            path=fake_bin / "docker",
            content="""#!/usr/bin/env bash
set -euo pipefail
project=""
for ((index=1; index <= $#; index++)); do
    if [ "${!index}" = "--project-name" ]; then
        next=$((index + 1))
        project="${!next}"
    fi
done
case " $* " in
    *" up "*) printf 'up %s\n' "$project" >>"$FAKE_DOCKER_LOG" ;;
    *" port "*) printf '127.0.0.1:49123\n' ;;
    *" down "*) printf 'down %s\n' "$project" >>"$FAKE_DOCKER_LOG" ;;
esac
""",
        )
        write_executable(
            path=fake_bin / "uv",
            content="""#!/usr/bin/env bash
set -euo pipefail
case " $* " in
    *" performance.query_plans.database name "*)
        printf 'query_script_test_query_plans_aaaaaaaaaaaa\n'
        ;;
    *" performance.query_plans "*) exit 17 ;;
esac
""",
        )
        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{fake_bin}:{environment['PATH']}",
                "FAKE_DOCKER_LOG": str(docker_log),
            },
        )
        command = (
            "bash",
            "scripts/run_query_plans.sh",
            "realistic",
            str(env_file),
            "",
        )

        processes = tuple(
            subprocess.Popen(  # noqa: S603
                command,
                cwd=Path(__file__).parents[3],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for _ in range(2)
        )
        results = tuple(process.communicate(timeout=15) for process in processes)

        assert all(process.returncode == 17 for process in processes), results
        lifecycle = docker_log.read_text(encoding="utf-8").splitlines()
        started_projects = {
            line.removeprefix("up ") for line in lifecycle if line.startswith("up ")
        }
        stopped_projects = {
            line.removeprefix("down ") for line in lifecycle if line.startswith("down ")
        }
        assert len(started_projects) == 2
        assert stopped_projects == started_projects
        summaries = tuple(report_root.glob("query-plans/*/summary.md"))
        assert len(summaries) == 2
        assert all("run failed" in path.read_text(encoding="utf-8") for path in summaries)
