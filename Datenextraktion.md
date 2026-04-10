# Datenextraktion Kurszähler Villingen-Schwenningen

Dieses Dokument beschreibt, wie die Daten zu laufenden Kursen an der DHBW und HFU
in Villingen-Schwenningen extrahiert werden. Für jeden Wochentag wird gezählt, wie
viele Kurse um 8:00, 9:00 und 13:00 Uhr gleichzeitig stattfinden.

---

## DHBW Villingen-Schwenningen (Rapla)

### Datenquelle

Die DHBW nutzt **Rapla** als Stundenplansystem. Die Daten werden über eine
öffentliche Kalender-URL abgerufen:

```
https://rapla.dhbw.de/rapla/calendar?key=...&salt=...&day=D&month=M&year=Y
```

Die URL enthält einen API-Key, der den Zugang zum DHBW-VS-Gesamtkalender
ermöglicht. Die Parameter `day`, `month`, `year` bestimmen die angezeigte Woche
(Rapla zeigt die Woche, in die das angegebene Datum fällt).

### Ablauf der Extraktion

1. **HTTP-Request**: Die Rapla-URL wird mit dem gewünschten Datum aufgerufen.
   Rapla liefert eine HTML-Seite mit einer Wochentabelle (`week_table`).

2. **Tabellen-Parsing**: Die Wochentabelle enthält alle Tage (Mo–Sa) als Spalten
   nebeneinander. Jeder Kurs ist eine Tabellenzelle mit der CSS-Klasse
   `week_block`. Die Zuordnung zu Wochentagen erfolgt über die Spaltenposition,
   wobei ein Rowspan-Tracking-Algorithmus die korrekte Spaltenzuordnung
   sicherstellt (Kurse können sich über mehrere Zeilen erstrecken).

3. **Zeitextraktion**: Aus dem Text jeder `week_block`-Zelle wird per Regex
   die Start- und Endzeit extrahiert (Format `HH:MM - HH:MM`).

4. **Filter**: Folgende Einträge werden übersprungen:
   - Einträge mit **"online"** im Text (case-insensitive) — Online-Veranstaltungen
     finden nicht vor Ort statt
   - Einträge mit **"Ausflug"** oder **"Exkursion"** im Text — Studierende sind
     nicht am Campus

5. **Feiertage**: An gesetzlichen Feiertagen in Baden-Württemberg (12 Feiertage,
   davon 5 Ostern-basiert) werden alle Zähler auf 0 gesetzt, auch wenn Rapla
   Einträge anzeigt.

6. **Zählung**: Für jeden Wochentag wird gezählt, wie viele Kurse zu den drei
   Prüfzeitpunkten (8:00, 9:00, 13:00) laufen. Ein Kurs "läuft" zu einem
   Zeitpunkt, wenn `Startzeit <= Prüfzeitpunkt <= Endzeit`.

### Besonderheiten

- Rapla liefert **eine einzige Wochentabelle** pro Abfrage (Mo–Sa als Spalten).
- Die Tabelle nutzt `colspan` und `rowspan` extensiv — ein Algorithmus trackt
  belegte Zellen über Zeilen hinweg, um die korrekte Spaltenzuordnung zu gewährleisten.
- Die Daten sind **datumsspezifisch**: Jede Woche zeigt die tatsächlich
  stattfindenden Kurse.

---

## HFU Villingen-Schwenningen (StarPlan)

### Datenquelle

Die HFU nutzt **StarPlan** (Hersteller: ProGotec) als Stundenplansystem. Die Daten
werden über eine JSON/HTML-API abgerufen:

```
Basis-URL:   https://splan.hs-furtwangen.de/starplan/mobile   (Session-Init)
API-URL:     https://splan.hs-furtwangen.de/starplan/json     (Datenabfragen)
```

Wichtig: Die API-URL liegt unter `/starplan/json`, **nicht** unter
`/starplan/mobile/json` — das JavaScript auf der Seite sendet relative URLs,
die vom Browser zum übergeordneten Pfad aufgelöst werden.

### Ablauf der Extraktion

1. **Semester ermitteln**: Über den Endpunkt `getpus` wird die Liste aller
   Semester abgerufen (JSON). Anhand des Abfragedatums wird automatisch das
   passende Semester bestimmt (z.B. SoSe 2026 = ID 6, Zeitraum 01.03.–31.08.).
   Fällt das Datum in kein Semester, wird eine leere Woche (alle Werte 0)
   zurückgegeben.

2. **Session initialisieren**: Eine HTTP-Session wird mit dem richtigen Semester
   und dem Parameter `sd=true` ("Mit Datum") aufgebaut. Dieser Parameter ist
   entscheidend: Mit `sd=true` liefert StarPlan **datumsspezifische**
   Stundenplandaten; ohne diesen Parameter (`sd=false`) wird nur ein generischer
   Wochenplan geliefert, der für jede Woche identisch ist.

