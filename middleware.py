from flask import Response, request
import requests


PROXY_TARGET = "http://iptvsub1-elite.com"

class TransparentProxyMiddleware:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        print("HOLA")
        # Verificar si la solicitud está dirigida a /live
        if environ['PATH_INFO'].startswith('/live'):
            # Construir la URL de destino modificando la ruta de la solicitud
            target_url = PROXY_TARGET + environ['PATH_INFO']

            # Reenviar la solicitud al servidor de destino
            response = requests.request(
                method=environ['REQUEST_METHOD'],
                url=target_url,
                headers=dict(environ),
                data=environ['wsgi.input'].read(),
                cookies=dict(request.cookies),
                allow_redirects=False  # Evitar redirecciones para mantener la transparencia
            )

            # Devolver la respuesta del servidor de destino al cliente
            return Response(response.content, response.status_code, headers=response.headers)

        # Si la solicitud no está dirigida a /live, continuar con la aplicación Flask
        return self.app(environ, start_response)
