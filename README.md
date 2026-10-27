# XDG2 POC

Ein gemeinsamer, bidirektionaler Durchstich: Eine kurze XDG-Grammatik wird mit Einträgen aus dem Basislexikon zu einem Laufzeit-Lexikon kompiliert. PyDBSP/Datalog prüft harte Rahmen- und Diskursconstraints; Jev klassifiziert die danach zulässigen Lexikoneinträge und vollständigen Graphmodelle. Parsing und Generierung fragen dieselbe Relation zwischen Oberflächenform und XDG-Dokumentgraph ab.

## Ein Szenario

```text
Peter schenkte Paul ein Auto.
Paul lieh Peter das Auto.
Er fuhr es nach Hause.
```

Der erste und zweite Satz bilden den Diskurskontext. Beim dritten Satz lässt Datalog für „er“ Peter und Paul zu; Genus, Numerus und thematische Rolle schließen das Auto aus. Für „es“ bleibt das Auto als Fahrzeug-Thema übrig. Die Generierung ab demselben Zwei-Satz-Graphen liefert pronominale und explizite Fortsetzungen.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
export TYPESAFE_API_KEY="…"
.venv/bin/python xdg2_demo.py
```

Für einen Lauf ohne API-Aufruf:

```bash
.venv/bin/python xdg2_demo.py --offline
```

Jev sieht zunächst die beiden grammatikkompatiblen Einträge für `fahren` (`drive` und `travel`) und wählt einen für das Laufzeit-Lexikon. Danach klassifiziert es die vollständigen Parse- und Fortsetzungsmodelle anhand des Graphkontexts und der Präferenzmerkmale aus QUD, Grice-Relevanz und Centering. Jede Klassifikation wählt aus vorgelegten, bereits hart gefilterten Optionen. Einträge, Alternativen, Auswahl und Graphzustand sind protokollierbar.

## Graphmodell

- **Pro Satz** enthält das XDG getrennte `ID`-Dependency- und `PA`-Thematic-Rollen-Graphen. `LP` enthält Wortform, Reihenfolge, Abstände und die Ausrichtung von Oberflächenwörtern auf XDG-Knoten. In „schenkte“ richtet ein Wort einen ID-Knoten und zwei PA-Prädikate (`cause`, `transfer`) aus. „nach Hause“ zeigt die Gegenrichtung: zwei Wörter realisieren gemeinsam einen XDG-Knoten. Ein `event_structure`-Link bildet die logische Relation zwischen den PA-Prädikaten ab.
- **Über Sätze hinweg** bildet ein Diskurs-XDG die Sätze als Knoten ab. `ID` ordnet sie hier als einfache Anbindungshierarchie; `DR` markiert Narration und Fortsetzung; `QUD` hält die offene Frage nach dem Autobesitz fest.
- **Zwischen den Ebenen** verbinden Linking-Kanten Erwähnungen mit Entitäten. Ein Entity/Event-Graph hält Referenz und Ereignisrollen über Satzgrenzen hinweg verfügbar.

Die Oberflächenform wird aus den LP-Knoten des Graphen rekonstruiert. Die Relation ist mengenwertig:

```text
parse(text)     = { graph | (text, graph) ∈ R }
generate(graph) = { text | (text, graph) ∈ R }
```

Damit gilt in beiden Richtungen dieselbe Paarzugehörigkeit. Ein Text kann mehrere vollständige Graphen ergeben; eine Entscheidung wählt eine Alternative und lässt ihre Provenienz erhalten. Die graphgebundene Rückrichtung benötigt keine separate Parse- oder Generierungslogik.

## Was beim Lauf passiert

1. **Grammatik und Laufzeit-Lexikon:** `xdg_runtime.py` liest die allgemeinen `transfer`- und `motion`-Rahmen aus `Grammars/core.json` und baut daraus zusammen mit Basislexikon und XDG-Overlay die passenden Lexikoneinträge. PyDBSP verwirft Einträge, deren `ID`-, `PA`- oder Linking-Lizenzen nicht zum Rahmen passen. Für `fahren` bleiben beispielsweise `drive` und `travel` übrig.
2. **Lexikalische Klassifikation:** Jev wählt unter den bereits zugelassenen `fahren`-Einträgen. Die Auswahl wird als Laufzeit-Eintrag mit PA-Prädikaten und Wort-zu-Graph-Ausrichtung übernommen. Im Offline-Modus ersetzt eine feste Auswahl den API-Aufruf.
3. **Inkrementeller Diskurszustand:** PyDBSP erhält zuerst die Fakten der Sätze 1 und 2 und berechnet den Präfixzustand. Anschließend werden die Fakten von Satz 3 als weiteres Delta eingespeist. Datalog berechnet daraus die neuen Diskurskanten und Referenzkandidaten, ohne den Präfix neu aufzubauen.
4. **Harte Referenzconstraints:** Für „er“ bleiben Peter und Paul übrig: beide passen zu Genus und Numerus sowie zur Personenrolle. Auto und Home werden ausgeschlossen. Für „es“ bleibt allein Auto als neutrales Fahrzeug und thematische Rolle übrig. Diese Constraints verkleinern den Lösungsraum; sie geben keine Präferenzwertung ab.
5. **Vollständige Graphalternativen:** Aus jedem zulässigen „er“-Antezedenten entstehen ein pronominales und ein explizites Fortsetzungsmodell. Jedes Modell enthält die Satz-XDGs, den Diskurs-XDG und den Entity/Event-Graphen. Im API-Modus klassifiziert Jev diese vollständigen Modelle anhand des wachsenden Graphkontexts sowie QUD, Grice-Relevanz und Centering. Diese Merkmale sind Präferenzen und können keine durch Datalog ausgeschlossene Option zurückholen. `--offline` nutzt stattdessen eine lokale, deterministische Auswahl.
6. **Parsing und Generierung:** Beide Richtungen fragen dieselbe Relation aus Oberflächenform und Dokumentgraph ab. Beim Parsing schränkt der Text die Modelle ein; bei der Generierung schränken Präfixgraph oder vollständiger Graph die Oberflächen ein. Im API-Modus wählt Jev jeweils aus den verbleibenden Modellen. Der Demo-Lauf prüft anschließend beide Rundläufe: Graph → Text → gleicher Graph und Text → Graph → gleiche Oberfläche.

Der POC verwendet für Satzstrukturen und Fortsetzungsformen noch die endlichen Vorlagen aus `xdg_scenario.py`. Er demonstriert den inkrementellen Datalog-Schritt sowie die gemeinsame, reversible Relation, erzeugt aber noch keine beliebigen Satzgraphen aus der Grammatik.

Der einzige Einstieg ist [xdg2_demo.py](xdg2_demo.py). Die Implementierung ist nach Zuständigkeiten aufgeteilt:

- [xdg_scenario.py](xdg_scenario.py) enthält das eine Beispiel und seine Satzgraphen.
- [xdg_datalog.py](xdg_datalog.py) definiert harte Constraints und PyDBSP-Helfer.
- [xdg_graph.py](xdg_graph.py) baut Satz- und Diskursmultigraphen.
- [xdg_decisions.py](xdg_decisions.py) behandelt Jev-Auswahlen und Diskurspräferenzen.
- [xdg_runtime.py](xdg_runtime.py) erzeugt das Laufzeit-Lexikon aus der allgemeinen Grammatik.
- [xdg_document.py](xdg_document.py) verbindet die Module und stellt die gemeinsame Parse-/Generierungsrelation bereit.
- [xdg_document_demo.py](xdg_document_demo.py) zeigt den Ablauf über den Kommandozeilen-Einstieg.

## Stand und nächste Ausbaustufe

Das Beispiel verwendet weiterhin eine handautorisierte Szenario- und Fortsetzungsstruktur; die Verb-Lexikoneinträge und ihre ID/PA-Fragmente werden bereits zur Laufzeit aus Basislexikon und allgemeinen Rahmen kompiliert. Lemmazuordnung und Morphologie sind hier vorgegeben. Als nächstes sollten die Satz- und Diskursfragmente ebenfalls von der Grammatik instanziiert und inkrementell zusammengesetzt werden. Jev bleibt auf die Klassifikation der zulässigen Lexikoneinträge und vollständigen Modelle beschränkt.

Das Basislexikon und XDG-Overlay liegen in [Lexicon/](Lexicon/); die allgemeine Grammatik in [Grammars/core.json](Grammars/core.json). [xdg_runtime.py](xdg_runtime.py) kompiliert daraus das Laufzeit-Lexikon. Die Mehrwortanalyse orientiert sich an Debusmann, [“Multiword expressions as dependency subgraphs” (ACL 2004)](https://www.ps.uni-saarland.de/~rade/papers/acl04mwe.pdf). Die früheren Komponenten-Demos bleiben als Ausgangsmaterial erhalten; der integrierte Durchstich verwendet nur dieses Szenario.
