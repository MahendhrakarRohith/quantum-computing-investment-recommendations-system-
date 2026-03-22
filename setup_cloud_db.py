import os
import psycopg2
from dotenv import load_dotenv

# Load the secret URL from your .env file (override to ensure the Neon URL wins)
load_dotenv(override=True)
DB_URL = os.getenv("DATABASE_URL")


def create_cloud_db():
    print("Connecting to Cloud PostgreSQL...")
    try:
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()

        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS recommendations (
                symbol TEXT PRIMARY KEY,
                current_price REAL,
                target_price REAL,
                upside REAL,
                sentiment TEXT,
                reason TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            '''
        )

        conn.commit()
        cursor.close()
        conn.close()
        print("SUCCESS! Cloud Database connected and tables created.")

    except Exception as e:
        print(f"Failed to connect to the cloud: {e}")


if __name__ == "__main__":
    create_cloud_db()
