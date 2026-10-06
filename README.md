## Aktueller Stand 0.8.0 – 06.10.2026

Eindeutige temporäre JSON-Dateien mit kontrollierter Bereinigung; validierte Herstellerdateien und kontrollierter Rückfall auf gebündelte IEEE-Daten; Veröffentlichungstest und Großnetztest korrigiert; acht Sprach-/Hilfepakete nachgepflegt; IEEE-Listen vom 05.10.2026.

Gerätedetails unterscheiden vorhandenen Nachbarcache, erstmals im Scan erfasste Nachbareinträge und den eigenen Rechner. Die Erfassungszeit beweist keine Antwort. Technische Namen behalten die Quelle NSS (konkreter Dienst unbekannt), mDNS/Avahi oder lokal; eigene Namen bleiben erhalten. Zwei MACs mit derselben IP im selben abgeschlossenen Scan auf derselben Schnittstelle werden als möglicher Konflikt gemeldet (auch Proxy-ARP möglich). Frühere DHCP-Zuordnungen zählen nicht als aktueller Konflikt. Neue Scan-Schnappschüsse vergleichen Adressen und Namen; fehlende Geräte zeigen die Anzahl vergleichbarer Scans ohne Fund. Andere Netze zählen nicht dazu. Netzwerkdetails lesen IPv4-/IPv6-Routen und Gateways sowie resolvectl-Daten mit eingeschränktem Rückfall auf resolv.conf. Es wird kein Gateway kontaktiert. Bestehende Datenbanken werden ohne Verlust ergänzt; ältere Fund- und Namensquellen bleiben unbekannt. Änderungen und Konflikte werden in der Ergebnisliste gekennzeichnet; Details und JSON enthalten die Beobachtungen.

Noch nicht als DEB erstellt oder veröffentlicht. Der bisherige Release bleibt unverändert. Prüfdetails: `TESTBERICHT.md`.

# showipmac

GTK-4-Anwendung zur Erfassung von Geräten im ausgewählten lokalen Netzwerk.
Erster Entwicklungsstand; zentrale Versionsquelle: `core.VERSION` (`./start.sh --version`).

```bash
./start.sh
```

Systemvoraussetzungen: Python 3, python3-gi, gir1.2-gtk-4.0, iproute2, python3-requests, python3-bs4.
Für aktive Erfassung: ping (iputils-ping). Für Namensauflösung: getent.
Keine automatische Installation, keine Root-Rechte, keine Telemetrie.

Die Anwendung liest die tatsächlichen Schnittstellen und Präfixe. Sie erfasst
Nachbarn, ordnet IPv4/IPv6 anhand beobachteter MAC-Adressen zu, bewahrt Adresshistorie
in SQLite und unterstützt eigene Namen, Statusfilter, Details, bewusstes
Zusammenführen und CSV-/JSON-Export. MAC-Zuordnungen sind Heuristiken, keine
Identitätsgarantie. IPv6 wird anhand lokaler Nachbareinträge erfasst.

Die aktive IPv4-Erfassung hat ein konfigurierbares Budget von 4096 Adressen;
größere Subnetze werden ausdrücklich als unvollständig behandelt. Die Netzauswahl zeigt berechnete IPv4-Subnetze, erkannte Anschlussarten und
Linux-Schnittstellennamen. IPv6 bleibt intern erhalten. Netzwerkdetails sind über das Menü erreichbar.
Keine entfernten Netze, keine Portsweeps, keine Geräteanmeldung.

Deutsch/Englisch sind extern in `lang/` und `help/` enthalten. Die lokale Hilfe
erläutert Datenablage, Einschränkungen und Herstellerdaten. Herstellererkennung
funktioniert offline mit den mitgelieferten IEEE-Daten; Aktualisierung nur per
Benutzeraktion. Die Anwendung funktioniert auch bei fehlenden Herstellerdaten.

