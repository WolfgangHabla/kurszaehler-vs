# Session Changelog

## 2026-02-25 — Initiale Erstellung des Rapla Kurszählers

### Neues Projekt angelegt
- Projektverzeichnis `rapla-counter/` mit Flask-Backend und einfacher Web-Oberfläche erstellt
- Zweck: Automatisches Zählen, wie viele Kurse zu bestimmten Uhrzeiten laufen, basierend auf dem DHBW Rapla-Kalender (Standort VS)

### Erstellte Dateien
- **`app.py`** — Flask-Backend mit Rapla-HTML-Parser (BeautifulSoup), API-Endpoint `/api/week`
- **`templates/index.html`** — Web-Oberfläche mit Wochenauswahl (Vor/Zurück-Buttons), automatischem Laden
- **`requirements.txt`** — Dependencies: flask, beautifulsoup4, requests

### Funktionsweise
- Rapla-Seite wird serverseitig abgerufen (kein CORS-Problem)
- HTML wird geparst: `<td class="week_block">` Elemente mit Zeitbereichen per Regex extrahiert
- Zähllogik: Ein Kurs "läuft um X Uhr" wenn `Startzeit <= X < Endzeit`
- Zeigt Mo–Fr einer gewählten Woche auf einen Blick

### Änderungen während der Session
1. **Spalte "Gesamt" entfernt** — Gesamtzahl der Kurse pro Tag wird nicht benötigt, nur die Uhrzeiten sind relevant
2. **8:00 Uhr als Prüfzeit hinzugefügt** — Tabelle zeigt jetzt drei Spalten: Um 8:00, Um 9:00, Um 13:00

### Verifizierte Testdaten (KW 9, 23.–27. Feb 2026)
| Tag       | Um 8:00 | Um 9:00 | Um 13:00 |
|-----------|---------|---------|----------|
| Mo 23.02. | 4       | 18      | 16       |
| Di 24.02. | 3       | 15      | 12       |
| Mi 25.02. | 4       | 19      | 14       |
| Do 26.02. | 8       | 22      | 14       |
| Fr 27.02. | 14      | 28      | 22       |

### Hinweis zu den verifizierten Daten
Die "verifizierten Testdaten" oben waren vermutlich Wochensummen (5 aufeinanderfolgender Wochen), nicht Tageswerte — der ursprüngliche Parser war fehlerhaft (siehe Session 2026-03-10).

### Nutzung
```
cd rapla-counter
python app.py
# Browser: http://127.0.0.1:5000
```

---

## 2026-03-10 — HFU StarPlan-Integration + Rapla-Parser-Fix

### Neue Funktion: HFU VS via StarPlan
- `app.py` erweitert: `parse_starplan_week()` + `/api/starplan/week` Route
- Ansatz: Raumbasierte Abfrage aller 61 VS-Räume parallel (ThreadPoolExecutor, 12 Worker)
- StarPlan-API: `https://splan.hs-furtwangen.de/starplan/json?m=...` (erfordert JSESSIONID)
- Tag-Zuordnung via CSS `left`-Position der `.ttevent` Divs, Spaltengrenzen dynamisch aus `.ttweekdaycell`-Headern geparst

### Tabelle jetzt nebeneinander
- `templates/index.html` neu: DHBW | HFU | Σ für jede Uhrzeitspalte (Um 8:00, Um 9:00, Um 13:00)
- Beide APIs werden parallel per `Promise.allSettled` geladen; Teilausfälle werden mit "–" angezeigt

### Rapla-Parser korrigiert
- Alter Ansatz (`pages=5`) lieferte 5 aufeinanderfolgende Montage (eine Tabelle pro Woche), nicht Mo–Fr
- Neuer Ansatz: Einzelne Wochentabelle ohne `pages=`-Parameter; spaltenbasiertes Parsing mit Rowspan-Tracking
- Rapla hat eine einzige `week_table` mit allen Tagen als Spalten (colspan in Header-Zeile)

