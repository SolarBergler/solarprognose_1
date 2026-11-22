# Solarprognose

## Modulwirkungsgrad bei geringer Einstrahlung (V12.9.13)

Anlage Schliersee, Konfigurationsrevision 11. Der Rechenkern berücksichtigt
jetzt, dass der Wirkungsgrad der Siliziummodule von Einstrahlung und
Zelltemperatur abhängt. Das Modell verwendet die veröffentlichte
[PVGIS-Kennlinie für kristallines Silizium](https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis/general-information/data-sources-calculation-methods_en).
Die Kennlinie wird zwischen 100 und 1100 W/m² ausgewertet. Jenseits dieser
Grenzen gilt jeweils der Wirkungsgrad am Rand, während die berechnete
Leistung der tatsächlichen Einstrahlung folgt. Das vermeidet eine freie
Extrapolation, insbesondere in der Dämmerung. Die Kennlinie ist eine
Technologiereferenz für die Anlage, keine gemessene Modulkennlinie vor Ort.

Der Vergleich über 17 Novembertage verwendet denselben archivierten
Morgen-Wetterstand und dieselben Schattenprofile für beide Rechenvarianten.
Der mittlere absolute Fehler sinkt von 9,06 auf 7,84 kWh pro Tag. Die fünf
zusätzlichen Tage vom 3. bis 8. November verbessern sich von 16,03 auf
13,60 kWh pro Tag. Bei zu niedrig prognostizierter Einstrahlung kann auch
die neue Ertragsprognose weiter unter dem Istwert liegen. Der Testumfang
deckt Novemberbedingungen ab.

Die Kennlinie gehört zur physikalischen Modellkennung. Beim Wechsel bleiben
früher gespeicherte Prognosen unter ihrer ursprünglichen Kennung erhalten.
Konfigurationen ohne die Kennliniendefinition bleiben mit der bisherigen
Berechnung reproduzierbar.

## Stündliche Restprognose für heute (V12.9.12)

Neben Produktionsbeginn und -ende zeigt **„Noch zu erwarten heute“** die verbleibende Energie ab der aktuellen Uhrzeit. Sie wird aus der neuesten berechneten Kurve gebildet: vergangene Abschnitte zählen nicht mit, vom laufenden Fünfminuten-Intervall nur der noch verbleibende Teil. Ein vollständiger Tag mit null weiterer Prognose wird als 0,0 kWh angezeigt; fehlende oder lückenhafte Zukunftsdaten als nicht verfügbar.

Bei geöffneter, sichtbarer Seite wird das Wetter zur nächsten vollen Stunde erneut geladen. Ein überfälliger Abruf wird beim Zurückkehren in den Tab nachgeholt; Fokus- und Sichtbarkeitsereignisse starten keinen doppelten Abruf. Die Restmenge selbst läuft jede Minute mit. Die Anzeige nennt den Wetterabruf bzw. die DWD-Ausgabe und kennzeichnet Cache-/Fehlerstände. Ein geschlossener Browser aktualisiert sich nicht im Hintergrund.

Die ursprünglichen Vergleichskurven und bereits begonnenen Prognoseintervalle behalten ihre bisherige Archivierungslogik. Die Restanzeige verwendet bewusst die neue Rohberechnung anstelle der aus alten und neuen Intervallen zusammengesetzten Tageskurve. Berechnung, Anlagenwerte, Profile und 06-/18-Uhr-Archivläufe werden dadurch nicht verändert.

Ein vorhandener Fehler in der Monat/Jahr-Eingabe der Modul-Inbetriebnahme ist ebenfalls behoben: gültige Monate werden wieder angezeigt und akzeptiert. Bestehende Inbetriebnahmedaten und Alterungsberechnung bleiben gleich.

Zusätzliche Prüfungen: `node --test tests/remaining-forecast.test.cjs` und `python tests/test_remaining_forecast.py`. Wie die vorhandenen Browsertests verwendet letzterer einen fest angehefteten Wetterstand aus Git; alternativ kann `PV_TEST_WEATHER_FIXTURE` auf dieselbe JSON-Fixture zeigen. Er prüft in Chromium stündliche Aktualisierung, Rückkehr zum Tab, erhaltene Originale, Cache-Kennzeichnung und die schmale Darstellung.

## Wetter-Originaldaten künftig mit jeder 06-/18-Uhr-Prognose einfrieren