Entwicklungsdaten liegen in `.config/`. Ein isolierter Teststart ist möglich mit
`./start.sh --data-dir work/testprofil`. Persönliche Daten und Logs gehören nicht
in eine Veröffentlichung.

Tests:

```bash
/usr/bin/python3 -m unittest discover -s tests -v
```

Lizenz: GNU General Public License Version 3, **GPL-3.0-only**. Siehe `LICENSE`.
Autor: Josef. Fremdressourcen: `THIRD_PARTY.md`.

Bedienung über eine klassische Menüleiste im Stil von Linux Mint/Cinnamon.
Keine Aktionsschaltflächen im Hauptfenster. Tabellenköpfe sortieren die Liste, IPv4 numerisch. Eigener Rechner, lokale Zeit, kompakte
IPv6-Anzeige und eine Scan-Zusammenfassung erleichtern die Übersicht.

Aktueller Freigabestand: 0.8.0 – gemeinsame Bausteine eingebaut und technisch geprüft. Josef hat am 04.10.2026 die DEB-Erstellung und Veröffentlichung dieses Stands beauftragt.

## Reparatur 0.2.7 – globale MAC-Wiedererkennung

Neu/Bekannt verwendet die MAC-Adresse in der gesamten SQLite-Datenbank,
unabhängig von Scan-Schnittstelle und IP. Netzansichten bleiben getrennt.
Frühere doppelte Einträge derselben MAC werden beim nächsten Fund unter
Erhaltung eigener Namen und vollständiger Beobachtungshistorie vereinigt.
Verschiedene MAC-Adressen werden nicht automatisch zusammengeführt.

## Korrektur 0.2.8 – eigene Namen und saubere Installation

Ein verfügbarer Hostname wird automatisch als eigener Name gespeichert, wenn
noch kein Name gesetzt ist (Anzeige „Unbekannt“) oder der Name „Unbekannt“/„Unknown“
lautet. Das gilt auch für bereits gespeicherte Geräte beim nächsten Programmstart.
Eigene Namen können weiterhin geändert werden und werden nicht überschrieben.

`erstelledeb.sh` stellt den Paketinhalt über eine Positivliste zusammen. Die
Entwicklungsdatenbank `.config/devices.sqlite3`, Einstellungen, Logs und Tests
werden niemals ausgeliefert. Die installierte Anwendung erstellt beim ersten
Start eine leere Datenbank unter `~/.config/showipmac/devices.sqlite3` (bzw.
`$XDG_CONFIG_HOME/showipmac`). Updates und erneute Installation erhalten diese
Daten einschließlich eigener Namen. Nach vollständiger Deinstallation entsteht
beim nächsten Start wieder eine neue Datenbank.

Paketerstellung nach Benutzerfreigabe: `./erstelledeb.sh`.
DEB-Erstellung: `./erstelledeb.sh`. Installation des heruntergeladenen Pakets: `sudo apt install ./showipmac_0.8.0_all.deb`.

## Korrektur 0.3.1 – CSV-Speicherdialog

Der GTK-Speicherdialog öffnet im Projektordner (installiert: Benutzerordner),
nicht im versteckten Konfigurationsordner. Der Export schützt die aktive
Gerätedatenbank vor Überschreiben.

## Anpassung 0.3.2 – Datenbankausgabe im Menü

Datei → Datenbankausgabe fasst CSV exportieren und JSON exportieren zusammen.
Das zusätzliche Datenbankfenster wurde entfernt. Exportiert werden die aktuell
sichtbaren Geräte mit Status Neu oder Bekannt; derzeit nicht gefundene Geräte
werden ausgelassen.

## Funktion 0.4.0 – Sprachpakete installieren

Einstellungen → Sprachen installieren bietet:
- eigene JSON-Sprachpakete samt Offline-Hilfe importieren,
- Sprachpakete aus der intern festgelegten GitHub-Quelle nachladen,
- verfügbare Sprachen aus catalog.json auswählen und samt Hilfe nachladen.

