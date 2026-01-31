#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Backup MariaDB database to ./mysql_backups/

Usage:
  scripts/backup_db.sh [--dev] [--env <path>] [--service <name>] [--container <id|name>] [--output <path>] [--dry-run]

Options:
  --dev            Use docker-compose-dev.yml (default: docker-compose.yml)
  --env <path>     Env file to load (default: ./.env if present, else ./.env.example)
  --service <name> Compose DB service name (default: mariadb)
  --container <x>  Container id/name to exec into (skips compose lookup)
  --output <path>  Output .sql file path (default: mysql_backups/<timestamp>_backup.sql)
  --dry-run        Print the resolved commands without executing

Env vars used (from env file):
  MYSQL_DATABASE, MYSQL_USER, MYSQL_PASSWORD, MYSQL_ROOT_PASSWORD
EOF
}

DEV=0
ENV_PATH=""
SERVICE="mariadb"
CONTAINER=""
OUTPUT=""
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dev) DEV=1; shift ;;
    --env) ENV_PATH="${2:-}"; shift 2 ;;
    --service) SERVICE="${2:-}"; shift 2 ;;
    --container) CONTAINER="${2:-}"; shift 2 ;;
    --output) OUTPUT="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

COMPOSE_FILE="docker-compose.yml"
if [[ "$DEV" == "1" ]]; then
  COMPOSE_FILE="docker-compose-dev.yml"
fi

if [[ -z "$ENV_PATH" ]]; then
  if [[ -f ".env" ]]; then
    ENV_PATH=".env"
  elif [[ -f ".env.example" ]]; then
    ENV_PATH=".env.example"
  else
    echo "No .env or .env.example found. Use --env <path>." >&2
    exit 1
  fi
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Compose file not found: $COMPOSE_FILE" >&2
  exit 1
fi

if [[ ! -f "$ENV_PATH" ]]; then
  echo "Env file not found: $ENV_PATH" >&2
  exit 1
fi

# Load env file (simple KEY=VALUE lines). This is for local/dev only.
set -a
# shellcheck disable=SC1090
source "$ENV_PATH"
set +a

timestamp="$(date +'%Y-%m-%d_%H%M%S')"
mkdir -p "mysql_backups"

if [[ -z "$OUTPUT" ]]; then
  OUTPUT="mysql_backups/${timestamp}_backup.sql"
fi

if [[ -z "${MYSQL_DATABASE:-}" ]]; then
  echo "MYSQL_DATABASE is not set (check your env file: $ENV_PATH)" >&2
  exit 1
fi

db_user="${MYSQL_USER:-root}"
db_pass="${MYSQL_PASSWORD:-${MYSQL_ROOT_PASSWORD:-}}"
if [[ -z "$db_pass" ]]; then
  echo "MYSQL_PASSWORD (or MYSQL_ROOT_PASSWORD) is not set (check your env file: $ENV_PATH)" >&2
  exit 1
fi

compose_base=(docker compose -f "$COMPOSE_FILE" --env-file "$ENV_PATH")

container_id=""
if [[ -n "$CONTAINER" ]]; then
  container_id="$CONTAINER"
else
  # 1) Try the container started by this compose project (fast path)
  container_id="$("${compose_base[@]}" ps -q "$SERVICE" 2>/dev/null || true)"

  # 2) If empty, try any running compose container with the same service label
  if [[ -z "$container_id" ]]; then
    container_id="$(docker ps -q --filter "label=com.docker.compose.service=${SERVICE}" 2>/dev/null | head -n 1 || true)"
  fi

  # 3) If still empty, try matching by container name (contains service)
  if [[ -z "$container_id" ]]; then
    container_id="$(docker ps -q --filter "name=${SERVICE}" 2>/dev/null | head -n 1 || true)"
  fi

  # 4) If still empty, try any mariadb image container
  if [[ -z "$container_id" ]]; then
    container_id="$(docker ps -q --filter "ancestor=mariadb" 2>/dev/null | head -n 1 || true)"
  fi
fi

if [[ -z "$container_id" ]]; then
  echo "Could not find a running MariaDB container." >&2
  echo "If it's running under a different project/name, pass it explicitly:" >&2
  echo "  ./scripts/backup_db.sh --container <container_id_or_name> --env $ENV_PATH" >&2
  echo "Or verify Docker access with: docker ps" >&2
  exit 1
fi

dump_cmd=(docker exec "$container_id" mariadb-dump "-u${db_user}" "-p${db_pass}" "$MYSQL_DATABASE")

if [[ "$DRY_RUN" == "1" ]]; then
  echo "Compose file: $COMPOSE_FILE"
  echo "Env file:     $ENV_PATH"
  echo "Service:      $SERVICE"
  echo "Container:    $container_id"
  echo "Output:       $OUTPUT"
  printf 'Dump cmd:     '
  printf '%q ' "${dump_cmd[@]}"
  echo
  exit 0
fi

umask 077
echo "Writing backup to: $OUTPUT"
"${dump_cmd[@]}" > "$OUTPUT"
echo "Done."

