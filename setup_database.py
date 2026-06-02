import sys
import subprocess
import os

SCHEMA_PATH = "supabase/schema.sql"

def install_and_import(package):
    try:
        __import__(package)
        print(f"'{package}' is already installed.")
    except ImportError:
        print(f"Installing {package}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])

if __name__ == "__main__":
    install_and_import("psycopg2")
    import psycopg2

    schema_file = os.path.abspath(os.path.join(os.getcwd(), SCHEMA_PATH))
    if not os.path.exists(schema_file):
        print(f"Error: schema.sql file not found. Checked: {schema_file}")
        sys.exit(1)

    print(f"Reading schema from: {schema_file}")
    with open(schema_file, "r") as f:
        sql_commands = f.read()

    print("Connecting to Supabase PostgreSQL database...")
    try:
        conn = psycopg2.connect(
            host="aws-1-ap-northeast-2.pooler.supabase.com",
            port=6543,
            user="postgres.rcotcanlwgysparkojgj",
            password="@+*KgFfyf9p-rX$",
            database="postgres"
        )
        conn.autocommit = True
        cursor = conn.cursor()
        
        print("Executing schema setup SQL commands...")
        cursor.execute(sql_commands)
        
        print("Database schema successfully seeded and configured!")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error executing database setup: {e}")
        sys.exit(1)
