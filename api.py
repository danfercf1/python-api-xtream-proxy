import os
import re
import socket
import ipaddress
import requests
from urllib.parse import urlparse

DEFAULT_UPSTREAM_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Version/4.0 Chrome/120.0 Mobile Safari/537.36"
)

# SSRF protection: Blocked IP ranges that should never be accessed
BLOCKED_IP_PREFIXES = [
    '127.',        # Loopback
    '10.',         # Private Class A
    '172.16.', '172.17.', '172.18.', '172.19.', '172.20.',  # Private Class B
    '172.21.', '172.22.', '172.23.', '172.24.', '172.25.',
    '172.26.', '172.27.', '172.28.', '172.29.', '172.30.', '172.31.',
    '192.168.',    # Private Class C
    '169.254.',    # Link-local
    '0.',          # Current network
    '255.',        # Broadcast
    '::1',         # IPv6 loopback
    'fc00:', 'fd00:',  # IPv6 private
    'fe80:',       # IPv6 link-local
]


def _is_blocked_host(hostname):
    """Check if hostname resolves to a blocked/internal IP address (SSRF protection)."""
    try:
        # Check if it's already an IP address
        ip = ipaddress.ip_address(hostname)
        # Block all private, loopback, and reserved IPs
        return ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_multicast
    except ValueError:
        # It's a hostname, resolve it
        pass
    
    # Check if hostname itself looks like an IP or internal service
    for prefix in BLOCKED_IP_PREFIXES:
        if hostname.startswith(prefix):
            return True
    
    # Common internal/metadata service hostnames to block
    blocked_hosts = [
        'localhost',
        'metadata.google.internal',
        'metadata',
        'instance-data',
        '169.254.169.254',  # Cloud metadata services
    ]
    if hostname.lower() in blocked_hosts:
        return True
    
    try:
        # Resolve hostname and check resolved IPs
        resolved_ips = socket.getaddrinfo(hostname, None)
        for _, _, _, _, sockaddr in resolved_ips:
            ip_str = sockaddr[0]
            try:
                ip = ipaddress.ip_address(ip_str)
                if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_multicast:
                    return True
            except ValueError:
                continue
    except socket.gaierror:
        # If we can't resolve, be cautious but don't block
        pass
    
    return False


def validate_dns_url(url):
    """Validate DNS URL to prevent SSRF attacks."""
    if not url:
        raise ValueError("DNS URL cannot be empty")
    
    # Must start with http:// or https://
    if not (url.startswith('http://') or url.startswith('https://')):
        raise ValueError("DNS URL must start with http:// or https://")
    
    parsed = urlparse(url)
    hostname = parsed.hostname
    
    if not hostname:
        raise ValueError("DNS URL must have a valid hostname")
    
    # Block internal/blocked hosts
    if _is_blocked_host(hostname):
        raise ValueError(f"DNS URL hostname '{hostname}' is not allowed (SSRF protection)")
    
    return url


class Api:
    def __init__(self, db):
        dns_url = db.get_dns_url_random() # Esta función debería obtener una URL aleatoria de la tabla server_dns
        # Security: Validate DNS URL to prevent SSRF
        try:
            self.dns_url = validate_dns_url(dns_url)
        except ValueError as e:
            raise ValueError(f"Invalid DNS URL configured: {e}")
        self.timeout = int(os.getenv("UPSTREAM_TIMEOUT_SECONDS", "20"))
        self.user_agent = os.getenv("UPSTREAM_USER_AGENT", DEFAULT_UPSTREAM_USER_AGENT)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept": "application/json,text/plain,*/*",
                "Connection": "keep-alive",
            }
        )
    
    def get_user_info(self, username, password, app):
        app.logger.info('DNS URL: {}'.format(self.dns_url))

        # Realizar la solicitud HTTP con los datos de usuario a la URL obtenida
        response = self.session.get(
            self.dns_url + '/player_api.php',
            params={'username': username, 'password': password},
            timeout=self.timeout,
        )
        
        return response
    
    def get_categories(self, username, password):
        response = self.session.get(
            self.dns_url + '/player_api.php',
            params={'username': username, 'password': password, 'action': 'get_live_categories'},
            timeout=self.timeout,
        )
        
        return response
    
    def get_redirect(self, path):
        # Security: Validate path to prevent open redirects and path traversal
        import re
        # Remove any leading/trailing slashes and prevent path traversal
        path = path.strip('/')
        # Block paths that try to traverse outside (..) or contain full URLs
        if '..' in path or path.startswith('http://') or path.startswith('https://'):
            # Return a safe default or raise an error
            raise ValueError("Invalid path: path traversal or URL not allowed")
        # Block common malicious patterns
        if re.search(r'[<>":|?*\x00-\x1f]', path):
            raise ValueError("Invalid path: illegal characters")
        redirect_url = self.dns_url + '/' + path
        return redirect_url
    
    def get_server_url(self):
        return self.dns_url
   
