#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
. "$script_dir/common.sh"
cd "$backend_dir"

profile="${1:?profile is required}"
env_file="${2:?environment file path is required}"
baseline_path="${3:-}"

if [ ! -f "$env_file" ]; then
    echo "Environment file does not exist: $env_file" >&2
    exit 2
fi

run_id="$(date -u +%Y%m%dT%H%M%S%N)-$$"
load_env_file "$env_file"

require_var() {
    local name="$1"
    if [ -z "${!name:-}" ]; then
        echo "$name is required. Set it in $env_file or pass it in the environment." >&2
        exit 2
    fi
}

require_var PERFORMANCE_REPORT_DIR
require_var DB_USER
require_var DB_PASSWORD
require_var DB_NAME
report_run_dir="$(create_performance_report_run_dir "$PERFORMANCE_REPORT_DIR" "query-plans")"
base_database_name="$DB_NAME"
project_hash="$(printf '%s' "$run_id" | shasum -a 256 | cut -c1-12)"
compose_project="query-plans-${project_hash}"
compose_file="$script_dir/query_plans.compose.yml"
compose_args=(
    compose
    --project-name "$compose_project"
    --env-file "$env_file"
    -f "$compose_file"
)
query_plan_service_started=0
run_database_created=0
run_database_name=""

cleanup_query_plan_run() {
    local exit_status="$?"
    if [ ! -f "$report_run_dir/summary.md" ]; then
        printf '# Knowledge and Resumes query-plan report\n\n- Query-plan run failed; inspect CI logs.\n' \
            >"$report_run_dir/summary.md"
    fi
    if [ "$run_database_created" = "1" ]; then
        DB_NAME="$base_database_name" PYTHONPATH=src uv run --locked --all-groups \
            python -m performance.query_plans.database drop \
            --database-name "$run_database_name" || true
    fi
    if [ "$query_plan_service_started" = "1" ]; then
        docker "${compose_args[@]}" down -v --remove-orphans || true
    fi
    return "$exit_status"
}
trap cleanup_query_plan_run EXIT

ensure_backend_deps
query_plan_service_started=1
docker "${compose_args[@]}" up -d --wait postgres-query-plans
port_binding="$(docker "${compose_args[@]}" port postgres-query-plans 5432)"
DB_HOST=127.0.0.1
DB_PORT="${port_binding##*:}"
if [[ ! "$DB_PORT" =~ ^[0-9]+$ ]] || [ "$DB_PORT" -lt 1 ] || [ "$DB_PORT" -gt 65535 ]; then
    echo "Docker returned an invalid PostgreSQL port binding." >&2
    exit 2
fi
export DB_HOST DB_PORT
run_database_name="$(
    DB_NAME="$base_database_name" PYTHONPATH=src uv run --locked --all-groups \
        python -m performance.query_plans.database name \
        --base-name "$base_database_name" \
        --run-id "$run_id"
)"
DB_NAME="$base_database_name" PYTHONPATH=src uv run --locked --all-groups \
    python -m performance.query_plans.database create \
    --database-name "$run_database_name"
run_database_created=1
export DB_NAME="$run_database_name"

source_sha="workspace-sha256:$({
    find performance/query_plans -type f -name '*.py' -print
    find src/infra/postgresql/models/knowledge -type f -name '*.py' -print
    printf '%s\n' \
        src/infra/postgresql/alembic/versions/0001_initial_schema.py \
        src/infra/postgresql/models/files.py \
        src/infra/postgresql/models/resumes.py \
        src/infra/postgresql/storages/knowledge/dates.py \
        src/infra/postgresql/storages/knowledge/files.py \
        src/infra/postgresql/storages/knowledge/items.py \
        src/infra/postgresql/storages/knowledge/people.py \
        src/infra/postgresql/storages/resumes.py
    printf '%s\n' \
        scripts/run_query_plans.sh \
        scripts/build_query_plan_baseline.sh \
        scripts/query_plans.compose.yml
} | sort | xargs shasum -a 256 | shasum -a 256 | cut -d ' ' -f 1)"

runner_args=(
    --profile "$profile"
    --report-dir "$report_run_dir"
    --run-id "$run_id"
    --source-sha "$source_sha"
)
if [ -n "$baseline_path" ]; then
    runner_args+=(--baseline "$baseline_path")
fi
PYTHONUNBUFFERED=1 PYTHONPATH=src uv run --locked --all-groups \
    python -m performance.query_plans "${runner_args[@]}"
