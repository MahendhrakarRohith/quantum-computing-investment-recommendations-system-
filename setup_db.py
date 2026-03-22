import sqlite3

def create_db():
    conn = sqlite3.connect('market_leaderboard.db')
    cursor = conn.cursor()
    
    # Create a table to hold our pre-calculated AI predictions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recommendations (
            symbol TEXT PRIMARY KEY,
            current_price REAL,
            target_price REAL,
            upside REAL,
            sentiment TEXT,
            reason TEXT,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ Database ready!")

if __name__ == "__main__":
    create_db()