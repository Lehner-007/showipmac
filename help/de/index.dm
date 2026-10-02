SEITE
ID: hilfe

META
SPRACHE: de
STATUS: pruefung
VERSION: 1.12
ERSTELLT: 29.09.2026
GEAENDERT: 02.10.2026

TITEL
showipmac – Hilfe

INHALT
## Netzwerk auswählen
Wähle das automatisch berechnete IPv4-Subnetz in CIDR-Schreibweise. Die Auswahl zeigt Subnetz, zuverlässig erkannte Anschlussart (LAN, WLAN oder virtuell) und Linux-Schnittstellenname. Mehrere Anschlüsse desselben Netzes bleiben getrennt auswählbar. Mehrere erkannte LAN-Schnittstellen werden nach Namen sortiert als LAN 1, LAN 2 usw. bezeichnet; das sind laufende Programmbezeichnungen, keine Gehäuse-Portnummern. Nicht zuverlässig erkennbare Anschlussarten werden nicht ergänzt. Schnittstellen, eigene Adressen und IPv6 bleiben intern erhalten und sind unter Netzwerk → Netzwerkdetails einsehbar; dort werden virtuelle Schnittstellen gekennzeichnet. Hat eine Schnittstelle mehrere IPv4-Subnetze, erhält jedes einen eigenen Eintrag. Schnittstellen ohne IPv4-Subnetz erscheinen nicht in der Scan-Auswahl. Sie bleiben in der Schnittstellenauswahl unter Netzwerk → Netzwerkdetails einsehbar. Virtuelle Netze mit IPv4-Subnetz bleiben auswählbar. In einer VM ist nur das dort erreichbare Netzwerk sichtbar.

## Erfassung und Grenzen
Netzwerk → Scan starten (F5) untersucht das ausgewählte IPv4-Subnetz und die zugehörigen direkt konfigurierten IPv6-Netze der Schnittstelle. Abbrechen liegt ebenfalls im Netzwerk-Menü (Esc). Aktive Erfassung lässt sich im Menü Einstellungen umschalten. Aktive Erfassung prüft IPv4-Adressen per Ping und bereits beobachtete IPv6-Nachbarn. Vor jedem Ping wird die Route geprüft: Ziele über ein Gateway werden ausgelassen. Ohne aktive Erfassung werden nur lokale Nachbartabellen gelesen. Große IPv4-Netze oberhalb des konfigurierten Budgets werden nicht vollständig durchprobiert; eine Meldung weist darauf hin. IPv6 wird nicht vollständig enumeriert. Firewall, Schlafzustand und fehlender Netzwerkverkehr können Geräte verbergen. Veraltete Nachbareinträge können weiterhin auftauchen. Ein Scan ist kein Nachweis der Erreichbarkeit oder Vollständigkeit.

## Abbrechen und Speichern
Die Oberfläche bleibt bedienbar. Abbrechen beendet laufende Prüfungen und verwirft den unvollständigen Scan. Auch beim Schließen wird laufende Arbeit zuerst abgebrochen. Nur abgeschlossene Scans aktualisieren die SQLite-Gerätedaten. Eine Netzänderung während der Erfassung bricht die Übernahme ab. Herstellerdownloads können bis zum nächsten Netzwerk-Timeout zum Abbruch benötigen.

## Geräte und Wiedererkennung
IPv4 und IPv6 mit derselben MAC werden innerhalb des gewählten Netzes zusammengeführt. Das ist eine plausible Zuordnung, kein sicherer Identitätsnachweis. MAC-Adressen können wechseln, wiederverwendet oder gefälscht werden. Eine neue MAC wird nicht allein wegen einer gleichen IP oder eines Hostnamens mit einem bekannten Gerät verbunden. Lokal verwaltete MAC-Adressen werden ausdrücklich als unsicher gekennzeichnet. Zwei bekannte Einträge kannst du mit Strg + Klick auswählen und nach Bestätigung zusammenführen. Bei Auswahl eines einzelnen Geräts bietet die Zusammenführung auch gespeicherte Geräte aus anderen Netzwerkschnittstellen an. Der erste eigene Name bleibt erhalten; ist er leer, wird der zweite verwendet. Weitere eigene Namen bleiben in den Details gespeichert. Erst „Zusammenführen“ bestätigt die Änderung; „Abbrechen“ verändert keine Daten. Die vollständigen Beobachtungen bleiben in Details sichtbar.

