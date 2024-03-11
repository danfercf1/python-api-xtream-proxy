import os
import json
import random
import pymysql

# Obtener las variables de entorno
MYSQL_HOST = os.environ.get('MYSQL_HOST')
MYSQL_USER = os.environ.get('MYSQL_USER')
MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD')
MYSQL_DATABASE = os.environ.get('MYSQL_DATABASE')
PORT = os.environ.get('PORT')
SERVER_IP = os.environ.get('SERVER_IP')

class Database:
    def __init__(self):
        self.host = MYSQL_HOST
        self.user = MYSQL_USER
        self.password = MYSQL_PASSWORD
        self.database = MYSQL_DATABASE
        self.port = PORT
        self.server_ip = SERVER_IP
    
    def connect(self):
        return pymysql.connect(
            host=self.host,
            user=self.user,
            password=self.password,
            database=self.database
        )
        
    # Esta función verifica si un usuario existe en la base de datos

    def user_exists(self, username, password):
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                sql = "SELECT * FROM users WHERE username = %s AND password = %s"
                cursor.execute(sql, (username, password,))
                result = cursor.fetchone()
                return result is not None
        finally:
            connection.close()

    def save_user(self, username, password):
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                sql = "INSERT INTO users (username, password) VALUES (%s, %s)"
                cursor.execute(sql, (username, password))
                # Obtener el ID del usuario insertado
                user_id = cursor.lastrowid
            connection.commit()
            return user_id  # Devolver el ID del usuario insertado
        finally:
            connection.close()

    def get_user(self, user, passw):
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                sql = "SELECT * FROM users WHERE username = %s AND password = %s"
                cursor.execute(sql, (user, passw,))
                result = cursor.fetchone()
                if result:
                    id, username, password = result
                    return {"id": id, "username": username, "password": password}
                else:
                    return None
        finally:
            connection.close()

    
    def save_user_server_info(self, user_id, user_info, server_info):
        connection = self.connect()
        server_info["url"] = self.server_ip or server_info["url"]
        server_info["port"] = self.port or server_info["port"]
        user_info_json = json.dumps(user_info)
        server_info_json = json.dumps(server_info)
        try:
            with connection.cursor() as cursor:
                # Verificar si ya existe una fila para el usuario
                sql_select = "SELECT id FROM user_server_info WHERE user_id = %s"
                cursor.execute(sql_select, (user_id,))
                existing_row = cursor.fetchone()

                if existing_row:
                    # Si existe, actualizar los datos
                    sql_update = "UPDATE user_server_info SET user_info = %s, server_info = %s WHERE user_id = %s"
                    cursor.execute(sql_update, (user_info_json, server_info_json, user_id))
                    connection.commit()
                else:
                    # Si no existe, insertar una nueva fila
                    sql_insert = "INSERT INTO user_server_info (user_id, user_info, server_info) VALUES (%s, %s, %s)"
                    cursor.execute(sql_insert, (user_id, user_info_json, server_info_json))
                    connection.commit()
        finally:
            connection.close()


    def get_user_server_info(self, user_id):
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                sql = "SELECT * FROM user_server_info WHERE user_id = %s"
                cursor.execute(sql, (user_id,))
                row = cursor.fetchone()
                if row:
                    # Convertir la tupla en un diccionario
                    user_info = json.loads(row[2])  # user_info está en la segunda posición de la tupla
                    server_info = json.loads(row[3])  # server_info está en la tercera posición de la tupla
                    return {"user_info": user_info, "server_info": server_info}
                else:
                    return None
        finally:
            connection.close()



    def verify_authentication(self, username, password):
        if not self.user_exists(username, password):
            return False
        # Aquí realizarías la solicitud al servidor externo para verificar la autenticación
        return True  # Simplemente devolvemos True para este ejemplo

    # Esta función obtiene una URL aleatoria de la tabla server_dns
    def get_dns_url_random(self):
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                try:
                    sql = "SELECT dns_url FROM server_dns ORDER BY RAND() LIMIT 1"
                    cursor.execute(sql)
                    url = cursor.fetchone()[0]
                    return url
                except:
                    return 'http://iptvsub1-elite.com'
        finally:
            connection.close()

    
    def get_all_stream_categories(self):
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                sql = "SELECT * FROM stream_categories"
                cursor.execute(sql)
                # Obtener todos los resultados de la consulta
                results = cursor.fetchall()
                # Formatear los resultados como una lista de diccionarios
                categories = []
                for row in results:
                    category = {
                        "category_id": row[0],
                        "category_name": row[1],
                        "parent_id": row[2]
                    }
                    categories.append(category)
                return categories
        finally:
            connection.close()
    
    def get_all_streams(self):
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                sql = "SELECT * FROM streams"
                cursor.execute(sql)
                # Obtener todos los resultados de la consulta
                results = cursor.fetchall()
                # Formatear los resultados como una lista de diccionarios
                streams = []
                for row in results:
                    stream = {
                        "num": row[1],
                        "name": row[2],
                        "stream_type": row[3],
                        "stream_id": row[4],
                        "stream_icon": row[5],
                        "epg_channel_id": row[6],
                        "added": row[7],
                        "is_adult": row[8],
                        "category_id": row[9],
                        "category_ids": row[10],
                        "custom_sid": row[11],
                        "tv_archive": row[12],
                        "direct_source": row[13],
                        "tv_archive_duration": row[14],
                    }
                    streams.append(stream)
                return streams
        finally:
            connection.close()
            
    def get_all_streams_by_category(self, category_id):
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                sql = "SELECT * FROM streams WHERE category_id = %s"
                cursor.execute(sql, (category_id,))
                # Obtener todos los resultados de la consulta
                results = cursor.fetchall()
                # Formatear los resultados como una lista de diccionarios
                streams = []
                for row in results:
                    stream = {
                        "num": row[1],
                        "name": row[2],
                        "stream_type": row[3],
                        "stream_id": row[4],
                        "stream_icon": row[5],
                        "epg_channel_id": row[6],
                        "added": row[7],
                        "is_adult": row[8],
                        "category_id": row[9],
                        "category_ids": row[10],
                        "custom_sid": row[11],
                        "tv_archive": row[12],
                        "direct_source": row[13],
                        "tv_archive_duration": row[14],
                    }
                    streams.append(stream)
                return streams
        finally:
            connection.close()

