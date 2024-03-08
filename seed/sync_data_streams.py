import re
import pymysql
import requests

# MySQL database connection details
DB_HOST = 'mariadb'
DB_USER = 'daniel'
DB_PASSWORD = 'daniel'
DB_NAME = 'xtream_code'

USER_NAME = '8504f56cf0'
PASSWORD = 'e0737c5414'


# Text patterns to remove from name
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

# Function to remove text patterns from a name
def remove_patterns(name):
    for pattern in patterns_to_remove:
        name = re.sub(pattern, '', name)
    return name.strip()

# Function to connect to the database and save data
def save_to_database(data, allowed_category_ids):
    try:
        connection = pymysql.connect(host=DB_HOST,
                                     user=DB_USER,
                                     password=DB_PASSWORD,
                                     database=DB_NAME,
                                     cursorclass=pymysql.cursors.DictCursor)

        with connection.cursor() as cursor:
            for item in data:
                new_name = remove_patterns(item['name'])
                cursor.execute("SELECT * FROM streams WHERE name=%s", (new_name,))
                existing_item = cursor.fetchone()
                if existing_item:
                    # If the name already exists and the category_id is not in the allowed list, update it.
                    if existing_item['category_id'] not in allowed_category_ids:
                        cursor.execute("UPDATE streams SET added=%s, category_id=%s, custom_sid=%s, direct_source=%s, epg_channel_id=%s, is_adult=%s, num=%s, stream_icon=%s, stream_id=%s, stream_type=%s, tv_archive=%s, tv_archive_duration=%s WHERE name=%s",
                                       (item['added'], item['category_id'], item['custom_sid'], item['direct_source'], item['epg_channel_id'], item['is_adult'], item['num'], item['stream_icon'], item['stream_id'], item['stream_type'], item['tv_archive'], item['tv_archive_duration'], new_name))
                else:
                    cursor.execute("INSERT INTO streams (name, added, category_id, custom_sid, direct_source, epg_channel_id, is_adult, num, stream_icon, stream_id, stream_type, tv_archive, tv_archive_duration) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                                   (new_name, item['added'], item['category_id'], item['custom_sid'], item['direct_source'], item['epg_channel_id'], item['is_adult'], item['num'], item['stream_icon'], item['stream_id'], item['stream_type'], item['tv_archive'], item['tv_archive_duration']))
            connection.commit()
    except pymysql.Error as e:
        print("Error connecting to database:", e)
    finally:
        if connection:
            connection.close()

# Define the allowed category IDs for updating
allowed_category_ids = {1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,33}

# Function to fetch JSON data from external server
def fetch_json_data():
    url = 'http://iptvsub1-elite.com/player_api.php?username={}&password={}&action=get_live_streams'.format(USER_NAME, PASSWORD)

    # Make HTTP GET request
    response = requests.get(url)

    # Check if request was successful (status code 200)
    if response.status_code == 200:
        # Parse JSON response
        return response.json()
    else:
        print(f"Failed to fetch JSON data. Status code: {response.status_code}")
        return None

# Parse JSON data
json_data = fetch_json_data()

# Save to database
save_to_database(json_data, allowed_category_ids)

print("Data saved to database.")