3. **Raumliste abrufen**: Über `getros` (get rooms) mit `loc=2` (Standort
   Villingen-Schwenningen) wird die Liste aller 61 VS-Räume abgerufen (JSON).

4. **Stundenpläne parallel abrufen**: Für jeden der 61 Räume wird der Endpunkt
   `getTT` (get timetable) mit folgenden Parametern aufgerufen:
   - `sel=ro` (Selektion: Raum)
   - `pu={semester_id}` (Semester)
   - `ro={room_id}` (Raum-ID)
   - `dfc={monday_iso}` (Datum der Woche, ISO-Format)
   - `sd=true` (datumsspezifische Ansicht)

   Die Abfragen erfolgen parallel (12 gleichzeitige Threads) und dauern
   insgesamt ca. 10–15 Sekunden.

5. **HTML-Parsing**: `getTT` liefert ein HTML-Fragment (kein JSON). Jeder Kurs
   ist ein `<div class="ttevent">` mit einer CSS-Position (`left: Xpx`).
   Die Zuordnung zu Wochentagen erfolgt über die `left`-Werte:
   - Die Tages-Spaltenüberschriften (`ttweekdaycell`) definieren die
     Pixel-Grenzen jedes Wochentags
   - Ein Event gehört zu dem Tag, dessen Spalten-Startposition am nächsten
     links liegt

6. **Zeitextraktion**: Aus dem Text jedes `ttevent`-Divs wird per Regex
   die Start- und Endzeit extrahiert (Format `HH:MM - HH:MM`).

7. **Feiertage**: Wie bei der DHBW werden an gesetzlichen Feiertagen in
   Baden-Württemberg alle Zähler auf 0 gesetzt.

8. **Zählung**: Identisch zur DHBW — für jeden Tag wird gezählt, wie viele
   Kurse zu den Prüfzeitpunkten 8:00, 9:00, 13:00 laufen.

### Besonderheiten

- **Nur physische VS-Räume**: `loc=2` beschränkt die Abfrage auf den Campus
  Villingen-Schwenningen (keine Online-Räume, kein Furtwangen/Tuttlingen).
- **`sd=true` ist entscheidend**: Ohne diesen Parameter liefert die API
  identische Daten für jede Woche. Mit `sd=true` werden vorlesungsfreie Zeiten,
  Semesterferien und zweiwöchige Veranstaltungen korrekt abgebildet.
- **Kein Bulk-Endpoint**: Es gibt keine Möglichkeit, alle Räume in einem
  Request abzufragen — daher die 61 parallelen Einzelabfragen.
- **iCal-Export gesperrt**: StarPlan bietet theoretisch einen iCal-Export,
  dieser ist für die HFU aber deaktiviert (HTTP 400).

---

## Gemeinsame Nachbearbeitung

### Feiertage in Baden-Württemberg

An den 12 gesetzlichen Feiertagen in BW werden für beide Hochschulen alle
Kurszähler auf 0 gesetzt:

**Feste Termine:** Neujahr (1.1.), Heilige Drei Könige (6.1.), Tag der Arbeit
(1.5.), Tag der Deutschen Einheit (3.10.), Allerheiligen (1.11.),
1. Weihnachtstag (25.12.), 2. Weihnachtstag (26.12.)

**Bewegliche Termine (Ostern-basiert):** Karfreitag (Ostern−2), Ostermontag
(Ostern+1), Christi Himmelfahrt (Ostern+39), Pfingstmontag (Ostern+50),
Fronleichnam (Ostern+60)

Der Ostersonntag wird per Anonymous-Gregorian-Algorithmus berechnet.

### Prüfzeitpunkte

Für jeden Wochentag wird gezählt, wie viele Kurse zu folgenden Zeitpunkten
gleichzeitig laufen:

| Zeitpunkt | Bedeutung |
|-----------|-----------|
| 8:00 Uhr  | Früheste reguläre Vorlesungszeit |
| 9:00 Uhr  | Häufigster Vorlesungsbeginn |
| 13:00 Uhr | Nachmittagsvorlesungen |

Ein Kurs wird gezählt, wenn `Startzeit <= Prüfzeitpunkt <= Endzeit`.

### Statische Quartalsseite

Das Skript `generate_static.py` iteriert durch alle Wochen eines Quartals,
ruft für jede Woche die DHBW- und HFU-Daten ab und erzeugt eine eigenständige
HTML-Datei:

```
python generate_static.py --quarter 2026-Q2 --output docs/index.html
```

Die generierte Seite enthält alle Wochendaten als eingebettetes JSON und
benötigt keinen Server zur Anzeige.
