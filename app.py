from flask import Flask, request, jsonify, redirect, send_file, after_this_request
import os
import re
import time
from threading import Lock
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl, quote
from dotenv import load_dotenv
from database import Database
from api import Api
from proxy_utils import UpstreamProxy, should_use_proxy_mode

#  TODO EPG action=get_simple_data_table&stream_id=id Perfect player APP

# Load local .env if present (does not override existing env vars)
load_dotenv()

app = Flask(__name__)

# Security: Add security headers to all responses
@app.after_request
def add_security_headers(response):
    # Prevent MIME type sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # Prevent clickjacking
    response.headers['X-Frame-Options'] = 'DENY'
    # Basic XSS protection for older browsers
    response.headers['X-XSS-Protection'] = '1; mode=block'
    # Referrer policy
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    # Content Security Policy (adjust as needed for your use case)
    # Note: Xtream Codes players may need specific CSP adjustments
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'none'; object-src 'none'"
    # Remove server fingerprinting
    response.headers.pop('Server', None)
    return response


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

# Proxy mode configuration
# When enabled, gateway proxies requests to upstream instead of redirecting.
# This hides credentials from client logs but increases bandwidth usage.
PROXY_MODE_ENABLED = _env_bool('PROXY_MODE_ENABLED', False)

# Security: Audit logging configuration
AUDIT_LOG_ENABLED = _env_bool('AUDIT_LOG_ENABLED', True)

def _audit_log(event_type: str, username: str | None = None, details: dict | None = None):
    """Log security-relevant events for audit purposes."""
    if not AUDIT_LOG_ENABLED:
        return
    ip = _client_ip()
    user_str = f"user='{username}' " if username else ""
    details_str = f" details={details}" if details else ""
    app.logger.warning("AUDIT: event='%s' %sclient_ip='%s'%s", event_type, user_str, ip, details_str)

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
    # Security: Validate path before processing
    try:
        # Construir la URL de redirección con la nueva URL y el resto del path
        new_url = api.get_redirect(path_to_complete)
    except ValueError as e:
        app.logger.warning("Blocked suspicious redirect attempt: %s - path: %s", str(e), path_to_complete)
        return jsonify({"error": "invalid_path"}), 400
    
    # Proxy mode: Hide upstream URL and credentials from client
    # This prevents credentials from appearing in client logs/browser history
    if PROXY_MODE_ENABLED and should_use_proxy_mode(path_to_complete):
        app.logger.info("Proxying to upstream (hiding URL from client): %s", _redact_url(new_url))
        proxy = UpstreamProxy(api.get_server_url())
        return proxy.proxy_request(
            method=request.method,
            path=path_to_complete,
            params=request.args.to_dict()
        )
    
    # Redirect mode: Client sees upstream URL (Xtream standard behavior)
    app.logger.info("Redirecting to: %s", _redact_url(new_url))
    return redirect(new_url)

@app.route('/xmltv.php')
def servir_archivo_xml():
    # Security: Use absolute path and validate it's within allowed directory
    import os
    base_dir = os.path.abspath(os.path.dirname(__file__))
    xml_dir = os.path.join(base_dir, 'xml')
    ruta_archivo_xml = os.path.join(xml_dir, 'guide.xml')
    
    # Ensure the resolved path is within the allowed xml directory (prevent path traversal)
    real_path = os.path.realpath(ruta_archivo_xml)
    real_xml_dir = os.path.realpath(xml_dir)
    if not real_path.startswith(real_xml_dir + os.sep) and real_path != real_xml_dir:
        return jsonify({"error": "invalid_path"}), 403
    
    # Ensure file exists and is a file
    if not os.path.isfile(real_path):
        return jsonify({"error": "file_not_found"}), 404
    
    # Devuelve el archivo XML como respuesta
    return send_file(real_path, mimetype='text/xml')

@app.route("/health")
def health_check():
    """Health check endpoint for Docker and monitoring."""
    try:
        # Check database connectivity
        db.connect()
        return jsonify({"status": "healthy", "database": "connected"}), 200
    except Exception as e:
        app.logger.error("Health check failed: %s", e)
        return jsonify({"status": "unhealthy", "database": "disconnected"}), 503

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
        _audit_log('auth_missing_credentials', username)
        return jsonify({"error": "missing_credentials"}), 400

    # Enforce real upstream auth (and cache the result in DB).
    if not db.verify_authentication(username, password):
        response = api.get_user_info(username, password, app)

        if response.status_code != 200:
            _audit_log('auth_failed_upstream', username, {'status_code': response.status_code})
            return jsonify({"error": "authentication_failed"}), 401

        try:
            payload = response.json()
        except Exception:
            _audit_log('auth_failed_invalid_response', username)
            return jsonify({"error": "authentication_failed"}), 401

        user_info = (payload or {}).get("user_info") or {}
        server_info = (payload or {}).get("server_info") or {}

        if not _is_user_active_and_not_expired(user_info):
            _audit_log('auth_failed_inactive_or_expired', username, {
                'status': user_info.get('status'),
                'exp_date': user_info.get('exp_date')
            })
            return jsonify({"error": "authentication_failed"}), 401

        _audit_log('auth_success_new_user', username)
        user_id = db.save_user(username, password)
        db.save_user_server_info(user_id, user_info, server_info)
    else:
        _audit_log('auth_success_cached', username)
    
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
                # Security: Validate action parameter to prevent injection
                if not re.match(r'^[a-zA-Z0-9_]+$', action):
                    return jsonify({"error": "invalid_action"}), 400
                
                # Security: URL-encode parameters to prevent URL injection
                base_url = api.get_server_url()
                params = {
                    'username': username,
                    'password': password,
                    'action': action
                }
                if series_id:
                    # Validate series_id is numeric
                    if not re.match(r'^\d+$', str(series_id)):
                        return jsonify({"error": "invalid_series_id"}), 400
                    params['series_id'] = series_id
                elif vod_id:
                    # Validate vod_id is numeric
                    if not re.match(r'^\d+$', str(vod_id)):
                        return jsonify({"error": "invalid_vod_id"}), 400
                    params['vod_id'] = vod_id
                
                # Proxy mode: Hide upstream URL and credentials from client
                if PROXY_MODE_ENABLED:
                    app.logger.info("Proxying player_api action to upstream: %s", action)
                    proxy = UpstreamProxy(base_url)
                    return proxy.proxy_request(
                        method=request.method,
                        path='/player_api.php',
                        params=params
                    )
                
                # Redirect mode: Client sees upstream URL (Xtream standard behavior)
                nueva_url_redireccion = f"{base_url}/player_api.php?{urlencode(params)}"
                app.logger.info("Final - DNS URL: %s", _redact_url(nueva_url_redireccion))
                return redirect(nueva_url_redireccion)

if __name__ == "__main__":
    app.run(debug=DEBUG, host='0.0.0.0', port=PORT)
