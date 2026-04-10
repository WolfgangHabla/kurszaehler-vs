import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

RAPLA_BASE = (
    "https://rapla.dhbw.de/rapla/calendar?"
    "key=3m0O8EVJ2EaIYRGKNLrg04l51NVqdHUdqmVlRsPBk79i5RvkbUkRU3mkHJcmcGYy"
    "2iSBBS-IDTcajBP0hVZOvO4-EMZYgpSc7lj1FTS_4NLq5fb-ZVXqOA_7GxQZsYWjLmdX"
    "fLQ4PL68OAjCUe1vG-3T23NxGXJBNLjWKQqDU1o"
    "&salt=-888929980"
)

STARPLAN_PAGE = "https://splan.hs-furtwangen.de/starplan/mobile"
STARPLAN_JSON = "https://splan.hs-furtwangen.de/starplan/json"
STARPLAN_LOC = 2   # VS campus

TIME_RE = re.compile(r"(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})")
LEFT_RE = re.compile(r"left:\s*(-?\d+)px")


def _easter_sunday(year):
    """Ostersonntag nach dem Anonymous-Gregorian-Algorithmus."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _holidays_bw(year):
    """Gesetzliche Feiertage in Baden-Württemberg für ein Jahr."""
    easter = _easter_sunday(year)
    return {
        date(year, 1, 1),       # Neujahr
        date(year, 1, 6),       # Heilige Drei Könige
        easter + timedelta(-2), # Karfreitag
        easter + timedelta(1),  # Ostermontag
        date(year, 5, 1),       # Tag der Arbeit
        easter + timedelta(39), # Christi Himmelfahrt
        easter + timedelta(50), # Pfingstmontag
        easter + timedelta(60), # Fronleichnam
        date(year, 10, 3),      # Tag der Deutschen Einheit
        date(year, 11, 1),      # Allerheiligen
        date(year, 12, 25),     # 1. Weihnachtstag
        date(year, 12, 26),     # 2. Weihnachtstag
    }


def _starplan_semester_for_date(session, target_date):
    """Semester-ID aus getpus für ein Datum. None wenn kein Semester passt."""
    resp = session.get(f"{STARPLAN_JSON}?m=getpus", timeout=15)
    resp.raise_for_status()
    for sem in resp.json()[0]:
        start = date.fromisoformat(sem["startdate"])
        end = date.fromisoformat(sem["enddate"])
        if start <= target_date <= end:
            return sem["id"]
    return None


def _empty_starplan_week(monday):
    """Leere StarPlan-Woche (kein Semester gefunden)."""
    day_abbr = ["Mo", "Di", "Mi", "Do", "Fr", "Sa"]
    results = []
    for i in range(6):
        d = monday + timedelta(days=i)
        label = d.strftime(f"{day_abbr[i]} %d.%m.")
        results.append({
            "label": label, "total_events": 0,
            "running_at_0800": 0, "running_at_0900": 0, "running_at_1300": 0,
        })
    return {"week": f"KW {monday.isocalendar()[1]}", "days": results}


def time_to_minutes(t):
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def parse_rapla_week(day, month, year):
    url = f"{RAPLA_BASE}&day={day}&month={month}&year={year}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", class_="week_table")

    if not table:
        return None

    # Extract week number
    week_num = ""
    wn = table.find("th", class_="week_number")
    if wn:
        week_num = wn.get_text().strip()

    rows = table.find_all("tr")

    # Parse day column boundaries from header row
    day_boundaries = []  # [(label, start_col, end_col)]
    col = 0
    for cell in rows[0].find_all(["th", "td"]):
        cs = int(cell.get("colspan", 1))
        if "week_header" in cell.get("class", []):
            nobr = cell.find("nobr")
            label = nobr.get_text().strip() if nobr else cell.get_text().strip()
            day_boundaries.append((label, col, col + cs - 1))
        col += cs

    def day_for_col(c):
        for lbl, s, e in day_boundaries:
            if s <= c <= e:
                return lbl
        return None

    # Simulate table cell placement across rows, tracking rowspan
    events_by_day = {lbl: [] for lbl, _, _ in day_boundaries}
    rowspan_cells = {}  # col -> remaining rowspan count

    for row in rows[1:]:
        # Decrement rowspan counters from the previous row
        for c in list(rowspan_cells):
            rowspan_cells[c] -= 1
            if rowspan_cells[c] <= 0:
                del rowspan_cells[c]

        col = 0
        for cell in row.find_all(["td", "th"]):
            # Skip columns occupied by spanning cells from previous rows
            while col in rowspan_cells:
                col += 1

            cs = int(cell.get("colspan", 1))
            rs = int(cell.get("rowspan", 1))

            if "week_block" in cell.get("class", []):
                text = cell.get_text()
                m = TIME_RE.search(text)
                if m:
                    text_lower = text.lower()
                    is_online = "online" in text_lower
                    is_excursion = "ausflug" in text_lower or "exkursion" in text_lower
                    if not is_online and not is_excursion:
                        lbl = day_for_col(col)
                        if lbl:
                            events_by_day[lbl].append((m.group(1), m.group(2)))

            if rs > 1:
                for c in range(col, col + cs):
                    rowspan_cells[c] = rs  # decremented at start of next row

            col += cs

    check_times = [
        ("08:00", time_to_minutes("08:00")),
        ("09:00", time_to_minutes("09:00")),
        ("13:00", time_to_minutes("13:00")),
    ]

    holidays = _holidays_bw(year)
    results = []
    for label, _, _ in day_boundaries:
        events = events_by_day.get(label, [])
        # Datum aus Label extrahieren ("Mo 09.03." → day=9, month=3)
        parts = label.split()[-1].rstrip(".").split(".")
        current_date = date(year, int(parts[1]), int(parts[0]))
        is_holiday = current_date in holidays

        counts = {}
        for time_label, check_min in check_times:
            key = f"running_at_{time_label.replace(':', '')}"
            if is_holiday:
                counts[key] = 0
            else:
                counts[key] = sum(
                    1
                    for start, end in events
                    if time_to_minutes(start) <= check_min <= time_to_minutes(end)
                )
        total = 0 if is_holiday else len(events)
        results.append({"label": label, "total_events": total, **counts})

    return {"week": week_num, "days": results}


def _starplan_session(semester_id):
    """Return a requests.Session with a valid StarPlan cookie."""
    session = requests.Session()
    session.get(
        f"{STARPLAN_PAGE}?lan=de&acc=true&act=tt&sel=ro"
        f"&pu={semester_id}&sd=true&loc={STARPLAN_LOC}&sa=false&cb=o",
        timeout=15,
    )
    return session


def _fetch_room_week(session, room_id, dfc, semester_id):
    """Fetch one VS room's timetable and return (start, end, day_idx) tuples.

    Day index: 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat.
    Events sit at left = (column_start - 1)px. Column starts are parsed from
    the ttweekdaycell headers present in the HTML fragment.
    """
    url = (
        f"{STARPLAN_JSON}?m=getTT&sel=ro&pu={semester_id}"
        f"&ro={room_id}&dfc={dfc}&ddm=false&sd=true&sa=false&lan=de"
    )
    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Build sorted list of day-column left boundaries from the header divs.
    # Headers appear in Mon→Sat order; their left values increase by 180px each
    # (Fri may be wider if sub-columns exist, but its start is always 720).
    col_starts = []
    for h in soup.find_all("div", class_="ttweekdaycell"):
        m = LEFT_RE.search(h.get("style", ""))
        if m:
            col_starts.append(int(m.group(1)))
    col_starts.sort()

    def _day_idx(event_left_px):
        col_left = event_left_px + 1  # events are 1px inside their column
        # Largest col_start <= col_left gives the column index
        result = -1
        for i, start in enumerate(col_starts):
            if start <= col_left:
                result = i
        return result

    events = []
    for ev in soup.find_all("div", class_="ttevent"):
        m = LEFT_RE.search(ev.get("style", ""))
        if not m:
            continue
        day_idx = _day_idx(int(m.group(1)))
        if not (0 <= day_idx <= 5):
            continue
        tm = TIME_RE.search(ev.get_text())
        if tm:
            events.append((tm.group(1), tm.group(2), day_idx))
    return events


def parse_starplan_week(day, month, year):
    monday = date(year, month, day)
    dfc = monday.isoformat()

    # Bootstrap-Session für Semester-Erkennung
    bootstrap = requests.Session()
    bootstrap.get(f"{STARPLAN_PAGE}?lan=de&acc=true", timeout=15)
    semester_id = _starplan_semester_for_date(bootstrap, monday)
    if semester_id is None:
        return _empty_starplan_week(monday)

    # Richtige Session mit sd=true und korrektem Semester
    session = _starplan_session(semester_id)

    # Get all VS rooms
    rooms_resp = session.get(
        f"{STARPLAN_JSON}?m=getros&loc={STARPLAN_LOC}", timeout=15
    )
    rooms_resp.raise_for_status()
    vs_rooms = rooms_resp.json()[0]  # outer array wrapper

    # Fetch all room timetables in parallel
    events_by_day = [[] for _ in range(6)]  # Mon–Sat
    with ThreadPoolExecutor(max_workers=12) as ex:
        futures = {
            ex.submit(_fetch_room_week, session, room["id"], dfc, semester_id): room["id"]
            for room in vs_rooms
        }
        for fut in as_completed(futures):
            try:
                for start, end, day_idx in fut.result():
                    events_by_day[day_idx].append((start, end))
            except Exception:
                pass  # skip rooms that fail

    check_times = [
        ("08:00", time_to_minutes("08:00")),
        ("09:00", time_to_minutes("09:00")),
        ("13:00", time_to_minutes("13:00")),
    ]
    day_abbr = ["Mo", "Di", "Mi", "Do", "Fr", "Sa"]
    holidays = _holidays_bw(monday.year)
    results = []
    for i, events in enumerate(events_by_day):
        current_date = monday + timedelta(days=i)
        label = current_date.strftime(f"{day_abbr[i]} %d.%m.")
        is_holiday = current_date in holidays

        counts = {}
        for time_label, check_min in check_times:
            key = f"running_at_{time_label.replace(':', '')}"
            if is_holiday:
                counts[key] = 0
            else:
                counts[key] = sum(
                    1
                    for start, end in events
                    if time_to_minutes(start) <= check_min <= time_to_minutes(end)
                )
        total = 0 if is_holiday else len(events)
        results.append({"label": label, "total_events": total, **counts})

    week_num = f"KW {monday.isocalendar()[1]}"
    return {"week": week_num, "days": results}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/week")
def api_week():
    try:
        day = int(request.args["day"])
        month = int(request.args["month"])
        year = int(request.args["year"])
        date(year, month, day)  # validate
    except (KeyError, ValueError, TypeError):
        return jsonify({"error": "Ungültige Datumsparameter"}), 400

    try:
        result = parse_rapla_week(day, month, year)
    except requests.RequestException:
        return jsonify({"error": "Rapla-Server nicht erreichbar"}), 502

    if result is None:
        return jsonify({"error": "Unerwartete Seitenstruktur"}), 502

    return jsonify(result)


@app.route("/api/starplan/week")
def api_starplan_week():
    try:
        day = int(request.args["day"])
        month = int(request.args["month"])
        year = int(request.args["year"])
        date(year, month, day)  # validate
    except (KeyError, ValueError, TypeError):
        return jsonify({"error": "Ungültige Datumsparameter"}), 400

    try:
        result = parse_starplan_week(day, month, year)
    except requests.RequestException:
        return jsonify({"error": "StarPlan-Server nicht erreichbar"}), 502

    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True)