Neue Prognosearchive enthalten zusätzlich `forecastWeatherSnapshot` mit
den **tatsächlich im Browser für die Rechnung verwendeten** Stunden- und
gegebenenfalls 15-Minuten-Wetterfeldern (DNI, DHI, GHI, Temperatur usw.).
Gespeichert werden der damalige Wetteranbieter, die Ausgabekennung,
Prognosetag, -slot, Modellhash und zentrale Konfigurationskennung.

Dies ermöglicht später faire Gegenrechnungen neuer PV-Verschattungsmodelle
mit identischen *damals vorhergesagten* Wetterdaten. Bereits existierende
historische `06.json`-/`18.json`-Dateien werden nicht nachträglich mit
heutigen Wetterdaten aufgefüllt oder überschrieben. Bei fehlendem oder
ungültigem Wetterinput steht stattdessen ein expliziter
`forecastWeatherSnapshotStatus` im neuen Archiv; die bewährte
Prognosearchivierung wird dadurch nicht blockiert. Vor allem historische
18-Uhr-Snapshots können bereits eingefrorene Morgen-/Nachmittagsleistungen
enthalten; allein der 18-Uhr-Wetterstand rekonstruiert diese nicht.

## SolarEdge-AC-Tageswerte automatisch validieren

Der vorhandene AC-Prüfer benötigt keine Modul- oder Optimierer-Telemetrie.
Er akzeptiert jetzt entweder eine CSV mit `date,ac_kwh` oder unmittelbar das
gespeicherte SolarEdge-Kiosk-JSON-Archiv mit `dailyEnergy`:

```bash
python scripts/validiere_ac.py \
  --actual /pfad/zum/PV_SolarEdge_Kiosk_Ertraege.json \
  --archive prognosen \
  --slot 06 \
  --output ac_validierung.json
```

`historical_reported_value` wird als historisch *gemeldet*, **nicht**
als abschließend zertifiziert, eingestuft. `evening_reported_value_not_final`
und `intraday_provisional` sind vorläufig und werden standardmäßig
ausgeschlossen. Unbekannte Stati, doppelte Tage, negative Werte und
unvereinbare Wh-/kWh-Angaben führen zu einem Fehler.

Die Auswertung trennt neben physikalischem Modellhash und Nahprofil-ID
auch die konkrete Programmversion, damit unterschiedliche Releases
nicht zu einer einzigen Zeitreihe verschmelzen. Historische
Originalprognosen werden nicht überschrieben. Es wird kein nachträglich
beobachtetes Wetter als damalige Vorhersage ausgegeben.

## Optionales Neun-Punkte-Flächenmodell (experimentelle Schnittstelle)

Die reguläre PV-Prognose braucht **keine Modul-/Optimierer-Telemetrie**. Die
geometrische Nahverschattung kann optional je Modul aus neun unabhängigen
Sichtlinien der Modulfläche berechnet werden. Die AC-Validierung erfolgt
getrennt über `scripts/validiere_ac.py`.

Dafür darf ein `panelProfiles[]`-Eintrag in `nahverschattung.json` zusätzlich
`areaSamples` enthalten: ein Array in derselben Reihenfolge wie `samples`,
für jedes Modul entweder `null` (bewährter Mittelpunkt-Fallback) oder exakt
**neun** Horizontarrays mit jeweils **720** Winkeln in 0,5°-Abständen
(geografischer Azimut, Grad über Horizont). Die Fläche wird bei der direkten
Einstrahlung zu neun gleichen Teilflächen aufgelöst; die diffuse
Himmelslichtkomponente wird ebenfalls flächengewichtet ermittelt.

Diese Erweiterung ist rückwärtskompatibel: Solange `areaSamples` in den
zentral veröffentlichten Profilen fehlt, bleiben die bisherigen Mittelpunkt-
Berechnungen unverändert. Neue 88-Modul-Flächendaten dürfen nur zusammen mit
der dazu passenden Geometrie und den vorgeschriebenen SHA-256-Profilbindungen
veröffentlicht werden. Die vorliegenden 792 LiDAR-Testprofile sind **noch
nicht** als produktiver Datensatz aktiviert, da die AC-Gesamtvalidierung der
neuen Geometrie noch aussteht. Es erfolgt **keine** Anpassung von Dachneigungen
oder Systemverlusten an Einzelmodulleistungen.

PV-Prognose mit Gelände- und DOM20-Nahverschattung. Website: https://solarbergler.github.io/solarprognose_1/

## Modulalter und Eingabefeld in „Modulfelder bearbeiten“ (V12.9.10)

