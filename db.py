# db.py
import psycopg2, os
from dotenv import load_dotenv

load_dotenv()  # this reads your .env file and loads it into memory

def get_connection():
    connection_string = os.getenv("DATABASE_URL")
    return psycopg2.connect(connection_string)