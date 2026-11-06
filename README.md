# Solarprognose

PV-Prognose mit Gelände- und DOM20-Nahverschattung. Website: https://solarbergler.github.io/solarprognose_1/

## Zentrale Anlagenkonfiguration ab V12.8

`anlagenkonfiguration.json` ist die verbindliche Quelle für Standort, Höhe, Systemverluste, Albedo, Modulfelder einschließlich Geometrie, Wechselrichter, Zuordnungen und maximale AC-Wirkleistung in kW. Die erste zentrale Veröffentlichung übernimmt die vorhandenen fünf Modulfelder mit zusammen 31,305 kWp und vier Wechselrichtern unverändert. Schema-Version und Konfigurationsrevision sind unabhängig von der Website-Version.

Die Website lädt die Datei beim Start und bei der Wetteraktualisierung von GitHub Pages. Frühere lokale Anlageneinstellungen werden ignoriert. Mac, iPhone und die GitHub-Actions-Archivierung verwenden damit dieselben veröffentlichten Anlagenparameter. Unterschiedliche Wetterabrufzeiten können weiterhin unterschiedliche Prognosen ergeben.

Die Anzeige nennt Revision und den Anfang des SHA-256-Konfigurationshashs. Die Konfiguration bindet beide Profildateien mit ihren vollständigen SHA-256-Hashes und einem Geometriehash. Ein unvollständiger Veröffentlichungsstand wird nicht aktiviert. Die bestehende Prognoseberechnung, Wetter-Fallbacks und Verschattungsmodelle bleiben erhalten.

`localStorage` speichert Prognosehistorie, Wetter und eine geprüfte Kopie des gesamten zentralen Konfigurationspakets. Bei fehlender Verbindung darf diese Kopie weiter verwendet werden; die Website kennzeichnet sie ausdrücklich als **nicht aktuell bestätigt**. Ohne gültigen zentralen Stand oder gültige Kopie wird keine Prognose berechnet. Offline können keine zentralen Änderungen veröffentlicht werden. Die automatische Archivierung verlangt einen online bestätigten zentralen Stand.

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

Der Messzeitraum endet einschließlich 8. November 2026. Der DWD-MOSMIX-Abruf läuft anschließend wie bisher weiter.

## Tests

```sh
node tests/inverters.test.cjs
node tests/central-config.test.cjs
python tests/test_browser.py
python tests/test_profile_publication.py
```

Die Browsertests benötigen Python mit Playwright und verwenden vorhandenes Chromium (`PW_CHROMIUM_PATH`, ansonsten `/usr/bin/chromium`); sie installieren keinen Browser. GitHub-, Pages- und Wetterantworten werden isoliert simuliert. Geprüft werden unabhängige Browser, alte lokale Einstellungen, Offline-Betrieb, konkurrierende Veröffentlichungen, verzögertes Pages, gemeinsame Profilaktivierung, fehlende Schreibrechte, Geheimnisvermeidung, numerisch unveränderte Berechnung und die echte Archivierung in einem temporären Verzeichnis. Die Tests veröffentlichen keine Testanlagen auf GitHub.