Die vom Betreiber angegebenen Inbetriebnahmemonate sind für alle **88 Module** in 11 Modulgruppen hinterlegt: IBC 300 (33 Stück, 10/2016), Winaico 330 (16, 01/2019), Trina 400 Carport (18, 07/2020), JA Solar 415 Haus rechts (5, 05/2021), LONGi 450 Carport (6, 04/2022), Jinko 380 Hütte (5, 10/2023), LONGi 450 Haus links (5, 04/2024).

Im Dialog zur Bearbeitung bzw. Neuerstellung von Modulfeldern gibt es jetzt ein Feld **„Inbetriebnahme (Monat / Jahr)“**. Bei mehreren Modulgruppen innerhalb eines Modulfeldes erhält jede Gruppe einen eigenen Monatseingang. Bei neuen Modulfeldern ohne Einzelmodulbestückung ist der Monat Pflicht und der altersabhängige Verlust wirkt auf die gesamte Feldleistung. Bei bereits vorhandenen Gruppen ist er bearbeitbar; die Basisdaten bleiben unverändert, wenn das Datum geleert wird. Intern wird der erste Tag des angegebenen Monats als Berechnungsstichtag verwendet; die Genauigkeit ist als „Monat“ dokumentiert.

Die zunächst eingetragene Degradation von 1 % pro Jahr ist eine **vorläufige Modellannahme**, keine gemessene Materialalterung. Die Leistung wird zeitabhängig je Gruppe vor Wechselrichterbegrenzung reduziert. Unterschiedliche LONGi-Jahrgänge bleiben getrennt. Alte Originalprognosen sind unverändert. Verschattungsgeometrie, DOM20, GPS und nominale DC-Leistung von 31,305 kWp bleiben unverändert. Die aktiven Altersannahmen sind im neuen physikalischen Modellhash enthalten.

## Altersabhängige Modulleistung – Modellvorbereitung V12.9.9

Optional `moduleGroups[].commissionedOn` (ISO-Datum YYYY-MM-DD) und `annualDegradationPct` (0 bis 5) je Modulgeneration. Einzelmodule erhalten einen altersabhängigen STC-Leistungsfaktor: `(1-r/100)^max(0, (Prognosezeit-Inbetriebnahme)/365.2425 Tage)`. Unterschiedliche Modulgruppen im selben Feld werden mit ihren jeweiligen Wp gewichtet, auch beim DOM20-Nahprofil. Der Faktor wirkt vor AC-Clipping; keine pauschale Korrektur zusätzlich bei Systemverlusten eintragen.

Bei bekanntem Datum und ohne explizite Rate gilt 1 % pro Jahr als **Szenario**, nicht als gemessene Anlagenrate. Fehlt das Inbetriebnahmedatum, beträgt der Faktor exakt 1, ohne geschätztes Baujahr. Derzeit sind für die sechs verschiedenen Modultypen keine Inbetriebnahmedaten belegt: Die Berechnung zeigt daher zunächst unveränderte Erträge und weist in der Website sichtbar auf die fehlenden Daten hin. Sobald Daten eingetragen werden, wechselt die physikalische Modellkennung, damit Originalarchive nicht vermischt werden. Konfigurationsrevision 9 und alle DOM20/GPS-Daten bleiben bis dahin unverändert.

Die Rate ist von Wetter-/Verschattungsfehlern und den bestehenden 12 % pauschalen Systemverlusten getrennt. Sie erklärt keinen spezifischen mittäglichen Carport-Schatteneinbruch.

## Ausrichtungsraster zum Hausdach korrigiert in V12.9.8

Alle Modulgruppen der Anlage stehen rechtwinklig oder parallel zur Hausdachreferenz **165°**, also 75°, 165°, 255° oder 345°. Die Hütte vorne wurde von 254° auf den bestätigten Azimut **255°** korrigiert. Die fünf Einzelpositionen wurden um den unveränderten Mittelpunkt 2.1.19 in diesem Raster neu berechnet (äußere Module um ca. 3,7 cm versetzt). Die vier veränderten Modulhorizonte wurden anhand derselben Original-DOM20-Daten erneut berechnet; alle übrigen 84 Modulpositionen und Modulhorizonte wurden unverändert übernommen.

Der Geometriehash und das Nahprofil sind neu versioniert. Die bisherigen Originalprognosen bleiben unverändert. Der Layoutgenerator und Regressionstests sind angepasst.

## Hütte vorne: Fünferreihe ohne seitliche Stufen in V12.9.7