### Wichtige technische Details
- `STARPLAN_JSON = "https://splan.hs-furtwangen.de/starplan/json"` (nicht `.../mobile/json`)
- `STARPLAN_SEMESTER = 6` (SoSe 2026) — bei Semesterwechsel aktualisieren
- VS-Räume: 61 Räume, Kurzbezeichnungen beginnen mit "A"

### Verifizierte Daten (KW 11, 09.–14. März 2026)
| Tag       | DHBW 8:00 | HFU 8:00 | DHBW 9:00 | HFU 9:00 | DHBW 13:00 | HFU 13:00 |
|-----------|-----------|----------|-----------|----------|------------|-----------|
| Mo 09.03. | 6         | 21       | 15        | 26       | 13         | 6         |
| Di 10.03. | 4         | 24       | 17        | 31       | 11         | 11        |
| Mi 11.03. | 3         | 34       | 12        | 38       | 13         | 11        |
| Do 12.03. | 3         | 36       | 14        | 41       | 11         | 11        |
| Fr 13.03. | 0         | 22       | 11        | 24       | 7          | 19        |
| Sa 14.03. | 0         | 0        | 0         | 0        | 0          | 4         |

---

## 2026-03-30 — Feiertage, Online/Exkursion-Filter, StarPlan-Analyse

### Feiertage in Baden-Württemberg
- 12 gesetzliche Feiertage (7 feste + 5 Ostern-basierte) werden erkannt
- `_easter_sunday(year)` berechnet Ostersonntag per Anonymous-Gregorian-Algorithmus
- `_holidays_bw(year)` gibt Set aller BW-Feiertage zurück
- An Feiertagen: Alle Kurszähler (DHBW + HFU) werden auf 0 gesetzt

### Rapla-Filter: Online & Exkursionen
- Einträge mit "online" (case-insensitive, beliebige Position im Text) werden übersprungen
- Einträge mit "Ausflug" oder "Exkursion" werden übersprungen
- Beide Filter greifen vor der Zählung in `parse_rapla_week()`

### StarPlan-API-Analyse
- **Befund:** Alle StarPlan-Endpunkte (`getTT`, `searchRooms`) liefern nur generische Wochenstundenpläne — `dfc`-Parameter wird ignoriert
- **iCal-Export** ist gesperrt (HTTP 400 "No rights to view this plan as ical")
- Konsequenz: HFU-Zahlen sind für jede Woche identisch; zweiwöchige Veranstaltungen nicht erkennbar

### Geplant (noch nicht umgesetzt)
- **Render.com Hosting** — weiterhin offen

---

## 2026-03-31 — Datumsspezifische HFU-Daten & statische Quartalsseite

### StarPlan `sd=true` — datumsspezifische Stundenpläne
- **Entdeckung:** `getTT` mit `sd=true` ("Mit Datum") liefert wochenspezifische Events
- Vorher (`sd=false`): Jede Woche identische generische Zahlen
- Nachher (`sd=true`): KW 12 (99 Events/Mo), KW 14 (115 Events/Mo), Ferien (0)
- `STARPLAN_SEMESTER`-Konstante entfernt → automatische Erkennung via `getpus`
- Session-Init und `_fetch_room_week()` auf `sd=true` umgestellt
- Neue Funktionen: `_starplan_semester_for_date()`, `_empty_starplan_week()`
- `HFU_LECTURE_PERIODS` nicht nötig — API erledigt Vorlesungszeit-Filterung automatisch

### Statische Quartalsseite (`generate_static.py`)
- Neues Batch-Skript: `python generate_static.py --quarter 2026-Q2 --output docs/index.html`
- Iteriert durch alle Wochen eines Quartals, ruft DHBW + HFU Daten ab
- Erzeugt eigenständige HTML-Datei mit eingebettetem JSON (kein Server nötig)
- Dropdown zur Wochennavigation, alle Tabellen untereinander
- 2-Sekunden-Pause zwischen Wochen (Server-Schonung)
- Hosting-Empfehlung: GitHub Pages (kostenlos, `docs/`-Ordner)