## Eigene Namen für Geräte und Anschlüsse
Wähle einen Geräteeintrag aus und öffne Geräte → Details / Name. Trage unter „Eigener Name“ eine eindeutige Bezeichnung ein und bestätige mit „Speichern“. Ein Name ist optional, erleichtert aber die Wiedererkennung. LAN und WLAN desselben Geräts haben normalerweise unterschiedliche MAC-Adressen und erscheinen deshalb als getrennte Einträge. Benenne sie beispielsweise „Mein PC – LAN“ und „Mein PC – WLAN“. Der Name gehört zum gespeicherten Geräteeintrag; der Hostname des Geräts wird dadurch nicht geändert. Eigene Namen bleiben nach dem Schließen des Programms und bei weiteren Scans erhalten. Auch der Filter „Derzeit nicht gefunden“ zeigt diese Namen: Er enthält gespeicherte Geräte, die beim letzten abgeschlossenen Scan im ausgewählten Netz nicht erkannt wurden. Der Filter löscht oder verändert keine Daten. Wird ein gespeicherter Eintrag erneut erkannt, erscheint er wieder als „Bekannt“. Bei einer geänderten MAC-Adresse kann ein neuer Eintrag entstehen; der eigene Name wird dann nicht automatisch übertragen.

## Status und Historie
Neu: beim letzten Scan erstmals in diesem Netz beobachtet. Bekannt: in einem früheren Scan bereits beobachtet. Derzeit nicht gefunden: im jüngsten Scan nicht enthalten; das beweist nicht, dass das Gerät ausgeschaltet ist. Details zeigen erstmals und zuletzt gesehen, alle bisherigen Adressen, Schnittstellen, Nachbarstatus und lokale Netzzuordnung. Zeitstempel werden in UTC mit Zeitzonenangabe gespeichert. In allen Oberflächensprachen erscheinen Zeitwerte als lokale Zeit im Format DD.MM.YYYY HH:MM:SS. Eigene Namen lassen sich unter Geräte → Details / Name ändern. „Dieser Rechner“ kennzeichnet den lokalen Rechner ohne zusätzlichen Datensatz. Mehrere IPv6-Adressen erscheinen als Anzahl; Details enthalten alle Adressen. Lange Herstellernamen werden in der Tabelle gekürzt und in den Details vollständig angezeigt. Die Zusammenfassung nach dem Scan zählt gefundene, neue und bekannte Geräte.

## Herstellerdaten
Die getrennte lokale Datenbank verwendet die IEEE-Verzeichnisse MA-L, MA-M, MA-S und IAB. Der längste passende Präfix gewinnt. Bei lokal verwalteten MAC-Adressen bleibt der Hersteller unbekannt. OUI bezeichnet die registrierte Organisation, nicht Gerätemodell, Gerätetyp oder Verkaufsmarke. Die mitgelieferten Daten stammen aus ieee-data vom 27.08.2022; dieses Datum ist der Stand der Paketdateien, keine behauptete aktuelle IEEE-Ausgabe. Herstellerdaten aktualisieren lädt die vollständigen vier Listen direkt per HTTPS von IEEE. Es werden keine einzelnen MAC-Adressen oder Gerätelisten übertragen. Die bisherige Datenbank bleibt bei fehlerhaften Downloads erhalten; eine verständliche Meldung nennt den Fehler. Nach vollständiger Prüfung aller vier Listen zeigt das Programm den vom IEEE-Server gelieferten Datenstand. Fehlt ein Quellzeitpunkt, wird ausdrücklich nur der Downloadzeitpunkt angezeigt. Die Aktualisierung wird ausschließlich im Menü Einstellungen → Herstellerdaten aktualisieren ausgelöst.

## Suchen und Export
Alle Programmfunktionen liegen in der klassischen Menüleiste. Hilfe → Über zeigt den nativen Informationsdialog mit showipmac-Logo, Version, Lizenz und Mitwirkenden. Das Wasserzeichen liegt mittig im Ergebnisbereich. Spaltenüberschriften sortieren per Klick; alternativ die direkt unter Ansicht → Sortieren nach aufgeführten Spalten verwenden. Erneute Auswahl derselben Spalte kehrt die Richtung um. IPv4-Adressen werden numerisch sortiert. Die Suche berücksichtigt Namen, Adressen und gespeicherte Beobachtungen. Der Statusfilter schränkt die Liste weiter ein. Datei → CSV exportieren exportiert die aktuell angezeigten Geräte in UTF-8 mit BOM; Zellen mit möglichen Tabellenformeln werden mit einem Apostroph abgesichert. JSON enthält zusätzlich die vollständige Beobachtungshistorie und stabile technische Schlüssel. Die Dateien enthalten persönliche Netzwerkdaten; wähle ihren Speicherort bewusst.