Die türkisfarbenen Module 2.1.17 bis 2.1.21 waren im SVG trotz korrekt hinterlegter geodätischer Modulmittelpunkte gegeneinander versetzt. Ursache: Im Transformationsschritt der Dachachsen in die Bildachsen hatten die beiden gemischten Sinus-Terme das falsche Vorzeichen. Bei 254° statt exakt 255° fielen dadurch kleine sichtbare Treppenversätze auf. Die Modulpunkte und die Modulpolygonachsen stimmen nun überein; die vier Übergänge bilden eine durchgehende gerade Flucht mit jeweils etwa 24,4 mm Fuge (25 mm vorgesehen; Rundungsabweichung durch die unterschiedlichen Projektionen).

Nur die SVG-Darstellung wurde korrigiert. Azimut Hütte 254°, alle 88 Modulkoordinaten, DOM20-Profile, die physikalische Konfigurationsrevision 8 sowie alle Prognosen und Archive bleiben unverändert. Bestehende Hausfeld-Ausrichtung und der geografische Nordpfeil bleiben erhalten.

## Modulbelegung bündig und mit Nordpfeil in V12.9.6

Die orangefarbene Haus-links- und die blaue Haus-rechts-Gruppe überlappten in der SVG-Zeichnung um etwa 14,8 cm (X) und waren um etwa 4,5 cm in Y versetzt. Die Zeichnung richtet das blaue Feld anhand der Nachbarmodule 4.1.24 / 1.1.1 mit 25 mm Fuge in X und gleicher Reihenhöhe in Y aus. Alle 19 Module von Haus rechts sowie das zugehörige Bezugskreuz werden nur innerhalb der SVG-Darstellung um dieselbe kleine Differenz verschoben.

**Diese Anpassung ist ausschließlich grafisch.** Die physikalischen Modulmittelpunkte, DOM20-Nahprofile, Konfigurationsrevision 8, Ertragsberechnung und Archive sind unverändert.

Ein mit N beschrifteter Pfeil zeigt geografisch Nord an (15° rechts von der Bildoberkante bei 345° Ansichtsausrichtung). Der veraltete Text zur Garagenbelegung wurde aktualisiert.

## Garage Ost/West am Dachfirst korrigiert in V12.9.5

Der Fehler war eine Vertauschung der Modullängs- und -querachse sowie der Mittelpunktausrichtung. Die Module 2.1.15 West (255°) und 2.1.16 Ost (75°) liegen jetzt jeweils auf der richtigen Dachseite, beide mit 1,705 m langer Kante parallel zum First (345°). Die 1,028 m kurze Kante liegt quer zum First. Mittelpunktabstand ca. 0,991 m in der Draufsicht (bei ca. 20° Dachneigung und angenommener Fuge von 0,025 m); Positionen aus Luftbild und Modulmaßen abgeleitet, nicht vermessen.

Die Nahverschattung der zwei Modulmittelpunkte wurde aus den Original-DOM20-Kacheln neu berechnet; die anderen 86 Profile und alle übrigen Felder wurden nicht verändert. Die historischen Originalprognosen bleiben unverändert.

## Garagen-Azimut und SolarEdge-Modulnummern bestätigt in V12.9.4

Betreiberbestätigung vom 18.11.2026 anhand der vollständigen SolarEdge-Belegungsbilder (Süd ist im Bild unten): linkes Modul 2.1.15 ist nach Westen mit Azimut **255°**, rechtes Modul 2.1.16 nach Osten mit Azimut **75°** ausgerichtet. Beiden Modulen wurden die bestätigten Nummern zugeordnet. Die Dachneigung bleibt ca. 20°. Die korrigierten, getrennten Mittelpunktpositionen aus V12.9.3 sind abgeleitete Näherungen; keine weitere Verschiebung wird aus den Fotos vorgetäuscht.

Haus links und Carport: Die übermittelten vollständigen SolarEdge-Modulübersichten stimmen mit dem bestehenden Belegungsraster überein (Haus links: 24 Module; Carport: 18 Quer- plus 6 Hochkantmodule). Deren Nummern und Koordinaten wurden nicht verändert. Hütte 5 Module und Garage Hauptfeld 14 Module bleiben ebenfalls unverändert. Die DOM20-Nahhorizonte aller 88 Positionen bleiben gleich, da keine Mittelpunktkoordinaten geändert wurden; die Azimutänderung wirkt in der Einstrahlungsberechnung und die neue Geometrie erhält einen neuen Modellhash.

## Garagen-Ost-/Westmodule getrennt in V12.9.3