Das Paketformat entspricht dem Checkweb-Verfahren, mit `program_id: showipmac`:
`code`, `name`, `strings` (Übersetzungsschlüssel aus lang/en.json) und `help_html`.
Fehlende Texte fallen auf Englisch zurück. Fremde Programmkennungen, ungültige
Schlüssel/Platzhalter, unsichere Inhalte und zu große Downloads werden geprüft.
Vorhandene Pakete werden nicht überschrieben; DE/EN bleiben im Basispaket.
Installiert wird unter `<Datenverzeichnis>/languages/<code>/`; danach wird die
Sprache sofort ausgewählt und die lokale Hilfe verwendet. Eigene Sprachcodes
sind zulässig, ohne Begrenzung auf die acht vorgesehenen Standardsprachen.

Die veröffentlichte GitHub-Quelle zeigt auf den Ordner
`https://raw.githubusercontent.com/Lehner-007/showipmac/main/github/sprachpakete`.
Die Projektquellen sind intern festgelegt und im Dialog nicht bearbeitbar. Gespeicherte eigene Quellen werden durch die Projektvorgaben ersetzt.


## Veröffentlichungsvorbereitung 0.5.0

`./erstellegithub.sh` prüft den Quellumfang, Lizenz, zentrale Version und
auffällige Geheimnisse. Es erzeugt einen separaten Quellstand unter `dist/`;
keine privaten Konfigurationen, Datenbanken, Logs, Caches oder Testausgaben.
Der Standardlauf führt weder Commit, Tag noch Push aus.
`./erstellegithub.sh --publish` zeigt Ziel und Dateiliste und verlangt vor
Commit/Tag/Push eine ausdrückliche Bestätigung. Vorhandene Tags bleiben erhalten.

Veröffentlichungsziel: `github:Lehner-007/showipmac.git`, Branch `main`.
Die acht zusätzlichen Sprachen mit Offline-Hilfe liegen ausschließlich in
`github/sprachpakete/` und werden nicht ins DEB-Basispaket aufgenommen.
`github/version.json` identifiziert showipmac und die zentrale Programmversion.
Alle Übersetzungsschlüssel und Platzhalter sind technisch geprüft; eine
muttersprachliche Prüfung der Übersetzungen steht aus.

Das GitHub-Repository und alle acht Sprachdownloads sind veröffentlicht und geprüft.


## Links und Korrektur 0.5.1

