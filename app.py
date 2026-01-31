from flask import Flask, request, jsonify, redirect, send_file
import os
import time
from threading import Lock
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl
from database import Database
from api import Api

#  TODO EPG action=get_simple_data_table&stream_id=id Perfect player APP

app = Flask(__name__)
db = Database(app)
api = Api(db)

# Obtener las variables de entorno
PORT = os.environ.get('PORT') or 5000

def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "t", "yes", "y", "on"}

DEBUG = _env_bool('DEBUG', False)

# Simple in-process rate limiting (best-effort; for real protection use a reverse proxy).
_RATE_LIMIT_PLAYER_API_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PLAYER_API_PER_MINUTE", "30"))
_RATE_LIMIT_REDIRECT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_REDIRECT_PER_MINUTE", "120"))
_TRUST_PROXY_HEADERS = _env_bool("TRUST_PROXY_HEADERS", False)
_RATE_STATE: dict[tuple[str, str], tuple[float, int]] = {}
_RATE_LOCK = Lock()

def _client_ip() -> str:
    if _TRUST_PROXY_HEADERS:
        # X-Forwarded-For: client, proxy1, proxy2 ...
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            return xff.split(",")[0].strip()
    return request.remote_addr or "unknown"

def _rate_limit(key: str, per_minute: int) -> bool:
    """Return True if allowed, False if rate-limited."""
    if per_minute <= 0:
        return True
    window_seconds = 60.0
    now = time.time()
    ip = _client_ip()
    state_key = (ip, key)
    with _RATE_LOCK:
        window_start, count = _RATE_STATE.get(state_key, (now, 0))
        if now - window_start >= window_seconds:
            window_start, count = now, 0
        count += 1
        _RATE_STATE[state_key] = (window_start, count)
        return count <= per_minute

def _redact_url(url: str) -> str:
    """Redact sensitive query params like username/password."""
    try:
        parts = urlsplit(url)
        if not parts.query:
            return url
        q = []
        for k, v in parse_qsl(parts.query, keep_blank_values=True):
            if k.lower() in {"username", "password"}:
                q.append((k, "***"))
            else:
                q.append((k, v))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q, doseq=True), parts.fragment))
    except Exception:
        return "<redacted>"

def _is_user_active_and_not_expired(user_info: dict) -> bool:
    # Xtream-style payloads typically include: auth (1/0), status ("Active"), exp_date (unix timestamp string)
    try:
        if int(user_info.get("auth", 0)) != 1:
            return False
    except Exception:
        return False
    status = str(user_info.get("status", "")).strip().lower()
    if status and status != "active":
        return False
    exp = user_info.get("exp_date")
    if exp in (None, "", "0", 0):
        # Some panels may omit exp_date; treat missing as valid.
        return True
    try:
        return int(exp) > int(time.time())
    except Exception:
        return False

@app.before_request
def _bot_mitigation_guardrails():
    # Rate limit the noisiest endpoints first.
    if request.path == "/player_api.php":
        if not _rate_limit("player_api", _RATE_LIMIT_PLAYER_API_PER_MINUTE):
            return jsonify({"error": "rate_limited"}), 429
    else:
        # The catch-all redirect is a common bot target (scanners, brute force against stream URLs).
        if request.endpoint == "redirect_url":
            if not _rate_limit("redirect", _RATE_LIMIT_REDIRECT_PER_MINUTE):
                return jsonify({"error": "rate_limited"}), 429

# Endpoints
# Endpoint que redirecciona a otra URL reemplazando la URL original y agregando el resto del path
@app.route("/<path:path_to_complete>")
def redirect_url(path_to_complete):
    # Construir la URL de redirección con la nueva URL y el resto del path
    new_url = api.get_redirect(path_to_complete)
    
    app.logger.info("DNS URL: %s", _redact_url(new_url))

    # Redireccionar a la URL construida
    return redirect(new_url)

@app.route('/xmltv.php')
def servir_archivo_xml():
    # Ruta al archivo XML en tu proyecto
    ruta_archivo_xml = 'xml/guide.xml'
    # Devuelve el archivo XML como respuesta
    return send_file(ruta_archivo_xml, mimetype='text/xml')

@app.route("/player_api.php")
def player_api():
    username = request.args.get("username")
    password = request.args.get("password")
    action = request.args.get("action")
    category_id = request.args.get("category_id")
    vod_id = request.args.get("vod_id")
    series_id = request.args.get("series_id")
    debugger = request.args.get("__debugger__")
    
    if not username or not password:
        return jsonify({"error": "missing_credentials"}), 400

    # Enforce real upstream auth (and cache the result in DB).
    if not db.verify_authentication(username, password):
        response = api.get_user_info(username, password, app)

        if response.status_code != 200:
            return jsonify({"error": "authentication_failed"}), 401

        try:
            payload = response.json()
        except Exception:
            return jsonify({"error": "authentication_failed"}), 401

        user_info = (payload or {}).get("user_info") or {}
        server_info = (payload or {}).get("server_info") or {}

        if not _is_user_active_and_not_expired(user_info):
            return jsonify({"error": "authentication_failed"}), 401

        user_id = db.save_user(username, password)
        db.save_user_server_info(user_id, user_info, server_info)
    
    if not action:
        user = db.get_user(username, password)
        if not user:
            return jsonify({"error": "authentication_failed"}), 401
        
        user_info = db.get_user_server_info(user["id"])
        
        if not user_info:
            response = api.get_user_info(username, password, app)
            if response.status_code != 200:
                return jsonify({"error": "authentication_failed"}), 401
            payload = response.json()
            if not _is_user_active_and_not_expired((payload or {}).get("user_info") or {}):
                return jsonify({"error": "authentication_failed"}), 401
            db.save_user_server_info(user["id"], payload["user_info"], payload["server_info"])
            user_info = {"user_info": payload["user_info"], "server_info": payload["server_info"]}
        else:
            user_info = user_info

        return jsonify(user_info)
    else:
        if action == "get_live_categories":
            categories_from_db = db.get_all_stream_categories()
            return jsonify(categories_from_db)
        elif action == "get_live_streams":
            if category_id:
                live_stream = db.get_all_streams_by_category(category_id)
            else:
                live_stream = db.get_all_streams()

            return jsonify(live_stream)
        else:
            if not debugger:
                if series_id:
                    nueva_url_redireccion = "{}/player_api.php?username={}&password={}&action={}&series_id={}".format(api.get_server_url(), username, password, action, series_id)
                elif vod_id:
                    nueva_url_redireccion = "{}/player_api.php?username={}&password={}&action={}&vod_id={}".format(api.get_server_url(), username, password, action, vod_id)
                else:
                    nueva_url_redireccion = "{}/player_api.php?username={}&password={}&action={}".format(api.get_server_url(), username, password, action)
                
                app.logger.info("Final - DNS URL: %s", _redact_url(nueva_url_redireccion))
                
                # Redireccionar a la URL construida
                return redirect(nueva_url_redireccion)

if __name__ == "__main__":
    app.run(debug=DEBUG, host='0.0.0.0', port=PORT)