Zwei bislang exakt übereinander liegende Einzelmodule (Garage Ost / Garage West) sind jetzt auf gegenüberliegenden Dachseiten angeordnet: je 0,83 m östlich bzw. westlich der zuvor abgeleiteten gemeinsamen Paarmitte. Daraus ergeben sich 1,66 m Mittelpunktabstand. Das ist eine geometrisch aus Luftbild, SolarEdge-Belegung und Modulmaßen abgeleitete Näherung und keine Vermessung. Die SolarEdge-Positionsnummern 2.1.15 / 2.1.16 sind keinem der beiden Azimute willkürlich zugeordnet.

Azimut Ost 90° / West 270°, Neigung 20°, Leistung 330 Wp je Modul, Anzahl 88 und WR2 bleiben unverändert. Die beiden getrennten DOM20-Nahhorizonte wurden aus denselben originalen Geodaten am jeweils neuen Mittelpunkt neu berechnet. Die übrigen 86 Modulhorizonte sind unverändert. Historische Originalprognosen bleiben erhalten; die neue Geometrie und das neue Nahprofil erhalten eigene Versionshashes.

## Haus rechts korrigiert in V12.9.2

Nach Betreiberkorrektur und Vergleich mit dem bereitgestellten Luftbild lag das gesamte Feld Haus rechts zwei Modulreihen zu weit Richtung First. Alle 19 Module samt ihrem abgeleiteten Fensterbezug wurden gemeinsam Richtung Traufe verschoben: 2 × (0,992 m Modulbreite + 0,025 m angenommene Fuge) = 2,034 m auf dem 37° geneigten Dach, entsprechend rund 1,624 m in der Draufsicht. Die interne Belegung, Serien-/Modulnummern, 14 × 300 Wp + 5 × 415 Wp und WR1 bleiben erhalten. Die ursprüngliche GPS-Fensterangabe bleibt als Quelle in `layoutSurvey.registrationCorrection.sourceReferencePoint` gespeichert; die verschobenen Koordinaten sind abgeleitet und nicht neu vermessen.

Konfigurationsrevision 5 bindet die neuen Modulkoordinaten und die daraus erneut erzeugten DOM20-Horizonte. Die übrigen Modulpositionen und das Geländeprofil bleiben unverändert. Der Layoutgenerator wendet dieselbe Korrektur auch auf eine bereits erzeugte Konfiguration an; erneutes Ausführen verschiebt das Feld nicht nochmals. Ein Regressionstest prüft die vollständige Verschiebung, die erhaltene GPS-Rohangabe, den freien Fensterbereich und die Wiederholbarkeit gegen den vorher veröffentlichten Stand.

Das ist eine geometrische Korrektur nach Betreiberangabe, keine Ertragskalibrierung. Sie behebt nicht automatisch die separat untersuchte Nahverschattungsabweichung am Carport. Alte Originalprognosen bleiben unverändert.

## Richtungsfehler behoben in V12.9.1

Die DOM20-Rasterachsen beziehen sich auf UTM-Gitternord, der Sonnenstand auf geografisch Nord. Der bisherige Profilgenerator vermischte beide Richtungen. Die Meridiankonvergenz beträgt am Standort rund 2,131°. Python- und Browsergenerator korrigieren sie jetzt vor der Azimut-Zuordnung. Die 0,5°-Bins sind auf die von der Prognose interpolierten Winkelstützstellen zentriert. Alle 88 Nahhorizonte wurden aus denselben unveränderten DOM20-Dateien neu erzeugt; Modulpositionen, Geländeprofil, Wirkungsgrad und elektrische Grenzen wurden dabei nicht angepasst. Konfigurationsrevision 4 bindet das korrigierte Profil und trennt es durch die Modellkennung von alten Originalprognosen.

Die Korrektur ist keine Kalibrierung auf einen Tagesertrag: Für den 14.11.2026 erhöht sie die rückblickende Rechnung mit dem archivierten Morgenwetter von 55,326 auf 56,138 kWh, gegenüber 40,528 kWh SolarEdge. Sie behebt einen Richtungsfehler, nicht die gesamte Überschätzung. Die Morgenoriginalprognose von 58,123 kWh bleibt unverändert.

Weiter bestehende Modellgrenzen: Leistungen ganzer Module werden unabhängig summiert; SolarEdge-Stringspannung, Optimierer-Ausgangsspannungsgrenzen und Schatten innerhalb eines Moduls sind nicht modelliert. Streulicht wird isotrop verteilt; seine Richtungsverteilung und das Verhalten bei geringer Einstrahlung sind mit dem einen Messtag nicht eindeutig bestimmt. Diagnostische Gegenrechnungen mit 60/80-V-Optimierergrenzen, 750-V-Stringspannung und Hay-Davies-Streulicht sind keine bestätigten Geräteparameter und wurden nicht in die Prognose übernommen. Ein passender Einzelzeitpunkt oder eine passende Tagesenergie genügt nicht als Validierung. Es wurde kein empirischer Ertragsfaktor eingeführt.

