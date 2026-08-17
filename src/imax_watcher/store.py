from __future__ import annotations
import json, sqlite3
from .models import Preferences

class Store:
    def __init__(self, path: str = "imax_watcher.db"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS profiles(user_id INTEGER PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS movie_overrides(user_id INTEGER, movie_id TEXT, data TEXT NOT NULL,
          PRIMARY KEY(user_id,movie_id));
        CREATE TABLE IF NOT EXISTS watches(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
          movie_id TEXT NOT NULL, movie_name TEXT NOT NULL, watch_date TEXT NOT NULL, data TEXT NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS seen_state(watch_id INTEGER, showing_key TEXT, sig TEXT NOT NULL,
          PRIMARY KEY(watch_id,showing_key));
        CREATE TABLE IF NOT EXISTS browser_seat_state(
          showing_key TEXT PRIMARY KEY,
          movie_name TEXT,
          watch_date TEXT,
          start_time TEXT,
          remaining INTEGER NOT NULL,
          context TEXT,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)
        self.conn.commit()

    def get_profile(self, user_id: int) -> Preferences:
        row = self.conn.execute("SELECT data FROM profiles WHERE user_id=?", (user_id,)).fetchone()
        return Preferences(**json.loads(row[0])) if row else Preferences()

    def save_profile(self, user_id: int, prefs: Preferences):
        data={"party_size":prefs.party_size,"adjacency_mode":prefs.adjacency_mode,"seat_scope":prefs.seat_scope}
        self.conn.execute("INSERT INTO profiles(user_id,data) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data",
                          (user_id, json.dumps(data)))
        self.conn.commit()

    def save_movie_override(self, user_id: int, movie_id: str, override: dict):
        self.conn.execute("INSERT INTO movie_overrides(user_id,movie_id,data) VALUES(?,?,?) ON CONFLICT(user_id,movie_id) DO UPDATE SET data=excluded.data",
                          (user_id,movie_id,json.dumps(override)))
        self.conn.commit()

    def get_movie_override(self, user_id: int, movie_id: str) -> dict:
        row=self.conn.execute("SELECT data FROM movie_overrides WHERE user_id=? AND movie_id=?",(user_id,movie_id)).fetchone()
        return json.loads(row[0]) if row else {}

    def add_watch(self, user_id:int, movie_id:str, movie_name:str, date:str, override:dict|None=None)->int:
        cur=self.conn.execute("INSERT INTO watches(user_id,movie_id,movie_name,watch_date,data) VALUES(?,?,?,?,?)",
                              (user_id,movie_id,movie_name,date,json.dumps(override or {})))
        self.conn.commit(); return int(cur.lastrowid)

    def list_watches(self, user_id:int|None=None):
        if user_id is None:
            return self.conn.execute("SELECT * FROM watches WHERE enabled=1 ORDER BY id").fetchall()
        return self.conn.execute("SELECT * FROM watches WHERE user_id=? ORDER BY id",(user_id,)).fetchall()

    def set_enabled(self, watch_id:int, enabled:bool):
        self.conn.execute("UPDATE watches SET enabled=? WHERE id=?",(1 if enabled else 0,watch_id)); self.conn.commit()

    def resolved_preferences(self, watch_row) -> Preferences:
        p=self.get_profile(watch_row["user_id"])
        p=p.merged(self.get_movie_override(watch_row["user_id"],watch_row["movie_id"]))
        return p.merged(json.loads(watch_row["data"]))

    def get_seen(self, watch_id:int, showing_key:str)->set[str]:
        row=self.conn.execute("SELECT sig FROM seen_state WHERE watch_id=? AND showing_key=?",(watch_id,showing_key)).fetchone()
        return set(json.loads(row[0])) if row else set()

    def set_seen(self, watch_id:int, showing_key:str, sig:set[str]):
        self.conn.execute("INSERT INTO seen_state(watch_id,showing_key,sig) VALUES(?,?,?) ON CONFLICT(watch_id,showing_key) DO UPDATE SET sig=excluded.sig",
                          (watch_id,showing_key,json.dumps(sorted(sig))))
        self.conn.commit()

    def get_browser_remaining(self, showing_key: str) -> int | None:
        row=self.conn.execute("SELECT remaining FROM browser_seat_state WHERE showing_key=?",(showing_key,)).fetchone()
        return int(row[0]) if row else None

    def set_browser_remaining(self, showing_key: str, movie_name: str, watch_date: str, start_time: str,
                              remaining: int, context: str = "") -> None:
        self.conn.execute(
            """INSERT INTO browser_seat_state(showing_key,movie_name,watch_date,start_time,remaining,context,updated_at)
               VALUES(?,?,?,?,?,?,CURRENT_TIMESTAMP)
               ON CONFLICT(showing_key) DO UPDATE SET movie_name=excluded.movie_name,watch_date=excluded.watch_date,
               start_time=excluded.start_time,remaining=excluded.remaining,context=excluded.context,updated_at=CURRENT_TIMESTAMP""",
            (showing_key,movie_name,watch_date,start_time,int(remaining),context[:1500]),
        )
        self.conn.commit()

    def list_browser_states(self, limit: int = 10):
        return self.conn.execute(
            "SELECT * FROM browser_seat_state ORDER BY updated_at DESC LIMIT ?",(limit,)
        ).fetchall()
