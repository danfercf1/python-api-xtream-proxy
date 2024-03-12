from typing import Self
from flask import Flask, request, jsonify, redirect, send_file
import os
from database import Database
from api import Api

#  TODO EPG action=get_simple_data_table&stream_id=id Perfect player APP

app = Flask(__name__)
db = Database(app)
api = Api(db)

# Obtener las variables de entorno
PORT = os.environ.get('PORT') or 5000
DEBUG = os.environ.get('DEBUG') or False

# Endpoints
# Endpoint que redirecciona a otra URL reemplazando la URL original y agregando el resto del path
@app.route("/<path:path_to_complete>")
def redirect_url(path_to_complete):
    # Construir la URL de redirección con la nueva URL y el resto del path
    new_url = api.get_redirect(path_to_complete)
    
    app.logger.info("DNS URL: {}".format(new_url))

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
    
    if not db.verify_authentication(username, password):
        response = api.get_user_info(username, password, app)

        # Verificar si la solicitud fue exitosa (código de estado 200)
        if response.status_code == 200:
            # Guardar el usuario en la tabla users
            db.save_user(username, password)
        else:
            # Devolver un error de autenticación (status 401)
            return jsonify({"error": "Autenticación fallida"}), 401
    
    if not action:
        user = db.get_user(username, password)
        
        user_info = db.get_user_server_info(user["id"])
        
        if not user_info:
            response = api.get_user_info(username, password, app)
            user_info = response.json()
            db.save_user_server_info(user["id"], user_info["user_info"], user_info["server_info"])
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
                
                app.logger.info("Final - DNS URL: {}".format(nueva_url_redireccion))
                
                # Redireccionar a la URL construida
                return redirect(nueva_url_redireccion)

if __name__ == "__main__":
    app.run(debug=DEBUG, host='0.0.0.0', port=PORT)
