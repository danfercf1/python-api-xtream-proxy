import os
import requests

DEFAULT_UPSTREAM_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Version/4.0 Chrome/120.0 Mobile Safari/537.36"
)

class Api:
    def __init__(self, db):
        dns_url = db.get_dns_url_random() # Esta función debería obtener una URL aleatoria de la tabla server_dns
        self.dns_url = dns_url
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
        redirect_url = self.dns_url + '/' + path
        return redirect_url
    
    def get_server_url(self):
        return self.dns_url
   
