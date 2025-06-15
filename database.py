import pg8000
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS

def get_conn():
    return pg8000.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
    )

def release_conn(conn):
    conn.close()
