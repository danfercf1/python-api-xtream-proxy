"""
Proxy utilities for transparent upstream communication.
Instead of redirecting clients to upstream, proxy the requests to hide credentials in URLs.
"""
import os
import requests
from flask import Response, stream_with_context


class UpstreamProxy:
    """Proxy requests to upstream server to hide credentials from clients.
    
    Instead of:
      Client -> 302 Redirect -> Upstream (credentials visible in URL)
    
    Use proxy mode:
      Client -> Gateway -> Upstream (credentials only in gateway-upstream hop)
    """
    
    def __init__(self, upstream_base_url: str, timeout: int = 30):
        self.upstream_base_url = upstream_base_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": os.getenv(
                "UPSTREAM_USER_AGENT",
                "Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/120.0 Mobile Safari/537.36"
            ),
            "Accept": "*/*",
            "Connection": "keep-alive",
        })
    
    def proxy_request(self, method: str, path: str, params: dict = None, 
                      headers: dict = None, data=None, stream: bool = True) -> Response:
        """Proxy a request to upstream server.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            path: Path on upstream server
            params: Query parameters (will be encoded)
            headers: Additional headers to send
            data: Request body data
            stream: Whether to stream the response
            
        Returns:
            Flask Response object
        """
        url = f"{self.upstream_base_url}/{path.lstrip('/')}"
        
        # Merge headers
        request_headers = dict(self.session.headers)
        if headers:
            request_headers.update(headers)
        
        # Remove hop-by-hop headers that shouldn't be forwarded
        hop_by_hop = ['connection', 'keep-alive', 'proxy-authenticate', 
                      'proxy-authorization', 'te', 'trailers', 'transfer-encoding', 'upgrade']
        request_headers = {k: v for k, v in request_headers.items() 
                          if k.lower() not in hop_by_hop}
        
        try:
            upstream_response = self.session.request(
                method=method,
                url=url,
                params=params,
                headers=request_headers,
                data=data,
                timeout=self.timeout,
                stream=stream,
                allow_redirects=False,  # We'll handle redirects ourselves
                verify=os.getenv("SSL_VERIFY_UPSTREAM", "false").lower() in ("1", "true", "yes")
            )
        except requests.RequestException as e:
            return Response(f"Upstream error: {e}", status=502)
        
        # Handle upstream redirects
        if upstream_response.status_code in (301, 302, 307, 308):
            location = upstream_response.headers.get('location', '')
            # If redirect is to same upstream, we might want to follow it
            # For now, pass it through to client
            return Response(
                status=upstream_response.status_code,
                headers={'Location': location}
            )
        
        # Create Flask response
        # Filter out hop-by-hop headers from upstream
        response_headers = {}
        for key, value in upstream_response.headers.items():
            if key.lower() not in hop_by_hop and key.lower() != 'content-encoding':
                response_headers[key] = value
        
        # Remove content-length if streaming (chunked)
        if stream and 'content-length' in response_headers:
            del response_headers['content-length']
        
        return Response(
            stream_with_context(upstream_response.iter_content(chunk_size=8192)),
            status=upstream_response.status_code,
            headers=response_headers,
            content_type=upstream_response.headers.get('content-type')
        )


def should_use_proxy_mode(request_path: str) -> bool:
    """Determine if a request should use proxy mode instead of redirect.
    
    Proxy mode is recommended for:
    - Player API requests (hides credentials)
    - M3U playlist downloads
    - EPG/XML data
    
    Redirect mode is acceptable for:
    - Stream segments (already authenticated)
    - Static assets
    """
    proxy_paths = [
        '/player_api.php',
        '/get.php',      # M3U playlist
        '/xmltv.php',    # EPG
        '/panel_api.php',
    ]
    
    # Check if path starts with any proxy path
    for proxy_path in proxy_paths:
        if request_path.startswith(proxy_path) or request_path.endswith(proxy_path.split('/')[-1]):
            return True
    
    return False
