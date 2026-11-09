# Solarprognose

PV-Prognose mit Gelände- und DOM20-Nahverschattung. Website: https://solarbergler.github.io/solarprognose_1/

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
python tests/test_dwd_configuration.py
python tests/test_startup.py
python tests/test_browser.py
python tests/test_profile_publication.py
```

Die Browsertests benötigen Python mit Playwright und verwenden vorhandenes Chromium (`PW_CHROMIUM_PATH`, ansonsten `/usr/bin/chromium`); sie installieren keinen Browser. GitHub-, Pages- und Wetterantworten werden isoliert simuliert. Geprüft werden unabhängige Browser, alte lokale Einstellungen, Offline-Betrieb, konkurrierende Veröffentlichungen, verzögertes Pages, gemeinsame Profilaktivierung, fehlende Schreibrechte, Geheimnisvermeidung, numerisch unveränderte Berechnung und die echte Archivierung in einem temporären Verzeichnis. Die Tests veröffentlichen keine Testanlagen auf GitHub.
