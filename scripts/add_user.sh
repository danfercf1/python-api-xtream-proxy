#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Add a user row to the MariaDB "users" table.

Usage:
  scripts/add_user.sh --username <u> --password <p> [--env <path>] [--dev] [--service <name>] [--container <id|name>] [--dry-run]

Options:
  --username <u>    Username to add
  --password <p>    Password to add
  --env <path>      Env file to load (default: ./.env if present, else ./.env.example)
  --dev             Use docker-compose-dev.yml (default: docker-compose.yml)
  --service <name>  Compose DB service name (default: mariadb)
  --container <x>   Container id/name to exec into (skips compose lookup)
  --dry-run         Print the resolved commands without executing

Env vars used (from env file):
  MYSQL_DATABASE, MYSQL_USER, MYSQL_PASSWORD, MYSQL_ROOT_PASSWORD
EOF
}

DEV=0
ENV_PATH=""
SERVICE="mariadb"
CONTAINER=""
DRY_RUN=0
USERNAME=""
PASSWORD=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dev) DEV=1; shift ;;
    --env) ENV_PATH="${2:-}"; shift 2 ;;
    --service) SERVICE="${2:-}"; shift 2 ;;
    --container) CONTAINER="${2:-}"; shift 2 ;;
    --username) USERNAME="${2:-}"; shift 2 ;;
    --password) PASSWORD="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$USERNAME" || -z "$PASSWORD" ]]; then
  echo "Missing --username / --password" >&2
  usage
  exit 2
fi

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

if [[ ! -f "$ENV_PATH" ]]; then
  echo "Env file not found: $ENV_PATH" >&2
  exit 1
fi

# Load env file (simple KEY=VALUE lines). This is for local/dev only.
set -a
# shellcheck disable=SC1090
source "$ENV_PATH"
set +a

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
  container_id="$("${compose_base[@]}" ps -q "$SERVICE" 2>/dev/null || true)"
  if [[ -z "$container_id" ]]; then
    container_id="$(docker ps -q --filter "label=com.docker.compose.service=${SERVICE}" 2>/dev/null | head -n 1 || true)"
  fi
  if [[ -z "$container_id" ]]; then
    container_id="$(docker ps -q --filter "name=${SERVICE}" 2>/dev/null | head -n 1 || true)"
  fi
  if [[ -z "$container_id" ]]; then
    container_id="$(docker ps -q --filter "ancestor=mariadb" 2>/dev/null | head -n 1 || true)"
  fi
fi

if [[ -z "$container_id" ]]; then
  echo "Could not find a running MariaDB container." >&2
  echo "Pass it explicitly:" >&2
  echo "  ./scripts/add_user.sh --container <container_id_or_name> --env $ENV_PATH --username <u> --password <p>" >&2
  exit 1
fi

sql=$(
  cat <<'SQL'
SET @u := %s;
SET @p := %s;

-- Create a user row if it doesn't exist (by username+password)
INSERT INTO users (username, password)
SELECT @u, @p
WHERE NOT EXISTS (
  SELECT 1 FROM users WHERE username = @u AND password = @p
);

-- If the table has a 'status' column, set it to Active.
SET @has_status := (
  SELECT COUNT(*)
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'users'
    AND column_name = 'status'
);

SET @q := IF(
  @has_status > 0,
  CONCAT("UPDATE users SET status='Active' WHERE username = ", QUOTE(@u), " AND password = ", QUOTE(@p)),
  "SELECT 1"
);
PREPARE stmt FROM @q;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SELECT id, username FROM users WHERE username = @u AND password = @p LIMIT 1;
SQL
)

# Use mariadb client inside the container. Provide SQL via stdin.
cmd=(docker exec -i "$container_id" mariadb "-u${db_user}" "-p${db_pass}" "$MYSQL_DATABASE")

if [[ "$DRY_RUN" == "1" ]]; then
  echo "Env file:   $ENV_PATH"
  echo "Service:    $SERVICE"
  echo "Container:  $container_id"
  printf 'Cmd:        '
  printf '%q ' "${cmd[@]}"
  echo
  echo "SQL: (redacted username/password)"
  exit 0
fi

# Escape username/password safely for SQL by passing them as printf %q? Instead use mariadb's QUOTE via variables:
# We pass as SQL literals by replacing the two %s placeholders with QUOTED strings using printf and %q is shell, not SQL.
# Here we build safe SQL literals by using mysql/mariadb QUOTE() is not available outside SQL, so we do minimal escaping.
escape_sql_literal() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\'/\\\'}"
  printf "'%s'" "$s"
}

u_lit="$(escape_sql_literal "$USERNAME")"
p_lit="$(escape_sql_literal "$PASSWORD")"

final_sql="$(printf "$sql" "$u_lit" "$p_lit")"

echo "$final_sql" | "${cmd[@]}"
echo "Done."

