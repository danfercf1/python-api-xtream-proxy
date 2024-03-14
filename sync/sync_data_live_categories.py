import os
import pymysql
import requests
import logging
import time
from tools import Tools

tool = Tools()

# Configure logging to write to both file and stdout
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Create a file handler to write logs to a file
file_handler = logging.FileHandler('app.log')
file_handler.setLevel(logging.INFO)

# Create a stream handler to write logs to stdout
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)

# Create a formatter for both handlers
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)

# Add the handlers to the root logger
logging.getLogger().addHandler(file_handler)
logging.getLogger().addHandler(stream_handler)

# Function to check if category exists in the database
def category_exists(cursor, category_name):
    cursor.execute("SELECT COUNT(*) FROM stream_categories WHERE category_name = %s", (category_name,))
    result = cursor.fetchone()
    return result['COUNT(*)'] > 0

# Function to save data to the stream_categories table
def save_to_database(data, db_host, db_user, db_password, db_name):
    cont = 50
    try:
        connection = pymysql.connect(host=db_host,
                                     user=db_user,
                                     password=db_password,
                                     database=db_name,
                                     cursorclass=pymysql.cursors.DictCursor)

        with connection.cursor() as cursor:
            for category in data:
                if not category_exists(cursor, category['category_name']):
                    cursor.execute("INSERT INTO stream_categories (id, category_name, parent_id, cat_order) VALUES (%s, %s, %s, %s)",
                                   (int(category['category_id']), category['category_name'], category['parent_id'], cont + 1))
                    print("Category saved: {}, Category ID: {}".format(category['category_name'], category['category_id']))

            connection.commit()
    except pymysql.Error as e:
        print("Error connecting to database:", e)
    finally:
        if connection:
            connection.close()

if __name__ == '__main__':
    # Get MySQL database connection details from environment variables
    DB_HOST = os.getenv("MYSQL_HOST")
    DB_USER = os.getenv("MYSQL_USER")
    DB_PASSWORD = os.getenv("MYSQL_PASSWORD")
    DB_NAME = os.getenv("MYSQL_DATABASE")

    USER_NAME = os.getenv("USERNAME")
    PASSWORD = os.getenv("PASSWORD")

    print(USER_NAME, '*******')

    start_time = time.time()

    # Fetch JSON data from the provided URL
    url = 'http://iptvsub1-elite.com/player_api.php?username={}&password={}&action=get_live_categories'.format(USER_NAME, PASSWORD)
    
    response = requests.get(url)

    if response.status_code == 200:
        json_data = response.json()

        # Remove categories with specified name
        cleaned_data = tool.remove_categories_by_name(json_data)

        # Save cleaned data to database
        save_to_database(cleaned_data, DB_HOST, DB_USER, DB_PASSWORD, DB_NAME)

        print("Data processed and saved successfully.")
    else:
        print("Failed to fetch JSON data. Status code:", response.status_code)

    end_time = time.time()
    execution_time = end_time - start_time

    minutes = int(execution_time // 60)
    seconds = int(execution_time % 60)

    print("Execution time: {} minutes and {} seconds".format(minutes, seconds))
    
    # Log execution time
    logging.info("Execution time: {} minutes and {} seconds".format(minutes, seconds))