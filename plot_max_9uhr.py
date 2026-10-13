"""Erzeuge ein Balkendiagramm: Maximum an Kursen um 9 Uhr pro Woche.

Liest die JSON-Daten aus einer vom generate_static.py erzeugten HTML-Datei
und plottet fuer jede Woche den hoechsten Tageswert (DHBW+HFU) um 9:00 Uhr.

Usage:
    python plot_max_9uhr.py --input uebersichten/Auslastung_Okt2025_bis_Sept2026.html
"""

import argparse
import json
import re
import sys
from pathlib import Path

import matplotlib.pyplot as plt


def load_data(html_path):
    text = Path(html_path).read_text(encoding="utf-8")
    m = re.search(r"const DATA = (.+?);\s*\n", text)
    if not m:
        raise ValueError("Konnte 'const DATA = ...' in HTML nicht finden.")
    return json.loads(m.group(1))


def max_9uhr_per_week(weeks):
    """Fuer jede Woche: max(DHBW+HFU) ueber alle Tage um 9:00."""
    rows = []
    for w in weeks:
        rapla_days = (w.get("rapla") or {}).get("days") or []
        starplan_days = (w.get("starplan") or {}).get("days") or []
        n = max(len(rapla_days), len(starplan_days), 0)
        best = 0
        for i in range(n):
            r = rapla_days[i] if i < len(rapla_days) else {}
            s = starplan_days[i] if i < len(starplan_days) else {}
            rv = r.get("running_at_0900", 0) or 0
            sv = s.get("running_at_0900", 0) or 0
            best = max(best, rv + sv)
        rows.append({
            "monday": w["monday"],
            "week_label": w.get("week_label", ""),
            "max_9": best,
        })
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Von generate_static.py erzeugte HTML")
    parser.add_argument("--output", help="Ziel-PNG (Default: neben Input, _max9uhr.png)")
    parser.add_argument("--title", default="Maximale Kursanzahl um 9:00 Uhr pro Woche (DHBW + HFU)",
                        help="Diagramm-Titel")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Fehler: {input_path} nicht gefunden")
        sys.exit(1)

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.with_name(input_path.stem + "_max9uhr.png")

    weeks = load_data(input_path)
    rows = max_9uhr_per_week(weeks)
    print(f"Geladen: {len(rows)} Wochen")

    labels = [r["week_label"] or f"KW {r['monday']}" for r in rows]
    values = [r["max_9"] for r in rows]

    # Farbe pro Quartal (aus Monat des Montags)
    def color_for(monday_iso):
        month = int(monday_iso.split("-")[1])
        q = (month - 1) // 3 + 1
        return {1: "#60a5fa", 2: "#34d399", 3: "#fbbf24", 4: "#f87171"}[q]

    colors = [color_for(r["monday"]) for r in rows]

    fig, ax = plt.subplots(figsize=(16, 6))
    bars = ax.bar(range(len(rows)), values, color=colors, edgecolor="white", linewidth=0.5)

    # Werte ueber den Balken
    for bar, v in zip(bars, values):
        if v > 0:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(values) * 0.01,
                    str(v), ha="center", va="bottom", fontsize=8, color="#374151")

    ax.set_xticks(range(len(rows)))
    ax.set_xticklabels(labels, rotation=90, fontsize=8)
    ax.set_ylabel("Kurse (Max ueber alle Wochentage)")
    ax.set_title(args.title, fontsize=12, fontweight="bold", pad=12)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # Legende fuer Quartale
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor="#60a5fa", label="Q1 (Jan-Maerz)"),
        Patch(facecolor="#34d399", label="Q2 (Apr-Juni)"),
        Patch(facecolor="#fbbf24", label="Q3 (Juli-Sept)"),
        Patch(facecolor="#f87171", label="Q4 (Okt-Dez)"),
    ]
    ax.legend(handles=legend_elements, loc="upper right", frameon=False, fontsize=9)

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"Fertig: {output_path}")


if __name__ == "__main__":
    main()
