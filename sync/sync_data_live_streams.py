import re
import sys
from pathlib import Path
import pymysql
import requests
import os
import time
import logging
from requests import RequestException
from tools import Tools
from dotenv import load_dotenv

# Allow importing from repo root (e.g. database.py)
sys.path.append(str(Path(__file__).resolve().parents[1]))
from database import Database

# Load repo .env if present (so USERNAME/PASSWORD changes apply)
_dotenv_override = os.getenv("SYNC_DOTENV_OVERRIDE", "1").strip().lower() in {"1", "true", "yes", "on"}
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env", override=_dotenv_override)

# For M3U fallback parsing
tool = Tools()

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
SYNC_LOG_EVERY_N = int(os.getenv("SYNC_LOG_EVERY_N", "100"))
SYNC_LOG_SAMPLE_SIZE = int(os.getenv("SYNC_LOG_SAMPLE_SIZE", "10"))

logger = logging.getLogger("sync.live_streams")
if not logger.handlers:
    logger.setLevel(logging.DEBUG if SYNC_DEBUG else logging.INFO)
    fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    sh = logging.StreamHandler()
    sh.setLevel(logging.DEBUG if SYNC_DEBUG else logging.INFO)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    if SYNC_DEBUG:
        fh = logging.FileHandler("sync_live_streams.log")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    logger.propagate = False

# Text patterns to remove from name
patterns_to_remove = [
    r'OL\| US LATIN ',
    r'LA: ',
    r'MX\| ',
    r'MXC: ',
    r'LATINO \| ',
    r'US\| \(LATIN\) ',
    r'LATIN ',
    r'LATIN  ',
    r'CLARO\| ',
    r'ARG\| ',
    r'PE\| ',
    r'US\| ',
    r'UY\| ',
    r'\| '
]

# Function to remove text patterns from a name
def remove_patterns(name):
    for pattern in patterns_to_remove:
        name = re.sub(pattern, '', name)
    return name.strip()

STREAM_SKIP_NAME_REGEX = os.getenv("STREAM_SKIP_NAME_REGEX", r"^#+\s*.+\s*#+$").strip()
_stream_skip_name_re = re.compile(STREAM_SKIP_NAME_REGEX)

def is_skip_stream(item: dict) -> bool:
    """Return True if the stream looks like a category separator/header."""
    name = (item.get("name") or "").strip()
    if not name:
        return True
    if _stream_skip_name_re.match(name):
        return True
    return False

