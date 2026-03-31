"""Generate a static HTML page with pre-computed course counts for a quarter.

Usage:
    python generate_static.py --quarter 2026-Q2 --output docs/index.html
"""

import argparse
import json
import os
import sys
import time
from datetime import date, timedelta

from app import parse_rapla_week, parse_starplan_week

QUARTER_MONTHS = {
    1: ("Januar\u2013M\u00e4rz", 1, 3),
    2: ("April\u2013Juni", 4, 6),
    3: ("Juli\u2013September", 7, 9),
    4: ("Oktober\u2013Dezember", 10, 12),
}


def mondays_in_quarter(year, quarter):
    """Yield all Mondays whose week falls (primarily) within the quarter."""
    _, first_month, last_month = QUARTER_MONTHS[quarter]
    # Start from the Monday on or before the 1st of the first month
    d = date(year, first_month, 1)
    d -= timedelta(days=d.weekday())  # back to Monday
    # End: last day of last month
    if last_month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, last_month + 1, 1) - timedelta(days=1)
    while d <= end:
        # Include if Thursday (middle of ISO week) falls in the quarter
        thursday = d + timedelta(days=3)
        if first_month <= thursday.month <= last_month and thursday.year == year:
            yield d
        d += timedelta(weeks=1)


def fetch_week(monday):
    """Fetch DHBW + HFU data for one week. Returns dict with both results."""
    day, month, year = monday.day, monday.month, monday.year

    rapla = None
    try:
        rapla = parse_rapla_week(day, month, year)
    except Exception as e:
        print(f"  DHBW-Fehler: {e}")

    starplan = None
    try:
        starplan = parse_starplan_week(day, month, year)
    except Exception as e:
        print(f"  HFU-Fehler: {e}")

    week_label = ""
    if rapla and "week" in rapla:
        week_label = rapla["week"]
    elif starplan and "week" in starplan:
        week_label = starplan["week"]

    return {
        "monday": monday.isoformat(),
        "week_label": week_label,
        "rapla": rapla,
        "starplan": starplan,
    }


HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kurszähler VS — {title}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            max-width: 900px;
            margin: 2rem auto;
            padding: 0 1rem;
            color: #333;
        }}
        h1 {{
            font-size: 1.4rem;
            margin-bottom: 0.5rem;
            color: #1a1a1a;
        }}
        .subtitle {{
            font-size: 0.9rem;
            color: #6b7280;
            margin-bottom: 1.5rem;
        }}
        .week-nav {{
            position: sticky;
            top: 0;
            background: white;
            padding: 0.6rem 0;
            border-bottom: 1px solid #e5e7eb;
            margin-bottom: 1rem;
            z-index: 10;
        }}
        .week-nav select {{
            padding: 0.4rem 0.6rem;
            border: 1px solid #ccc;
            border-radius: 4px;
            font-size: 0.95rem;
        }}
        .week-section {{
            margin-bottom: 2rem;
        }}
        .week-title {{
            font-size: 1rem;
            font-weight: 600;
            margin-bottom: 0.4rem;
            color: #1a1a1a;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
        }}
        th, td {{
            padding: 0.45rem 0.6rem;
            text-align: center;
            border-bottom: 1px solid #e5e7eb;
            border-right: 1px solid #e5e7eb;
        }}
        th {{ background: #f9fafb; font-weight: 600; }}
        tr.group-header th {{
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            color: #374151;
            background: #f3f4f6;
            border-bottom: 2px solid #d1d5db;
        }}
        tr.sub-header th {{
            font-size: 0.75rem;
            color: #6b7280;
            background: #f9fafb;
        }}
        td:first-child, th:first-child {{ text-align: left; }}
        .sum-cell {{ font-weight: 700; background: #f0f9ff; }}
        th.sum-col {{ background: #e0f2fe; color: #0369a1; }}
        .sep-left {{ border-left: 2px solid #9ca3af; }}
        tr:hover td {{ background: #f9fafb; }}
        tr:hover td.sum-cell {{ background: #e0f2fe; }}
        .number {{ font-variant-numeric: tabular-nums; }}
        .cell-error {{ color: #9ca3af; font-style: italic; }}
        .generated {{
            margin-top: 2rem;
            padding-top: 1rem;
            border-top: 1px solid #e5e7eb;
            font-size: 0.75rem;
            color: #9ca3af;
        }}
    </style>
</head>
<body>
    <h1>Kurszähler Villingen-Schwenningen</h1>
    <p class="subtitle">{title} — Laufende Kurse um 8:00, 9:00 und 13:00 Uhr</p>

    <div class="week-nav">
        <label for="week-select">Zur Woche springen:</label>
        <select id="week-select"></select>
    </div>

    <div id="content"></div>

    <p class="generated">Generiert am {generated}. Datenquellen: DHBW Rapla, HFU StarPlan.</p>

    <script>
    const DATA = {data_json};

    const TIMES = ['0800', '0900', '1300'];
    const content = document.getElementById('content');
    const weekSelect = document.getElementById('week-select');

    DATA.forEach((week, idx) => {{
        // Dropdown option
        const opt = document.createElement('option');
        opt.value = 'week-' + idx;
        opt.textContent = week.week_label || ('KW ' + week.monday);
        weekSelect.appendChild(opt);

        // Week section
        const section = document.createElement('div');
        section.className = 'week-section';
        section.id = 'week-' + idx;

        const title = document.createElement('h2');
        title.className = 'week-title';
        title.textContent = week.week_label || ('Woche ' + week.monday);
        section.appendChild(title);

        const table = document.createElement('table');
        table.innerHTML = `
            <thead>
                <tr class="group-header">
                    <th rowspan="2">Tag</th>
                    <th colspan="3" class="sep-left">Um 8:00</th>
                    <th colspan="3" class="sep-left">Um 9:00</th>
                    <th colspan="3" class="sep-left">Um 13:00</th>
                </tr>
                <tr class="sub-header">
                    <th class="sep-left">DHBW</th><th>HFU</th><th class="sum-col">&Sigma;</th>
                    <th class="sep-left">DHBW</th><th>HFU</th><th class="sum-col">&Sigma;</th>
                    <th class="sep-left">DHBW</th><th>HFU</th><th class="sum-col">&Sigma;</th>
                </tr>
            </thead>`;

        const tbody = document.createElement('tbody');
        const raplaDays = (week.rapla && week.rapla.days) || [];
        const starplanDays = (week.starplan && week.starplan.days) || [];
        const numDays = Math.max(raplaDays.length, starplanDays.length, 5);

        for (let i = 0; i < numDays; i++) {{
            const rd = raplaDays[i];
            const sd = starplanDays[i];
            const label = (rd && rd.label) || (sd && sd.label) || ('Tag ' + (i+1));

            const tr = document.createElement('tr');
            let html = '<td>' + label + '</td>';
            for (const t of TIMES) {{
                const rv = rd ? (rd['running_at_' + t] ?? 0) : null;
                const sv = sd ? (sd['running_at_' + t] ?? 0) : null;
                const sum = (rv ?? 0) + (sv ?? 0);
                const rvCell = rv !== null
                    ? '<span class="number">' + rv + '</span>'
                    : '<span class="cell-error">&ndash;</span>';
                const svCell = sv !== null
                    ? '<span class="number">' + sv + '</span>'
                    : '<span class="cell-error">&ndash;</span>';
                html += '<td class="sep-left">' + rvCell + '</td>'
                      + '<td>' + svCell + '</td>'
                      + '<td class="sum-cell number">' + sum + '</td>';
            }}
            tr.innerHTML = html;
            tbody.appendChild(tr);
        }}

        table.appendChild(tbody);
        section.appendChild(table);
        content.appendChild(section);
    }});

    weekSelect.addEventListener('change', function() {{
        document.getElementById(this.value).scrollIntoView({{ behavior: 'smooth' }});
    }});
    </script>
</body>
</html>
"""


def generate(year, quarter, output_path):
    label, _, _ = QUARTER_MONTHS[quarter]
    title = f"Q{quarter} {year} ({label})"
    mondays = list(mondays_in_quarter(year, quarter))

    print(f"Generiere {title}: {len(mondays)} Wochen")
    all_weeks = []

    for i, monday in enumerate(mondays):
        kw = monday.isocalendar()[1]
        print(f"  [{i+1}/{len(mondays)}] KW {kw} ({monday}) ...", end=" ", flush=True)
        data = fetch_week(monday)
        all_weeks.append(data)
        print("OK")
        if i < len(mondays) - 1:
            time.sleep(2)

    html = HTML_TEMPLATE.format(
        title=title,
        generated=date.today().strftime("%d.%m.%Y"),
        data_json=json.dumps(all_weeks, ensure_ascii=False),
    )

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nFertig: {output_path} ({len(html)} Bytes)")


def main():
    parser = argparse.ArgumentParser(description="Statische Quartals-Seite generieren")
    parser.add_argument(
        "--quarter", required=True,
        help="Quartal im Format YYYY-QN, z.B. 2026-Q2",
    )
    parser.add_argument(
        "--output", default="docs/index.html",
        help="Ausgabedatei (Standard: docs/index.html)",
    )
    args = parser.parse_args()

    parts = args.quarter.split("-Q")
    if len(parts) != 2:
        print("Fehler: Quartal muss im Format YYYY-QN sein (z.B. 2026-Q2)")
        sys.exit(1)

    year = int(parts[0])
    quarter = int(parts[1])
    if quarter not in (1, 2, 3, 4):
        print("Fehler: Quartal muss 1-4 sein")
        sys.exit(1)

    generate(year, quarter, args.output)


if __name__ == "__main__":
    main()
