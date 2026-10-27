"""Compile a small general XDG grammar against the generic lexical seed."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydbsp.datalog_stratified import IncrementalDatalogStratified
from pydbsp.zset import ZSet

from xdg_lexicon import load_xdg_lexicon
from xdg_datalog import fact, rule
from xdg_decisions import JevClassifier


ROOT = Path(__file__).parent
GRAMMAR = json.loads((ROOT / "Grammars" / "core.json").read_text(encoding="utf-8"))


def compile_grammar_rules() -> ZSet:
    rules = {}
    for frame_name, frame in GRAMMAR["frames"].items():
        body = [
            ("runtime_candidate", ("?Q", "?E")),
            ("runtime_entry_frame", ("?E", frame_name)),
        ]
        body.extend(
            ("runtime_entry_role", ("?E", dimension, role))
            for dimension in ("ID", "PA")
            for role in frame[dimension]
        )
        body.extend(
            ("runtime_entry_link", ("?E", id_role, pa_role))
            for id_role, pa_role in frame["LINK"].items()
        )
        rules[rule(("runtime_admissible", ("?Q", "?E", frame_name)), *body)] = 1
    return ZSet(rules)


RULES = compile_grammar_rules()


class RuntimeLexiconBuilder:
    """Incrementally filter base entries by general grammar frames."""

    def __init__(self) -> None:
        self.entries = load_xdg_lexicon("de")
        self.frames = GRAMMAR["frames"]
        self.engine = IncrementalDatalogStratified()
        self.engine.push_rules(RULES)
        static_facts = []
        for entry_id, entry in self.entries.items():
            frame = entry["xdg"].get("frame")
            if frame:
                static_facts.append(fact("runtime_entry_frame", entry_id, frame))
            for dimension in ("ID", "PA"):
                for license_ in entry["xdg"].get(dimension, {}).get("licenses", []):
                    static_facts.append(
                        fact("runtime_entry_role", entry_id, dimension, license_["role"])
                    )
            for link in entry["xdg"].get("LINK", []):
                static_facts.append(
                    fact("runtime_entry_link", entry_id, link["id_role"], link["pa_role"])
                )
        self.engine.push_facts(ZSet({item: 1 for item in static_facts}))
        self.query_number = 0

    def admissible_entry_ids(self, lemma: str, frame_name: str) -> list[str]:
        query_id = f"runtime_q{self.query_number}"
        self.query_number += 1
        query_facts = [
            fact("runtime_candidate", query_id, entry_id)
            for entry_id, entry in self.entries.items()
            if entry["lemma"].casefold() == lemma.casefold()
        ]
        self.engine.push_facts(ZSet({item: 1 for item in query_facts}))
        result = self.engine.saturate()
        return sorted(
            args[1]
            for (predicate, args), weight in result.inner.items()
            if weight > 0
            and predicate == "runtime_admissible"
            and args[0] == query_id
            and args[2] == frame_name
        )

    def compile_entry(self, entry_id: str, frame_name: str) -> dict[str, Any]:
        entry = self.entries[entry_id]
        frame = self.frames[frame_name]
        predicates = set(entry["xdg"].get("PA", {}).get("predicates", []))
        realizes = set(entry["xdg"].get("realizes", predicates))
        if not realizes <= predicates:
            raise ValueError(
                f"Lexical entry {entry_id!r} realizes predicates absent from its PA fragment: "
                f"{sorted(realizes - predicates)}"
            )
        return {
            "entry_id": entry_id,
            "lemma": entry["lemma"],
            "sense": entry["sense"],
            "definition": entry["definition"],
            "semantic_type": entry["semantic_type"],
            "frame": frame_name,
            "frame_template": frame,
            "source": entry["source"],
            "graph_fragment": entry["xdg"],
        }

    @staticmethod
    def choose_entry(
        candidates: list[dict[str, Any]], *, context: dict[str, Any], offline: bool
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not candidates:
            raise ValueError("No lexical entry satisfies the grammar's hard frame constraints.")
        if len(candidates) == 1:
            entry = candidates[0]
            return entry, {"choice": entry["entry_id"], "source": "unique-hard-result"}

        criteria = {
            entry["entry_id"]: json.dumps(entry, ensure_ascii=False, sort_keys=True)
            for entry in candidates
        }
        if offline:
            selected = next(
                (entry for entry in candidates if entry["entry_id"] == "fahren.v.drive"),
                candidates[0],
            )
            return selected, {"choice": selected["entry_id"], "source": "offline-demo"}

        selected_id, decision = JevClassifier().choose(
            state={"context": context, "runtime_lexicon_candidates": candidates},
            criteria=criteria,
            question_name="runtime_lexical_entry",
            instructions=(
                "Choose the contextually appropriate compiled XDG lexical entry. "
                "All candidates satisfy the hard ID, PA and linking constraints. "
                "Choose one supplied entry; do not create or alter entries."
            ),
        )
        selected = next((entry for entry in candidates if entry["entry_id"] == selected_id), None)
        if selected is None:
            raise RuntimeError(f"Jev selected an inadmissible lexical entry: {selected_id!r}")
        return selected, decision

    @staticmethod
    def instantiate(sentence: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
        """Insert a compiled lexical fragment into a sentence graph template."""
        fragment = entry["graph_fragment"]
        nodes = [dict(node) for node in sentence["nodes"]]
        predicate_nodes = {
            node["predicate"]: node["id"]
            for node in nodes
            if node.get("predicate")
        }
        head = sentence["lexical_head"]
        for node in nodes:
            if node["id"] == head and "predicate" in node:
                node["predicate"] = fragment["PA"]["predicates"][0]
                predicate_nodes[node["predicate"]] = head

        try:
            realization_edges = [
                (head, "contributes", predicate_nodes[predicate])
                for predicate in fragment.get("realizes", fragment["PA"].get("predicates", []))
            ]
            event_structure_edges = [
                (predicate_nodes[source], relation, predicate_nodes[target])
                for source, relation, target in fragment.get("event_structure", [])
            ]
        except KeyError as exc:
            raise ValueError(
                f"Sentence {sentence['id']!r} lacks a predicate anchor for {exc.args[0]!r}."
            ) from exc
        return {
            **sentence,
            "nodes": nodes,
            "realization_edges": realization_edges,
            "event_structure_edges": event_structure_edges,
        }
