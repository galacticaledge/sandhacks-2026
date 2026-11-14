from db.store import init_db, is_sqlite

if __name__ == "__main__":
    init_db()
    print("database ready", "(sqlite)" if is_sqlite() else "(postgres/timescale)")
