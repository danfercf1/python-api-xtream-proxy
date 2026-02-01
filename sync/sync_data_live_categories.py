import os
import sys
from pathlib import Path
import pymysql
import requests
import logging
import time
from tools import Tools
from requests import RequestException
from dotenv import load_dotenv

# Allow importing from repo root (e.g. database.py)
sys.path.append(str(Path(__file__).resolve().parents[1]))
from database import Database

tool = Tools()

# Load repo .env if present (so USERNAME/PASSWORD changes apply)
_dotenv_override = os.getenv("SYNC_DOTENV_OVERRIDE", "1").strip().lower() in {"1", "true", "yes", "on"}
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env", override=_dotenv_override)

# Allow overriding DNS URL(s) for testing (comma-separated)
DNS_URL_OVERRIDE = os.getenv("DNS_URL", "").strip()
ENABLE_M3U_FALLBACK = os.getenv("ENABLE_M3U_FALLBACK", "0").strip().lower() in {"1", "true", "yes", "on"}

def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def _redact(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "***"
    return value[:2] + "***" + value[-2:]


SYNC_DEBUG = _env_bool("SYNC_DEBUG", False) or _env_bool("DEBUG", False)
UPSTREAM_TIMEOUT_SECONDS = int(os.getenv("UPSTREAM_TIMEOUT_SECONDS", "20"))
SYNC_LOG_EVERY_N = int(os.getenv("SYNC_LOG_EVERY_N", "50"))
SYNC_LOG_SAMPLE_SIZE = int(os.getenv("SYNC_LOG_SAMPLE_SIZE", "10"))

logger = logging.getLogger("sync.live_categories")
if not logger.handlers:
    logger.setLevel(logging.DEBUG if SYNC_DEBUG else logging.INFO)
    fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    sh = logging.StreamHandler()
    sh.setLevel(logging.DEBUG if SYNC_DEBUG else logging.INFO)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    # Only write file logs in debug/local mode to avoid noisy production logs.
    if SYNC_DEBUG:
        fh = logging.FileHandler("sync_live_categories.log")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    logger.propagate = False

# Function to save data to the stream_categories table
def save_to_database(data, db_host, db_user, db_password, db_name):
    inserted = 0
    updated = 0
    try:
        connection = pymysql.connect(host=db_host,
                                     user=db_user,
                                     password=db_password,
                                     database=db_name,
                                     cursorclass=pymysql.cursors.DictCursor)
 
        with connection.cursor() as cursor:
            # Get the current max cat_order to increment from there
            cursor.execute("SELECT MAX(cat_order) as max_order FROM stream_categories")
            result = cursor.fetchone()
            cont = result['max_order'] if result and result['max_order'] is not None else 0
 
            for idx, category in enumerate(data, start=1):
                category_id = int(category['category_id'])
                category_name = category['category_name']
                parent_id = category['parent_id']
 
                if SYNC_DEBUG and SYNC_LOG_EVERY_N > 0 and (idx == 1 or idx % SYNC_LOG_EVERY_N == 0):
                    logger.debug(
                        "Progress %s/%s: category_id=%s name=%s",
                        idx,
                        len(data),
                        category_id,
                        category_name,
                    )

                cursor.execute("SELECT id, category_name FROM stream_categories WHERE id = %s", (category_id,))
                existing_category = cursor.fetchone()
 
                if existing_category:
                    # Update if name is different
                    if existing_category['category_name'] != category_name:
                        cursor.execute("UPDATE stream_categories SET category_name = %s WHERE id = %s", (category_name, category_id))
                        updated += 1
                        if SYNC_DEBUG:
                            logger.debug("Category updated: %s (id=%s)", category_name, category_id)
                else:
                    # Insert new category
                    cont += 1
                    cursor.execute("INSERT INTO stream_categories (id, category_name, parent_id, cat_order) VALUES (%s, %s, %s, %s)", (category_id, category_name, parent_id, cont))
                    inserted += 1
                    if SYNC_DEBUG:
                        logger.debug("Category inserted: %s (id=%s)", category_name, category_id)
            connection.commit()
            logger.info("DB sync complete. Inserted=%s Updated=%s Total=%s", inserted, updated, len(data))
    except pymysql.Error as e:
        logger.error("Error with database operation: %s", e)
    finally:
        if connection:
            connection.close()

if __name__ == '__main__':
    # Get MySQL database connection details from environment variables
    DB_HOST = os.getenv("MYSQL_HOST")
    DB_USER = os.getenv("MYSQL_USER")
    DB_PASSWORD = os.getenv("MYSQL_PASSWORD")
    DB_NAME = os.getenv("MYSQL_DATABASE")

    USER_NAME = os.getenv("USERNAME")
    PASSWORD = os.getenv("PASSWORD")

    logger.info("Starting category sync for user: %s", USER_NAME)
    if SYNC_DEBUG:
        logger.debug("Upstream timeout: %ss", UPSTREAM_TIMEOUT_SECONDS)
        logger.debug("Credentials: username=%s password=%s", USER_NAME, _redact(PASSWORD))

    start_time = time.time()

    # Fetch JSON data from the provided URL
    upstream_ua = os.getenv(
        "UPSTREAM_USER_AGENT",
        "Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/120.0 Mobile Safari/537.36",
    )
    headers = {
        "User-Agent": upstream_ua,
        "Accept": "application/json,text/plain,*/*",
        "Connection": "keep-alive",
    }
    db = Database(None)
    if DNS_URL_OVERRIDE:
        dns_candidates = [u.strip() for u in DNS_URL_OVERRIDE.split(",") if u.strip()]
    else:
        dns_candidates = db.get_dns_urls() or [db.get_dns_url_random()]

    # Try https variants too (some panels reset plain http).
    expanded: list[str] = []
    for u in dns_candidates:
        expanded.append(u.rstrip("/"))
        if u.startswith("http://"):
            expanded.append("https://" + u[len("http://"):].rstrip("/"))
    # de-dupe preserving order
    seen = set()
    dns_candidates = [u for u in expanded if not (u in seen or seen.add(u))]

    logger.info("DNS candidates: %s", dns_candidates)
    response = None
    last_error = None
    for dns_url in dns_candidates[:5]:
        url = f'{dns_url}/player_api.php?username={USER_NAME}&password={PASSWORD}&action=get_live_categories'
        try:
            if SYNC_DEBUG:
                logger.debug("GET %s", url.replace(PASSWORD or "", "***"))
            response = requests.get(url, headers=headers, timeout=UPSTREAM_TIMEOUT_SECONDS, allow_redirects=True, verify=False)
            if response.status_code == 200:
                logger.info("Upstream OK from %s (200)", dns_url)
                break
            logger.warning("Non-200 from %s: %s", dns_url, response.status_code)
        except RequestException as e:
            last_error = e
            logger.warning("Request failed for %s: %s", dns_url, e)
            response = None
            continue

    if response is None:
        raise SystemExit(f"Failed to fetch categories via player_api.php. Last error: {last_error}")
    if response.status_code != 200:
        if not ENABLE_M3U_FALLBACK:
            raise SystemExit(
                f"Failed to fetch categories via player_api.php. Last status: {response.status_code}. "
                "Set ENABLE_M3U_FALLBACK=1 to try get.php playlist fallback."
            )

        # Optional fallback (disabled by default)
        json_data = None
        m3u_last_error = None
        for dns_url in dns_candidates[:5]:
            m3u_url = f"{dns_url}/get.php?username={USER_NAME}&password={PASSWORD}&type=m3u_plus&output=ts"
            try:
                logging.info("Falling back to M3U from: %s", dns_url)
                m3u_resp = requests.get(m3u_url, headers=headers, timeout=30, allow_redirects=True, verify=False)
                if m3u_resp.status_code != 200:
                    logging.warning("Non-200 M3U from %s: %s", dns_url, m3u_resp.status_code)
                    continue
                categories = tool.parse_m3u_categories(m3u_resp.text)
                if categories:
                    json_data = categories
                    break
                logging.warning("Parsed 0 categories from M3U at %s", dns_url)
            except RequestException as e:
                m3u_last_error = e
                logging.warning("M3U request failed for %s: %s", dns_url, e)

        if json_data is None:
            raise SystemExit(
                "Failed to fetch categories via player_api.php; M3U fallback enabled but also failed. "
                f"Last player_api error: {last_error}. Last M3U error: {m3u_last_error}"
            )
    else:
        json_data = response.json()

    logger.info("Fetched %s categories from upstream", len(json_data) if isinstance(json_data, list) else 0)
    if SYNC_DEBUG and isinstance(json_data, list):
        sample = json_data[: max(SYNC_LOG_SAMPLE_SIZE, 0)]
        for i, c in enumerate(sample, start=1):
            try:
                logger.debug(
                    "Sample upstream[%s]: category_id=%s category_name=%s parent_id=%s",
                    i,
                    c.get("category_id"),
                    c.get("category_name"),
                    c.get("parent_id"),
                )
            except Exception:
                logger.debug("Sample upstream[%s]: %r", i, c)

    # Remove categories with specified name
    cleaned_data = tool.remove_categories_by_name(json_data)
    logger.info("After filtering, %s categories remain", len(cleaned_data))

    # Save cleaned data to database
    save_to_database(cleaned_data, DB_HOST, DB_USER, DB_PASSWORD, DB_NAME)

    logger.info("Data processed and saved successfully.")

    end_time = time.time()
    execution_time = end_time - start_time

    minutes = int(execution_time // 60)
    seconds = int(execution_time % 60)

    # Log execution time
    logger.info("Execution time: %s minutes and %s seconds", minutes, seconds)