## Belegung und Modulmittelpunkte ab V12.9.0

Die bestätigte Bestückung umfasst 88 Module und 31,305 kWp: Haus rechts/WR1 6,275 kWp, Garage und Hütte/WR2 7,180 kWp, Carport/WR3 9,900 kWp und Haus links/WR4 7,950 kWp. Gerätekennungen, Modultypen, Herstellermaße, Quellen und die fünf vom Betreiber genannten geografischen Bezugspunkte stehen in der zentralen Konfiguration. Die beiden Garagen-Einzelmodule sind getrennte Ost- und Westgruppen mit je 330 Wp und etwa 20° Neigung; die Südgruppe hat 4,620 kWp.

Die Modulpositionen sind aus Belegungsraster, Modulmaßen und GPS-Ankern **abgeleitete Näherungen, keine Vermessung**. Die Dachfenster dienen als Bezugspunkte; sie werden nicht pauschal als Feldmittelpunkte übernommen. Die Lage des Fensterankers innerhalb des Rasters und 25 mm Fugenabstand sind Arbeitsannahmen. Die Optimiererpositionen 2.1.15/16 sind noch keiner Ost-/Westrichtung sicher zugeordnet. Diese beiden Orientierungen verwenden daher vorläufig die gemeinsame, aus dem Schema geschätzte Paarmitte. Azimut 90°/270° ist aus der Himmelsrichtung abgeleitet, nicht separat vermessen. Die Website zeigt diese Grenzen in der Belegungsansicht und bei den Anlagenangaben.

Das DOM20-Nahprofil Version 2 enthält einen Horizont je Modulmittelpunkt und gewichtet die resultierenden Leistungen nach den jeweiligen Wp. Andere elektrische Annahmen, Wirkungsgrad, Systemverluste, Albedo und WR-Grenzen bleiben erhalten. Es gibt keinen neuen Ertrags- oder Diffusfaktor. Die vorhandene 0,5°-Winkelauflösung, 150 m Radius und 3 m Ausschlusskreis bleiben bestehen. DOM20-Quellen und ihre SHA-256-Hashes sind im Profil dokumentiert. Quellenlizenz: © Bayerische Vermessungsverwaltung, CC BY 4.0; Profile sind daraus abgeleitete Daten. Das Gelände-Horizontprofil bleibt unverändert.

Alte Version-1-Profile mit neun Stichproben werden weiterhin unterstützt. Alte Originalprognosen werden weder geändert noch nachberechnet. Das neue physikalische Modell erhält durch Geometrie- und Profilbindung eine eigene Modellkennung. `scripts/erstelle_modullayout.py` dokumentiert die geometrische Ableitung aus der vorbereiteten Bestückung; `scripts/baue_modulnahprofil.py` erzeugt und prüft das Nahprofil aus den originalen DOM20-TIFFs (numpy/Pillow und Node erforderlich). Felder ohne Einzelbelegung verwenden im vorhandenen Profilgenerator weiterhin neun Stichproben. Die aus Einzelmodulen abgeleiteten Rechteckmaße und Zentren sind im Editor schreibgeschützt; die Einzelpositionen dürfen nicht durch eine freie Rechteckänderung unbemerkt veralten.

## Zentrale Anlagenkonfiguration ab V12.8

`anlagenkonfiguration.json` ist die verbindliche Quelle für Standort, Höhe, Systemverluste, Albedo, Modulfelder einschließlich Geometrie, Wechselrichter, Zuordnungen und maximale AC-Wirkleistung in kW. Die erste zentrale Veröffentlichung übernimmt die vorhandenen fünf Modulfelder mit zusammen 31,305 kWp und vier Wechselrichtern unverändert. Schema-Version und Konfigurationsrevision sind unabhängig von der Website-Version.

Die Website lädt die Datei beim Start und bei der Wetteraktualisierung von GitHub Pages. Frühere lokale Anlageneinstellungen werden ignoriert. Mac, iPhone und die GitHub-Actions-Archivierung verwenden damit dieselben veröffentlichten Anlagenparameter. Unterschiedliche Wetterabrufzeiten können weiterhin unterschiedliche Prognosen ergeben.

Die Anzeige nennt Revision und den Anfang des SHA-256-Konfigurationshashs. Die Konfiguration bindet beide Profildateien mit ihren vollständigen SHA-256-Hashes und einem Geometriehash. Ein unvollständiger Veröffentlichungsstand wird nicht aktiviert. Die bestehende Prognoseberechnung, Wetter-Fallbacks und Verschattungsmodelle bleiben erhalten.

