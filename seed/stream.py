import json
import re

# Nombre del archivo JSON
json_file = "data.json"

# Nombre del archivo JSON de categorías
categories_json_file = "categories.json"

# Nombre del archivo SQL de salida
sql_file = "output.sql"

# Expresiones regulares para eliminar las palabras específicas
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

# Comenzar el archivo SQL con la declaración INSERT INTO
with open(sql_file, 'w') as f:
    f.write("INSERT INTO tabla (num, name, stream_type, stream_id, stream_icon, epg_channel_id, added, is_adult, category_id, custom_sid, tv_archive, direct_source, tv_archive_duration) VALUES\n")

# Leer el archivo JSON de categorías
with open(categories_json_file, 'r') as cat_file:
    categories_data = json.load(cat_file)

# Leer el archivo JSON y escribir en el archivo SQL
with open(json_file, 'r') as f:
    data = json.load(f)
    with open(sql_file, 'a') as f_sql:
        for entry in data:
            # Remover palabras específicas y espacios en blanco al principio y final
            name = entry["name"]
            for pattern in patterns_to_remove:
                name = re.sub(pattern, '', name)
            name = name.strip()

            # Buscar el nombre en las categorías y obtener el ID correspondiente
            category_id = None
            for key, category_list in categories_data.items():
                if name in category_list:
                    category_id = int(key)
                    break

            num = entry["num"]
            stream_type = entry["stream_type"]
            stream_id = entry["stream_id"]
            stream_icon = entry["stream_icon"]
            epg_channel_id = entry["epg_channel_id"]
            added = entry["added"]
            is_adult = entry["is_adult"]
            custom_sid = entry["custom_sid"]
            tv_archive = entry["tv_archive"]
            direct_source = entry["direct_source"]
            tv_archive_duration = entry["tv_archive_duration"]
            
            # Escribir la línea SQL de inserción
            sql_line = f"({num}, '{name}', '{stream_type}', {stream_id}, '{stream_icon}', '{epg_channel_id}', {added}, {is_adult}, {category_id}, {custom_sid}, {tv_archive}, '{direct_source}', {tv_archive_duration}),\n"
            f_sql.write(sql_line)

# Eliminar la coma adicional al final del archivo SQL
with open(sql_file, 'r+') as f:
    lines = f.readlines()
    f.seek(0)
    for line in lines[:-1]:
        f.write(line)
    f.truncate()

print("Archivo SQL generado:", sql_file)
