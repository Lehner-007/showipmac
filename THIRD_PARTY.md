# Herkunft und Lizenzen

## IEEE-Herstellerdaten

Die vier unveränderten CSV-Dateien unter `vendor/` wurden am 05.10.2026
direkt von den öffentlichen IEEE-Quellen geladen und inhaltlich validiert.
Quellen, Last-Modified und Abrufzeit stehen in `vendor/metadata.json`.
Der frühere mitgelieferte Stand aus `ieee-data` vom 27.08.2022 wurde ersetzt.
Es handelt sich um MA-L (24 Bit), MA-M (28 Bit), MA-S (36 Bit) und IAB.
Die Quellen meldeten jeweils den Dateistand 05.10.2026.

Die mitgelieferte vollständige Rechteerklärung liegt in
`vendor/ieee-data-copyright.txt`. Für `oui.*`, `mam.*`, `oui36.*` und `iab.*`
führt sie Public Domain auf: IEEE erhebt keinen Copyright-Anspruch auf diese
öffentlichen Listen und beschränkt ihre Verteilung nicht. Diese Daten werden
als eigenständige Datensätze verwendet; sie werden nicht als eigener GPL-Code
umdeklariert. Ihre Verwendung und Weitergabe zusammen mit GPLv3-Code ist damit
nach der dokumentierten Rechteerklärung möglich.

Quellen für bewusste Aktualisierungen:

- https://standards-oui.ieee.org/oui/oui.csv
- https://standards-oui.ieee.org/oui28/mam.csv
- https://standards-oui.ieee.org/oui36/oui36.csv
- https://standards-oui.ieee.org/iab/iab.csv

Grundlage der Lizenzbewertung: lokale Debian-Paketmetadaten, obige beigefügte
Rechteerklärung und GNU-Erläuterung zu Public Domain / freien Lizenzen:
https://www.gnu.org/licenses/license-list.html#PublicDomain

Es wird ausschließlich die ganze Liste heruntergeladen, ohne Gerätekennungen
an einen Abfragedienst zu schicken. Aktualisierte Daten werden getrennt in
`vendors.json` gespeichert. Die HTTP-Last-Modified-Zeitpunkte aller vier Quellen
und der separate Downloadzeitpunkt werden gespeichert. Der Abruf verwendet eine
eindeutige showipmac-User-Agent-Kennung; Quelle und Datenlizenz bleiben gleich. Fehlerhafte Daten ersetzen keine vorhandene Datei.

## Laufzeit

Python (PSF-Lizenz), SQLite (Public Domain), GTK 4 (LGPL-2.1-or-later) und
PyGObject (LGPL-2.1-or-later) werden als vorhandene Systemkomponenten verwendet,
nicht im Projekt gebündelt. iproute2, iputils/ping und glibc/getent werden als
separate Systemprogramme aufgerufen; ihre Dateien werden nicht mitgeliefert.
Es wurde kein Fremdcode aus diesen Projekten übernommen.

## Markenzeichen

Das Wolf-und-D-Logo wurde aus Josefs bereitgestellter Datei `favicon.png`
übernommen und liegt in `assets/wasserzeichen.png`. Das während der Entwicklung vom Benutzer ergänzte Netzwerk-Programmsymbol liegt in `assets/showipmac.png`. Herkunft: Benutzerressourcen. Eine vom Benutzer erteilte öffentliche
Weitergabelizenz ist damit nicht unabhängig nachgewiesen; vor einer öffentlichen
Veröffentlichung muss Josef die Rechte am Logo bestätigen. Lokale Verwendung
entsprechend seiner Projektregeln.

## Eigener Code

GPL-3.0-only. Vollständiger Lizenztext: `LICENSE`.