## Einstellungen, Sprachen und Dateien
In der Entwicklung liegen Einstellungen unter .config/settings.json, Gerätedaten in .config/devices.sqlite3, aktualisierte Herstellerdaten in .config/vendors.json und begrenzte Logs in .config/logs. --data-dir erlaubt einen getrennten Datenordner. Deutsch und Englisch samt Hilfe funktionieren offline. Einstellungen → Sprache wechselt die Sprache sofort. Hostnamen stammen aus der konfigurierten System-Namensauflösung (NSS). Falls verfügbar, dient avahi-resolve-address als zusätzlicher mDNS-Rückfall; Namen werden nicht geraten. Zusätzliche lokale JSON-Sprachen in <Datenordner>/lang mit einem language_name-Feld werden beim Start erkannt; Hilfe liegt unter <Datenordner>/help/<Sprachcode>/index.html. Englisch ist die Rückfallsprache. Beschädigte Einstellungen bleiben als Diagnosekopie erhalten. Es existiert noch keine GitHub-Quelle für Sprach- oder Programmupdates.

## Lizenz
Eigener Programmcode: GNU General Public License Version 3 (GPL-3.0-only), vollständiger Text in LICENSE. Autor: Josef. Die IEEE-Daten und ihre Herkunft/Lizenz sind in THIRD_PARTY.md und vendor/ieee-data-copyright.txt dokumentiert. Keine Telemetrie, keine Anmeldung an Geräten, keine Passwortversuche.

Wenn „Eigener Name“ unbekannt oder leer ist, wird ein vorhandener Hostname automatisch übernommen, auch für bereits gespeicherte Geräte beim Programmstart. Danach kannst du den Namen weiterhin ändern. Ein gesetzter eigener Name wird bei weiteren Scans nicht überschrieben. Das DEB enthält keine Entwicklungs-Gerätedatenbank; bei einer frischen Installation wird die leere Datenbank beim ersten Start im Benutzerprofil unter ~/.config/showipmac angelegt (oder unter $XDG_CONFIG_HOME/showipmac). Updates und erneute Installation behalten Geräte und eigene Namen.

Datei → Datenbankausgabe enthält CSV exportieren und JSON exportieren. Beide Ausgaben enthalten die aktuell sichtbaren, im letzten Scan gefundenen Geräte (Neu oder Bekannt). Derzeit nicht gefundene Geräte werden ausgelassen. Es gibt kein zusätzliches Datenbankfenster.

Der Speicherdialog öffnet im Projektordner, bei installierter Anwendung im Benutzerordner. Wähle einen Zielordner und bestätige mit Speichern. Abbrechen erstellt keine Datei.

## Sprachen installieren
Einstellungen → Sprachen installieren bietet eine GitHub-Basisadresse, Sprachpaket importieren und Sprache und Hilfe nachladen. Eigene UTF-8-JSON-Pakete benötigen program_id „showipmac“, code, name, strings und help_html. Übersetzungen dürfen Schlüssel weglassen (englischer Rückfall), vorhandene Schlüssel und Platzhalter müssen aber stimmen. DE/EN können nicht durch Pakete ersetzt werden. Importierte Pakete werden im Benutzerprofil unter languages/<code>/ gespeichert und sofort ausgewählt. Die passende Hilfe funktioniert offline. Beim Nachladen wird catalog.json gelesen; bereits installierte Sprachen werden ausgeblendet. Heruntergeladen wird <code>.json erst nach bewusster Auswahl. Die GitHub-Adresse kann gespeichert werden; ohne Adresse funktioniert der lokale Import. Es werden nur HTTPS-GitHub-Adressen akzeptiert. Beschädigte, zu große, fremde oder bereits installierte Pakete werden nicht übernommen. Acht zusätzliche Sprach-/Hilfepakete sind getrennt für GitHub vorbereitet. Die geplante GitHub-Quelle wird erst nach Veröffentlichung verfügbar; sie bleibt in den Einstellungen änderbar.

Ein Gerät kann mehrere MAC-Adressen haben: beispielsweise zwei LAN und eine WLAN. Zuerst LAN 1 und LAN 2 zusammenführen, danach den gemeinsamen Eintrag mit WLAN. Alle MAC-Adressen und Beobachtungen bleiben gespeichert; eine neue MAC muss manuell zugeordnet werden.

ENDE
