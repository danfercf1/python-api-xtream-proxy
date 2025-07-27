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

# Function to save data to the stream_categories table
def save_to_database(data, db_host, db_user, db_password, db_name):
    try:
        connection = pymysql.connect(host=db_host,
                                     user=db_user,
                                     password=db_password,
                                     database=db_name,
                                     cursorclass=pymysql.cursors.DictCursor)
 
        with connection.cursor() as cursor:
            # Get the current max cat_order to increment from there
            cursor.execute("SELECT MAX(cat_order) as max_order FROM stream_categories")
            result = cursor.fetchone()
            cont = result['max_order'] if result and result['max_order'] is not None else 0
 
            for category in data:
                category_id = int(category['category_id'])
                category_name = category['category_name']
                parent_id = category['parent_id']
 
                cursor.execute("SELECT id, category_name FROM stream_categories WHERE id = %s", (category_id,))
                existing_category = cursor.fetchone()
 
                if existing_category:
                    # Update if name is different
                    if existing_category['category_name'] != category_name:
                        cursor.execute("UPDATE stream_categories SET category_name = %s WHERE id = %s", (category_name, category_id))
                        logging.info(f"Category updated: {category_name}, Category ID: {category_id}")
                else:
                    # Insert new category
                    cont += 1
                    cursor.execute("INSERT INTO stream_categories (id, category_name, parent_id, cat_order) VALUES (%s, %s, %s, %s)", (category_id, category_name, parent_id, cont))
                    logging.info(f"Category saved: {category_name}, Category ID: {category_id}")
            connection.commit()
    except pymysql.Error as e:
        logging.error("Error with database operation: %s", e)
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

    logging.info(f"Starting category sync for user: {USER_NAME}")

    start_time = time.time()

    # Fetch JSON data from the provided URL
    url = f'http://iptvsub1-elite.com/player_api.php?username={USER_NAME}&password={PASSWORD}&action=get_live_categories'
    headers = {
        'User-Agent': 'curl/7.88.1'
    }
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        json_data = response.json()

        # Remove categories with specified name
        cleaned_data = tool.remove_categories_by_name(json_data)

        # Save cleaned data to database
        save_to_database(cleaned_data, DB_HOST, DB_USER, DB_PASSWORD, DB_NAME)

        logging.info("Data processed and saved successfully.")
    else:
        logging.error("Failed to fetch JSON data. Status code: %s", response.status_code)

    end_time = time.time()
    execution_time = end_time - start_time

    minutes = int(execution_time // 60)
    seconds = int(execution_time % 60)

    # Log execution time
    logging.info("Execution time: {} minutes and {} seconds".format(minutes, seconds))