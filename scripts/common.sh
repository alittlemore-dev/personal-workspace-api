#!/usr/bin/env bash

backend_script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
backend_dir="$(cd -- "${backend_script_dir}/.." && pwd)"
repo_dir="$(cd -- "${backend_dir}" && pwd)"

# shellcheck source=test_services.sh
. "${script_dir}/test_services.sh"

require_uv() {
    if ! command -v uv >/dev/null 2>&1; then
        echo "UV could not be found." >&2
        exit 2
    fi
}

ensure_backend_deps() {
    local marker=".venv/.self-contained-all-groups"
    local expected_entrypoint_prefix="#!${backend_dir}/.venv/bin/"
    local installed_entrypoint_prefix=""
    local reinstall_entrypoints=false

    require_uv

    if [ -f .venv/bin/pip-audit ]; then
        IFS= read -r installed_entrypoint_prefix < .venv/bin/pip-audit
        if [[ "$installed_entrypoint_prefix" != "$expected_entrypoint_prefix"* ]]; then
            reinstall_entrypoints=true
        fi
    fi

    if [ -x .venv/bin/python ] \
        && [ -f "$marker" ] \
        && [ ! pyproject.toml -nt "$marker" ] \
        && [ ! uv.lock -nt "$marker" ] \
        && [ "$reinstall_entrypoints" = false ]; then
        return
    fi

    if [ "$reinstall_entrypoints" = true ]; then
        uv sync --locked --all-groups --reinstall
    else
        uv sync --locked --all-groups
    fi
    mkdir -p .venv
    touch "$marker"
}

invalidate_backend_deps_marker() {
    rm -f .venv/.self-contained-all-groups
}

performance_report_timestamp() {
    date -u +"%Y%m%dT%H%M%SZ"
}

create_performance_report_run_dir() {
    local report_root="$1"
    local report_type="$2"
    local timestamp
    local report_type_dir
    local candidate
    local suffix

    timestamp="$(performance_report_timestamp)"
    report_type_dir="${report_root%/}/${report_type}"
    candidate="${report_type_dir}/${timestamp}"
    suffix=2

    mkdir -p "$report_type_dir"
    while ! mkdir "$candidate" 2>/dev/null; do
        candidate="${report_type_dir}/${timestamp}-${suffix}"
        suffix=$((suffix + 1))
    done

    printf '%s\n' "$candidate"
}

run_with_test_env() {
    # Intentional word splitting preserves the previous Makefile's KEY=value override form.
    env ${TEST_ENV_OVERRIDES:-} PYTHONPATH=src APP_USE_CACHE=false "$@"
}

ensure_backend_test_db() {
    local compose_file="${1:-docker-compose.test.yml}"
    local forced_port="${2:-}"

    ensure_test_db "$TEST_ENV_FILE" "$compose_file" "$forced_port"
}