`localStorage` speichert Prognosehistorie, Wetter und eine geprüfte Kopie des gesamten zentralen Konfigurationspakets. Bei fehlender Verbindung darf diese Kopie weiter verwendet werden; die Website kennzeichnet sie ausdrücklich als **nicht aktuell bestätigt**. Ohne gültigen zentralen Stand oder gültige Kopie wird keine Prognose berechnet. Offline können keine zentralen Änderungen veröffentlicht werden. Die automatische Archivierung verlangt einen online bestätigten zentralen Stand.

## Korrektur V12.8.2: Start und bisherige Originalkurven

V12.8 führte einen neuen lokalen Archivschlüssel und eine neue Modellkennung ein. Ohne Übernahme des bisherigen Verlaufs entstanden dadurch neue Referenzkurven, die zunächst mit der aktuellen Prognose identisch waren. V12.8.2 liest zusätzlich die älteren lokalen Archive. V12.7-Originale werden mit unveränderten Werten und Zeitstempeln übernommen, wenn Profilbindung, Modulparameter und Wechselrichtermodell passen. Die bekannte Änderung der Standortpräzision bei der Einführung von V12.8 (unter 8 cm; ursprüngliche veröffentlichte Startkoordinaten) wird ausschließlich für diese historische Zuordnung berücksichtigt und gekennzeichnet. Sie verändert keine Anlagenparameter und berechnet keine historischen Werte neu.

Anderen Anlagen- und Modellständen werden getrennte Historien zugewiesen. Die alten Browserschlüssel bleiben unverändert erhalten. Bereits neu angelegte V12.8-Referenzen bleiben beim Wiederherstellen eines älteren Originals ebenfalls in der Historie erhalten. Browserdaten nicht löschen: Früher ausschließlich lokal gespeicherte Kurven können nur aus dem bisherigen Browser wiederhergestellt werden.

Fehlgeschlagene Downloads der zentralen Konfiguration oder Profile werden bis zu zweimal automatisch wiederholt. Unvollständige Pages-Veröffentlichungen werden weiterhin abgewiesen. Eine konkrete Fehlermeldung nennt die betroffene Datei; **Erneut laden** wiederholt den vollständigen Start, einschließlich einer fehlgeschlagenen `central-config.js`-Anfrage. Die Originalkurven dürfen auch bei einem Ladefehler nicht durch neu berechnete Werte ersetzt werden.

## Änderungen zentral speichern

1. Wie bisher Modulfelder/Wechselrichter, Standort oder Berechnungsparameter bearbeiten und speichern. Bis zur Veröffentlichung bleibt die bisherige Konfiguration aktiv.
2. Der Speicherdialog verlinkt zur Erstellung eines befristeten **Fine-grained personal access token** bei GitHub. Als Besitzer `SolarBergler`, unter **Only select repositories** nur `solarprognose_1` und unter **Repository permissions → Contents** **Read and write** wählen. Ein Ablaufdatum von sieben Tagen ist voreingestellt. Weitere Rechte, insbesondere für Workflows, sind für diesen Speicherweg nicht erforderlich.
3. Den erzeugten Schlüssel ausschließlich im Speicherdialog eingeben. Niemals in Chat, Projektdateien oder hochgeladene JSON-Dateien kopieren. Die Website sendet ihn nur an die GitHub-API für dieses Repository, hält ihn nur während dieses Speichervorgangs im Arbeitsspeicher und verwirft ihn anschließend. Die Website speichert ihn nicht in `localStorage`, Cookies oder URLs. Keine Speicherung im Passwortmanager auswählen. Für einen weiteren Speichervorgang ist die erneute Eingabe erforderlich; ein noch gültiger Schlüssel kann wieder verwendet werden.
4. **Autorisieren & zentral speichern** wählen. Der Dialog zeigt den GitHub-Speicherstatus und wartet anschließend mit Fortschrittsanzeige auf GitHub Pages. Sobald das vollständige Paket bereitsteht, wird es aktiviert und das Fenster automatisch geschlossen. Das kann einige Minuten dauern. Nach fünf Minuten lässt sich die Prüfung wiederholen, ohne einen weiteren Commit anzulegen.

