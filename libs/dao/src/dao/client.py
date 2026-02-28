import os
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from dotenv import load_dotenv

load_dotenv()


class UrogDB:
    def __init__(self, connection_string=None):
        self.conn_str = connection_string or os.getenv("DATABASE_URL")
        if not self.conn_str:
            raise ValueError("DATABASE_URL is not set in environment variables.")
        self.conn = None

    def connect(self):
        """Establish connection to Neon."""
        if not self.conn or self.conn.closed:
            self.conn = psycopg2.connect(self.conn_str, cursor_factory=RealDictCursor)

    def close(self):
        """Close connection."""
        if self.conn:
            self.conn.close()

    def init_schema(self, schema_path=None):
        """Runs the schema.sql file to create tables."""
        if not schema_path:
            # default to local schema.sql
            schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")

        self.connect()
        with self.conn.cursor() as cur:
            with open(schema_path, "r") as f:
                cur.execute(f.read())
            self.conn.commit()
        print("Schema initialized successfully.")

    # ==========================
    # BRONZE LAYER (Inbox) Ops
    # ==========================

    def ingest_raw(self, source_name, source_type, payload):
        """
        Dumps raw data (dict or list) into the data_inbox.
        """
        self.connect()
        sql = """
            INSERT INTO data_inbox (source_name, source_type, raw_payload)
            VALUES (%s, %s, %s)
            RETURNING id;
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, (source_name, source_type, Json(payload)))
            new_id = cur.fetchone()["id"]
            self.conn.commit()
        return new_id

    def get_unprocessed_inbox_items(self, limit=50):
        """Fetch items that haven't been processed yet."""
        self.connect()
        sql = """
            SELECT * FROM data_inbox 
            WHERE processed_at IS NULL 
            ORDER BY created_at ASC 
            LIMIT %s;
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, (limit,))
            return cur.fetchall()

    def mark_inbox_processed(self, inbox_id, error=None):
        """Mark an inbox item as done (or failed)."""
        self.connect()
        status_sql = "processed_at = NOW()" if not error else "processed_at = NULL"

        sql = f"""
            UPDATE data_inbox 
            SET {status_sql}, error_log = %s 
            WHERE id = %s;
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, (error, inbox_id))
            self.conn.commit()

    # ==========================
    # SILVER LAYER (Core) Ops
    # ==========================

    def upsert_person(
        self, email, full_name=None, role="student", phone=None, extra_data={}
    ):
        """
        Creates or Updates a person.
        - Merges extra_data into existing profile_data.
        """
        self.connect()
        sql = """
            INSERT INTO people (email, full_name, role, phone, profile_data, updated_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (email) 
            DO UPDATE SET
                full_name = COALESCE(EXCLUDED.full_name, people.full_name),
                phone = COALESCE(EXCLUDED.phone, people.phone),
                profile_data = people.profile_data || EXCLUDED.profile_data,
                updated_at = NOW()
            RETURNING id;
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, (email, full_name, role, phone, Json(extra_data)))
            person_id = cur.fetchone()["id"]
            self.conn.commit()
        return person_id

    def create_opportunity(
        self, title, owner_id, description=None, type="research", form_config=None
    ):
        """Create a new opportunity, optionally storing Google Workspace metadata."""
        self.connect()
        sql = """
            INSERT INTO opportunities (title, owner_id, description, type, form_config)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
        """
        with self.conn.cursor() as cur:
            cur.execute(
                sql, (title, owner_id, description, type, Json(form_config or {}))
            )
            opp_id = cur.fetchone()["id"]
            self.conn.commit()
        return opp_id

    # ==========================
    # AUTOMATION Ops
    # ==========================

    def get_person_by_email(self, email):
        """Fetch a single person by email, or None if not found."""
        self.connect()
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM people WHERE email = %s", (email,))
            return cur.fetchone()

    def get_people(self, role=None, limit=100):
        """Fetch people, optionally filtered by role."""
        self.connect()
        if role:
            sql = """
                SELECT * FROM people
                WHERE role = %s
                ORDER BY created_at DESC
                LIMIT %s;
            """
            params = (role, limit)
        else:
            sql = """
                SELECT * FROM people
                ORDER BY created_at DESC
                LIMIT %s;
            """
            params = (limit,)
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def get_template(self, name):
        self.connect()
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM templates WHERE name = %s", (name,))
            return cur.fetchone()

    def create_template(self, name, platform, content, required_keys=None):
        """Insert a new message template."""
        self.connect()
        sql = """
            INSERT INTO templates (name, platform, content, required_keys)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (name) DO UPDATE SET
                content = EXCLUDED.content,
                required_keys = EXCLUDED.required_keys
            RETURNING id;
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, (name, platform, content, required_keys))
            tmpl_id = cur.fetchone()["id"]
            self.conn.commit()
        return tmpl_id

    def log_sent_message(
        self,
        recipient_id,
        template_id,
        platform,
        compiled_msg,
        status="sent",
        error=None,
    ):
        self.connect()
        sql = """
            INSERT INTO sent_logs (recipient_id, template_id, platform, status, compiled_message, error_message)
            VALUES (%s, %s, %s, %s, %s, %s);
        """
        with self.conn.cursor() as cur:
            cur.execute(
                sql, (recipient_id, template_id, platform, status, compiled_msg, error)
            )
            self.conn.commit()


# Singleton instance for easy import
db = UrogDB()
