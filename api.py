import requests

class Api:
    def __init__(self, db):
        dns_url = db.get_dns_url_random() # Esta función debería obtener una URL aleatoria de la tabla server_dns
        self.dns_url = dns_url
    
    def get_user_info(self, username, password, app):
        app.logger.info('DNS URL: {}'.format(self.dns_url))

        # Realizar la solicitud HTTP con los datos de usuario a la URL obtenida
        response = requests.get(self.dns_url + '/player_api.php', params={'username': username, 'password': password})
        
        return response
    
    def get_categories(self, username, password):
        response = requests.get(self.dns_url + '/player_api.php',
                                params={'username': username, 'password': password, 'action': 'get_live_categories'})
        
        return response
    
    def get_redirect(self, path):
        redirect_url = self.dns_url + '/' + path
        return redirect_url
    
    def get_server_url(self):
        return self.dns_url
   
