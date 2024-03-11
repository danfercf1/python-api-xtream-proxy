import os
import pymysql
import requests
from dotenv import load_dotenv
from tools import Tools

# Load environment variables from .env file
load_dotenv()
tool = Tools()


# Function to check if category exists in the database
def category_exists(cursor, category_name):
    cursor.execute("SELECT COUNT(*) FROM stream_categories WHERE category_name = %s", (category_name,))
    result = cursor.fetchone()
    return result['COUNT(*)'] > 0

# Function to save data to the stream_categories table
def save_to_database(data):
    cont = 50
    try:
        connection = pymysql.connect(host=os.getenv('DB_HOST'),
                                     user=os.getenv('DB_USER'),
                                     password=os.getenv('DB_PASSWORD'),
                                     database=os.getenv('DB_NAME'),
                                     cursorclass=pymysql.cursors.DictCursor)

        with connection.cursor() as cursor:
            for category in data:
                if not category_exists(cursor, category['category_name']):
                    cursor.execute("INSERT INTO stream_categories (id, category_name, parent_id, cat_order) VALUES (%s, %s, %s, %s)",
                                   (int(category['category_id']), category['category_name'], category['parent_id'], cont + 1))
            connection.commit()
    except pymysql.Error as e:
        print("Error connecting to database:", e)
    finally:
        if connection:
            connection.close()

if __name__ == '__main__':
    # Load credentials from environment variables
    username = os.getenv('USERNAME')
    password = os.getenv('PASSWORD')

    # Fetch JSON data from the provided URL
    url = 'http://iptvsub1-elite.com/player_api.php?username={}&password={}&action=get_live_categories'.format(username, password)
    
    print(url)
    
    response = requests.get(url)

    if response.status_code == 200:
        json_data = response.json()

        # Remove categories with specified name
        cleaned_data = tool.remove_categories_by_name(json_data)

        # Save cleaned data to database
        save_to_database(cleaned_data)

        print("Data processed and saved successfully.")
    else:
        print("Failed to fetch JSON data. Status code:", response.status_code)