Lesen und Prognoseberechnung benötigen keine Anmeldung. Die reine GitHub-Pages-Website hat keinen Server für eine dauerhafte OAuth-Anmeldung. Der beschränkte, kurzzeitig eingegebene Schlüssel ermöglicht sichere direkte Veröffentlichung ohne zusätzliche Infrastruktur. Für eine spätere Anmeldung ohne wiederholte Schlüsseleingabe wäre ein gesonderter OAuth-Dienst mit serverseitig verwahrtem Geheimnis erforderlich; dieser gehört nicht zur Anwendung.

Vor dem Schreiben prüft die Website die aktuell auf `main` gespeicherte Konfiguration gegen die beim Bearbeiten geladene Version. Hat ein anderes Gerät zwischenzeitlich gespeichert, bleibt der Entwurf erhalten und der Schreibversuch wird mit einer Konfliktmeldung abgewiesen. Den neuen Stand laden und die beabsichtigte Änderung erneut vornehmen. Auch ein anderer neuer Commit auf `main` während des Speicherns wird niemals mit `force` überschrieben.

Elektrische Änderungen (kWp, Zuordnung, AC-Grenzen, WR-Verwaltung) benötigen keine neuen Verschattungsprofile. Geometrische Änderungen führen in den vorhandenen DOM20-Dialog. Nach der Berechnung werden Konfiguration und beide benötigten Profile in **einem gemeinsamen Git-Commit** veröffentlicht. Ein manueller Datei-Upload ist dafür nicht mehr nötig. Auch während einer verzögerten oder teilweise ausgelieferten Pages-Veröffentlichung wird kein widersprüchlicher Stand aktiviert.

## Archivierung

Neue Prognosen enthalten unter `centralConfiguration` die Konfigurationsrevision, den vollständigen SHA-256-Hash, einen Hash des physikalischen Modells, beide Profilhashes und die tatsächlich verwendete vollständige Konfiguration. Der Browserzustand ab V12.8 liegt getrennt in `prognosen/browser_prognosezustand_v12_8.json`. Frühere Prognose- und Modellstände bleiben unverändert; manuelle Läufe erzeugen weiterhin ausdrücklich als Test benannte Snapshots. Fehlende historische Originalprognosen werden nicht nachberechnet.

Ab V12.8.1 liest auch der DWD-Abruf seinen Standort ausschließlich aus der zentralen Konfiguration. Die Archivierung verlangt zusätzlich exakt den Konfigurationshash des ausgecheckten Repository-Stands; eine noch veraltete Pages-Version wird nicht archiviert.

Die Prognosearchivierung läuft seit der Verlängerung am 9. November 2026 ohne festes Enddatum täglich um 06:00 und 18:00 Uhr in `Europe/Berlin` weiter. Der unabhängige DWD-MOSMIX-Abruf bleibt erhalten. Bereits gespeicherte Originalsnapshots werden nicht überschrieben; verspätete oder manuelle Läufe werden nicht als authentischer 06-/18-Uhr-Abruf ausgegeben. Die Rohwetterstände bleiben über die jeweiligen Archiv-Commits nachvollziehbar.

Die nächste Vergleichsphase wartet auf einen tatsächlich weitgehend wolkenlosen Tag mit niedrigem Sonnenstand. Dann werden die zuvor gesicherten Prognosen einschließlich Wetter- und Modellstand mit der gemessenen Leistungskurve verglichen: Produktionsbeginn und -ende, Verschattungsübergänge, Leistung während direkter Sonne und Tagesenergie. Die örtlichen Strahlungsdaten sowie Schnee, Reif oder Nebel sind gesondert zu prüfen; Wolkenlosigkeit allein beweist keine fehlerfreien Einstrahlungseingaben. Das Anlagen- und Verschattungsmodell wird während der Messphase nicht anhand der Erträge kalibriert.

## Tests

```sh
node tests/inverters.test.cjs
node tests/central-config.test.cjs
node tests/module-layout.test.cjs
python tests/test_dwd_configuration.py
python tests/test_startup.py
python tests/test_browser.py
python tests/test_profile_publication.py
```

Die Browsertests benötigen Python mit Playwright und verwenden vorhandenes Chromium (`PW_CHROMIUM_PATH`, ansonsten `/usr/bin/chromium`); sie installieren keinen Browser. GitHub-, Pages- und Wetterantworten werden isoliert simuliert. Geprüft werden unabhängige Browser, alte lokale Einstellungen, Offline-Betrieb, konkurrierende Veröffentlichungen, verzögertes Pages, gemeinsame Profilaktivierung, fehlende Schreibrechte, Geheimnisvermeidung, numerisch unveränderte Berechnung und die echte Archivierung in einem temporären Verzeichnis. Die Tests veröffentlichen keine Testanlagen auf GitHub.
