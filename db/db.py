import sqlite3
from datetime import datetime

DB_PATH = "./db/competitions.db"


def db_conn() -> sqlite3.Connection:
    """
    Establishes a connection to the SQLite database.

    Returns:
    sqlite3.Connection: SQLite database connection object.
    """
    return sqlite3.connect(DB_PATH)


def create_tables() -> None:
    """
    Creates necessary tables if they don't exist.
    """
    conn = db_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tournaments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            country TEXT NOT NULL,
            location TEXT,
            url TEXT UNIQUE
        )
    """
    )
    conn.commit()
    cur.close()
    conn.close()


def clear_database() -> None:
    """
    Clears all entries from the database.

    Returns:
    None
    """
    try:
        conn = db_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM tournaments")
        conn.commit()
        cur.close()
        conn.close()
    except sqlite3.DatabaseError as error:
        print(f"Error clearing database: {error}")


def load_known_competitions() -> list:
    """
    Loads saved competitions from the database with start dates greater than or equal to the current date.

    Returns:
    list: List of dictionaries with saved competitions.
    """
    try:
        conn = db_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM tournaments WHERE start_date >= ?", (get_current_date(),)
        )
        results = cur.fetchall()
        cur.close()
        conn.close()

        return [
            {
                "Name": result[1],
                "URL": result[6],
                "Start Date": result[2],
                "End Date": result[3],
                "Location": result[5],
                "Country": result[4],
            }
            for result in results
        ]
    except sqlite3.DatabaseError as error:
        print(f"Error loading known competitions: {error}")
        return []


def save_competition(competition: dict) -> None:
    """
    Saves a competition entry to the database, handling unique constraints and retrying on locked database errors.

    Parameters:
    competition (dict): Dictionary with competition details.

    Returns:
    None
    """
    try:
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO tournaments (name, start_date, end_date, country, location, url) VALUES (?, ?, ?, ?, ?, ?);",
                (
                    competition["Name"],
                    competition["Start Date"],
                    competition["End Date"],
                    competition["Country"],
                    competition["Location"],
                    competition["URL"],
                ),
            )
            conn.commit()
            cur.close()

    except sqlite3.IntegrityError as e:
        print(f"Integrity error: {e}")
    except sqlite3.OperationalError as error:
        print(f"Operational error: {error}")


def delete_old_competitions():
    """
    Deletes competitions from the database that have an end date earlier than the current date.

    Returns:
    None
    """
    try:
        conn = db_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM tournaments WHERE end_date < ?", (get_current_date(),))
        conn.commit()
        cur.close()
        conn.close()
        print("Old competitions have been deleted from the database.")

    except sqlite3.DatabaseError as error:
        print(f"Error deleting old competitions: {error}")


def get_current_date():
    """
    Returns the current date.

    Returns:
    datetime.date: Current date.
    """
    return datetime.now().date()
