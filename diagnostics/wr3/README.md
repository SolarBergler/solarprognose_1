# WR3 – Schattenverdacht am 14. November 2026 (getrennte Testversion)

**Keine Produktionsänderung.** Der produktive Prognosecode (`index.html`), die veröffentlichten DOM20-Profile, Modulgeometrien, Automationen und archivierten Originalprognosen auf `main` bleiben unverändert.

## Vorgehen

Das eigenständige Diagnoseprogramm `compare.mjs` liest **lokal** die vom Betreiber bereitgestellte Originaldatei `PV_SolarEdge_Kiosk_Ertraege.json`. Es prüft die bestätigte 24-Modul-Seriennummern-Zuordnung und verwendet nur vorhandene Paare von Optimierer-DC-Leistung und Ausgangsspannung. Keine fehlenden Werte werden interpoliert oder zu Null ergänzt.

Es vergleicht 18 gleichartige Trina-400-Wp-Module: Ein Kandidat muss im Morgen-Referenzfenster mindestens einmal 150 W erreicht haben, zum Vergleichszeitpunkt bei unter 75 V weniger als 25 % eines zeitgleich starken, nicht bei 80 V begrenzten anderen Trina-Moduls (mindestens 130 W) liefern. Das Ergebnis ist ein **Schattenverdacht**, kein optischer Beweis.

`dom20-mask-2026-11-14.json` hält die **aus V12.9.10 getrennt berechnete Direktsonnenmaske** der Carportmodule für 09:00–15:30 Uhr im 5-Minutenraster fest (24-Bit, Modulnummer 3.1.1 bis 3.1.24). Sonnenazimut und -höhe stammen aus der NOAA-Berechnung der produktiven Website, Hinderniswinkel aus dem veröffentlichten DOM20- und Fernhorizont. Dieser festgehaltene Snapshot verändert das Modell nicht.

Reproduzierbar lokal (Node.js 20+):

```bash
node --test diagnostics/wr3/compare.test.mjs
node diagnostics/wr3/compare.mjs /PFAD/PV_SolarEdge_Kiosk_Ertraege.json > wr3-shadow-evidence.json
```

## Erste Ergebnisse aus der Originaldatei

288 Export-Zeitstempel, 13 Module mit starkem Morgenreferenzwert. Unter den 251 tatsächlich vergleichbaren Modul-Zeitpaaren gibt es 51 Schattenverdachtsfälle. **14** widersprechen der aktuellen DOM20-Direktsonnenmaske; sie betreffen **7 Module an 8 Zeitpunkten**.

Beispiele: **3.1.9 / 3.1.10 um 12:30**: 21,14 W / 16,39 W, zeitgleiches leistungsstarkes Trina-Modul 162,39 W. Das Modell erwartet direkte Sonne; Sonne bei rund 188,6° Azimut und 23,6° Höhe. Auch 12:25 liegen Widersprüche vor. Ein reiner 5-Minuten-Zeitversatz erklärt diese Beispiele nicht; das veröffentlichte DOM20-Modell meldet 12:10–12:40 durchgehend direkte Sonne an beiden Modulen.

**Grenzen:** Das ist nur ein Tag; die Export-Zeitzuordnung und die elektrisch/optisch bedingten Leistungsanteile sind nicht vollständig trennbar. Relative Optimiererleistung ist **keine** direkt vermessene Hindernishöhe. Es gibt daher **keine automatische Ableitung einer 360°-Korrektur**, keinen neuen Ertragsfaktor und keinen behaupteten Energiegewinn. Vor einer Modellübernahme müssen die vermuteten Schattengeber anhand eines unabhängigen Tages oder einer bestätigten Geometrie geprüft werden. Rohmessungen und Seriennummern werden ausdrücklich nicht in das öffentliche Repository hochgeladen.
