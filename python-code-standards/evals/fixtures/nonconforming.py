import duckdb

def summarize(conn, name):
    rows = conn.execute("SELECT * FROM events WHERE name = '" + name + "'").fetchall()
    total = 0
    for row in rows:
        total += row[2]
    return total