# Function to connect to the database and save data
def save_to_database(data, allowed_category_ids, db_host, db_user, db_password, db_name):
    if not data:
        logger.warning("No streams received; nothing to save.")
        return
    # Remove non-stream "header" rows (e.g. ###### ECUADOR ######)
    before = len(data)
    data = [s for s in data if not is_skip_stream(s)]
    skipped = before - len(data)
    if skipped:
        logger.info("Skipped %s non-stream rows (header/separator)", skipped)
        if SYNC_DEBUG and skipped <= 50:
            for s in [x for x in data[:0]]:  # keep structure; no-op
                pass
    inserted = 0
    updated = 0
    preserved_category = 0
    try:
        connection = pymysql.connect(host=db_host,
                                     user=db_user,
                                     password=db_password,
                                     database=db_name,
                                     cursorclass=pymysql.cursors.DictCursor)

        with connection.cursor() as cursor:
            for idx, item in enumerate(data, start=1):
                new_name = remove_patterns(item['name'])
                if SYNC_DEBUG and SYNC_LOG_EVERY_N > 0 and (idx == 1 or idx % SYNC_LOG_EVERY_N == 0):
                    logger.debug(
                        "Progress %s/%s: stream_id=%s name=%s category_id=%s",
                        idx,
                        len(data),
                        item.get("stream_id"),
                        item.get("name"),
                        item.get("category_id"),
                    )
                cursor.execute("SELECT * FROM streams WHERE stream_id=%s", (item['stream_id'],))
                existing_item = cursor.fetchone()
                incoming_category_id = item.get("category_id")
                try:
                    cursor.execute("SELECT * FROM stream_categories WHERE id=%s", (incoming_category_id,))
                    existing_category = cursor.fetchone()
                except Exception:
                    existing_category = None
                
                # Decide which category_id to store:
                # - If the existing DB row is in a protected category, keep it.
                # - Otherwise, use the upstream category if it exists in DB, else fallback to 1153.
                if existing_item and existing_item.get("category_id") in allowed_category_ids:
                    category_to_store = existing_item["category_id"]
                    preserved_category += 1
                else:
                    if existing_category is None:
                        category_to_store = 1153
                    else:
                        category_to_store = incoming_category_id

                if existing_item:
                    # Always refresh core fields by stream_id.
                    cursor.execute(
                        "UPDATE streams SET added=%s, category_id=%s, custom_sid=%s, direct_source=%s, epg_channel_id=%s, is_adult=%s, num=%s, stream_icon=%s, name=%s, stream_type=%s, tv_archive=%s, tv_archive_duration=%s WHERE stream_id=%s",
                        (
                            item.get("added"),
                            category_to_store,
                            item.get("custom_sid"),
                            item.get("direct_source"),
                            item.get("epg_channel_id"),
                            item.get("is_adult"),
                            item.get("num"),
                            item.get("stream_icon"),
                            new_name,
                            item.get("stream_type"),
                            item.get("tv_archive"),
                            item.get("tv_archive_duration"),
                            item["stream_id"],
                        ),
                    )
                    updated += 1
                    if SYNC_DEBUG:
                        logger.debug(
                            "Stream updated: id=%s name=%s category_id=%s%s",
                            item["stream_id"],
                            new_name,
                            category_to_store,
                            " (preserved)" if existing_item.get("category_id") in allowed_category_ids else "",
                        )
                else:
                    cursor.execute("INSERT INTO streams (name, added, category_id, custom_sid, direct_source, epg_channel_id, is_adult, num, stream_icon, stream_id, stream_type, tv_archive, tv_archive_duration) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                                   (new_name, item.get('added'), category_to_store, item.get('custom_sid'), item.get('direct_source'), item.get('epg_channel_id'), item.get('is_adult'), item.get('num'), item.get('stream_icon'), item['stream_id'], item.get('stream_type'), item.get('tv_archive'), item.get('tv_archive_duration')))
                    inserted += 1
                    if SYNC_DEBUG:
                        logger.debug("Stream inserted: id=%s name=%s", item["stream_id"], new_name)
            connection.commit()
            logger.info(
                "DB sync complete. Inserted=%s Updated=%s PreservedCategory=%s Total=%s",
                inserted,
                updated,
                preserved_category,
                len(data),
            )
    except pymysql.Error as e:
        logger.error("Error connecting to database: %s", e)
    finally:
        if connection:
            connection.close()

# Define the allowed category IDs for updating
allowed_category_ids = {1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,33}

# Function to fetch JSON data from external server
def fetch_json_data(username, password):
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

    last_error = None
    for dns_url in dns_candidates[:5]:
        url = '{}/player_api.php?username={}&password={}&action=get_live_streams'.format(dns_url, username, password)
        try:
            if SYNC_DEBUG:
                logger.debug("GET %s", url.replace(password or "", "***"))
            logger.info("Fetching streams from: %s", dns_url)
            response = requests.get(url, headers=headers, timeout=UPSTREAM_TIMEOUT_SECONDS, allow_redirects=True, verify=False)
            if response.status_code == 200:
                logger.info("Upstream OK from %s (200)", dns_url)
                payload = response.json()
                logger.info("Fetched %s streams from upstream", len(payload) if isinstance(payload, list) else 0)
                if SYNC_DEBUG and isinstance(payload, list):
                    sample = payload[: max(SYNC_LOG_SAMPLE_SIZE, 0)]
                    for i, s in enumerate(sample, start=1):
                        try:
                            logger.debug(
                                "Sample upstream[%s]: stream_id=%s name=%s category_id=%s direct_source=%s",
                                i,
                                s.get("stream_id"),
                                s.get("name"),
                                s.get("category_id"),
                                (s.get("direct_source") or "")[:120],
                            )
                        except Exception:
                            logger.debug("Sample upstream[%s]: %r", i, s)
                return payload
            logger.warning("Non-200 from %s: %s", dns_url, response.status_code)
        except RequestException as e:
            last_error = e
            logger.warning("Request failed for %s: %s", dns_url, e)
            continue

    if not ENABLE_M3U_FALLBACK:
        logger.error("Failed to fetch streams via player_api.php. Last error: %s", last_error)
        return None

    # Optional fallback: try M3U playlist download and parse streams from it.
    m3u_last_error = None
    for dns_url in dns_candidates[:5]:
        m3u_url = f"{dns_url}/get.php?username={username}&password={password}&type=m3u_plus&output=ts"
        try:
            logger.info("Falling back to M3U from: %s", dns_url)
            m3u_resp = requests.get(m3u_url, headers=headers, timeout=max(UPSTREAM_TIMEOUT_SECONDS, 30), allow_redirects=True, verify=False)
            if m3u_resp.status_code != 200:
                logger.warning("Non-200 M3U from %s: %s", dns_url, m3u_resp.status_code)
                continue
            categories = tool.parse_m3u_categories(m3u_resp.text)
            cat_map = {c["category_name"]: c["category_id"] for c in categories}
            streams = tool.parse_m3u_streams(m3u_resp.text, cat_map)
            if streams:
                return streams
            logger.warning("Parsed 0 streams from M3U at %s", dns_url)
        except RequestException as e:
            m3u_last_error = e
            logger.warning("M3U request failed for %s: %s", dns_url, e)

    logger.error(
        "Failed to fetch JSON data via player_api.php and M3U fallback. "
        f"Last player_api error: {last_error}. Last M3U error: {m3u_last_error}"
    )
    return None

# Get MySQL database connection details from environment variables
DB_HOST = os.getenv("MYSQL_HOST")
DB_USER = os.getenv("MYSQL_USER")
DB_PASSWORD = os.getenv("MYSQL_PASSWORD")
DB_NAME = os.getenv("MYSQL_DATABASE")

USER_NAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")

logger.info("Starting streams sync for user: %s", USER_NAME)
if SYNC_DEBUG:
    logger.debug("Upstream timeout: %ss", UPSTREAM_TIMEOUT_SECONDS)
    logger.debug("Credentials: username=%s password=%s", USER_NAME, _redact(PASSWORD))

start_time = time.time()

# Fetch JSON data
json_data = fetch_json_data(USER_NAME, PASSWORD)

# Save to database
save_to_database(json_data, allowed_category_ids, DB_HOST, DB_USER, DB_PASSWORD, DB_NAME)

end_time = time.time()
execution_time = end_time - start_time

minutes = int(execution_time // 60)
seconds = int(execution_time % 60)

logger.info("Data saved to database.")
logger.info("Execution time: %s minutes and %s seconds", minutes, seconds)