- [Projekt und Python-Quellen](https://github.com/Lehner-007/showipmac)
- [Quellcode als ZIP](https://github.com/Lehner-007/showipmac/archive/refs/heads/main.zip)
- [Releases und verfügbare Pakete](https://github.com/Lehner-007/showipmac/releases)
- [Sprachpakete und Offline-Hilfen](https://github.com/Lehner-007/showipmac/tree/main/github/sprachpakete)
- [Sprachkatalog](https://raw.githubusercontent.com/Lehner-007/showipmac/main/github/sprachpakete/catalog.json)
- [Versionsdaten](https://raw.githubusercontent.com/Lehner-007/showipmac/main/github/version.json)

Hilfe → Über enthält die Projektseite. Eine leere gespeicherte Sprachquelle
verwendet jetzt die veröffentlichte Standardadresse; eigene Quellen bleiben
unverändert. Ein DEB-Downloadlink wird erst nach vorhandenem Release-Anhang angegeben.

## Gemeinsame Bausteine 0.7.0

Übernommen aus `/home/josef/Labor/Python/.bausteien/vorlage`, lokal unter `modules/`; keine Laufzeitabhängigkeit vom Vorlagenordner. Netzwerklogik und bestehende SQLite-Gerätedaten bleiben erhalten.

Datei enthält „Ergebnisse speichern/exportieren“, Trennlinie, „Einstellungen“, Trennlinie und „Beenden“. Einstellungen bündeln aktive Erfassung, IPv4-Adressbudget und Herstelleraktualisierung, Versionsprüfung bei jedem Start und optional zusätzlich während des Betriebs sowie Sprache, Import und Nachladen. Abbrechen verwirft die Dialogänderungen; ausdrücklich installierte Sprachpakete bleiben erhalten. Eine importierte Sprache ist sofort in der geöffneten Auswahl verfügbar und wird beim Speichern übernommen. Profile und Testdemo sind hier nicht aktiviert.

Fortschritt erscheint in einem separaten zentrierten Fenster mit sicherem Abbruch. Sprachdownloads sind nicht kooperativ abbrechbar; beim Schließen wartet das Programm auf deren Ende. Der DEB-Update-Download ist kooperativ abbrechbar und entfernt Teil-Dateien. Netzwerkabbruch verwirft unvollständige Erfassung. Keine Änderungen der Monitoreinstellungen. Normale Fenstergröße und unter X11 Position werden gespeichert, maximierter Zustand separat; fehlende Monitore werden berücksichtigt. Unter Wayland übernimmt der Compositor die Position.

Der Exportdialog bietet CSV (UTF-8/BOM/Semikolon), JSON und eigenständiges HTML mit eingebettetem Programmbild. „Alle“ umfasst sämtliche Geräte der ausgewählten Netzansicht einschließlich derzeit fehlender Geräte; „Angezeigte“ verwendet Suche, Filter und Sortierung. JSON bewahrt technische Daten und enthält Programmkennung und Version. CSV und HTML übersetzen Anzeigewerte und formatieren Datum/Uhrzeit lokal. Konfigurationsordner, Gerätedatenbank, Programmquellen und Ressourcen sind als Exportziele geschützt.

Hilfe → Protokoll zeigt das aktuelle Log lesend und bietet Neu laden und Export des angezeigten Stands. Sitzungen erhalten sichtbare Trennlinien; ältere Einträge werden beim Start nicht geleert. Rotation bei 500.000 Bytes mit zwei Sicherungen.

DE/EN sind vollständig gepflegt. Bei bestehenden zusätzlichen Sprachpaketen fallen neue fehlende Texte auf Englisch zurück. Die acht GitHub-Pakete wurden für die gemeinsamen Bausteinfunktionen und die zugehörige Hilfe nachübersetzt; eine muttersprachliche Abnahme steht aus. Quellcode und das DEB werden im Release v0.8.0 bereitgestellt. Es wird kein Benutzer-ZIP erstellt.

## Gemeinsame Darstellung in 0.7.0

Das Menü Ansicht entfällt. Spalten durch Klick auf den Kopf sortieren; erneut klicken für die umgekehrte Reihenfolge. Standard: IPv4 numerisch aufsteigend (.0, .1, .2, .9, .10), fehlende IPv4 am Ende. Hilfe → Info zeigt tatsächlich verwendete Abhängigkeiten einschließlich ip, ping und Avahi zur Namensauflösung. GitHub-Quellen sind intern festgelegt. Die Version wird bei jedem Start geprüft; Einstellungen zeigt den Status und bietet einen geprüften DEB-Download bei neuerer Version. SHA-256, Paketname, Version und Architektur müssen stimmen. Keine automatische Installation. Fortschritt reserviert vier Textzeilen; das Über-Bild ist auf 128 × 128 Pixel begrenzt. Export, Fensterzustand und Protokoll bleiben erhalten.

Mehrere Instanzen speichern vollständige Einstellungsstände atomar. Der zuletzt vollständig abgeschlossene Schreibvorgang gewinnt; Änderungen verschiedener Instanzen werden nicht zusammengeführt. Jede Instanz hat ihre eigene temporäre Datei. Eine fehlerhafte Herstellerdatei bleibt erhalten; der Start verwendet gebündelte Herstellerdaten und meldet den Fehler.

Die Paketbereinigung merkt standardmäßige und verwendete XDG-Speicherorte vor. Persönliche Starter und verlinkte Eltern bleiben geschützt; purge ermöglicht einen erneuten Versuch nach Entfernung der Programmdateien. Beliebige --data-dir-Verzeichnisse bleiben erhalten.
