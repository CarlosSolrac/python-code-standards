import csv
import duckdb


def process_events(db_path, csv_path, out_path, min_count, start, end):
    conn = duckdb.connect(db_path)
    rows = conn.execute("SELECT event_id, event_name, occurred_at, count FROM events").fetchall()

    filtered = []
    for r in rows:
        if r[2] < start:
            continue
        if r[2] > end:
            continue
        if r[3] < min_count:
            continue
        filtered.append(r)

    by_name = {}
    for r in filtered:
        name = r[1]
        if name not in by_name:
            by_name[name] = 0
        by_name[name] = by_name[name] + r[3]

    by_month = {}
    for r in filtered:
        month = str(r[2])[:7]
        key = (month, r[1])
        if key not in by_month:
            by_month[key] = 0
        by_month[key] = by_month[key] + r[3]

    ranked = []
    for name in by_name:
        ranked.append((name, by_name[name]))
    ranked.sort(key=lambda x: x[1], reverse=True)

    lines = []
    for name, total in ranked:
        pct = 0
        allt = 0
        for n2 in by_name:
            allt = allt + by_name[n2]
        if allt > 0:
            pct = round(total * 100.0 / allt, 2)
        lines.append(name + "," + str(total) + "," + str(pct))

    with open(out_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["event_name", "total", "pct"])
        for line in lines:
            w.writerow(line.split(","))

    extras = []
    for key in by_month:
        extras.append((key[0], key[1], by_month[key]))
    extras.sort()

    summary = {}
    summary["events"] = len(by_name)
    summary["rows"] = len(filtered)
    summary["months"] = len(set([e[0] for e in extras]))
    summary["top"] = ranked[0][0] if ranked else None

    conn.close()
    return summary, extras
