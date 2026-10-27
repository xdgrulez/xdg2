"""Sentence and discourse multigraph construction."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from pydbsp.zset import ZSet


class DiscourseGraph:
    """Sentence XDGs plus a second XDG whose nodes are the sentences."""

    def __init__(self) -> None:
        self.sentence_graphs: list[dict[str, Any]] = []
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: list[dict[str, str]] = []
        self.discourse_nodes: dict[str, dict[str, Any]] = {}
        self.discourse_sentence_nodes: list[dict[str, Any]] = []
        self.runtime_lexicon: dict[str, dict[str, Any]] = {}
        self.lexicon_edges: list[dict[str, str]] = []

    def add(self, sentence: dict[str, Any]) -> None:
        sid = sentence["id"]
        for node in sentence["nodes"]:
            self.nodes[node["id"]] = {**node, "sentence": sid}
            if node["kind"] in {"entity", "event"}:
                self.discourse_nodes[node["id"]] = {**node, "introduced_in": sid}

        dimensions: dict[str, list[dict[str, str]]] = {
            "ID": [], "PA": [], "linking": [], "realization": [], "event_structure": [], "LEX": []
        }
        for dimension, key in (("ID", "id_edges"), ("PA", "pa_edges")):
            for source, target, relation in sentence[key]:
                edge = {"source": source, "relation": relation, "target": target, "sentence": sid, "dimension": dimension}
                dimensions[dimension].append(edge)
                self.edges.append(edge)
        for source, relation, target in sentence["link_edges"]:
            edge = {"source": source, "relation": relation, "target": target, "sentence": sid, "dimension": "linking"}
            dimensions["linking"].append(edge)
            self.edges.append(edge)
        for dimension, key in (
            ("realization", "realization_edges"),
            ("event_structure", "event_structure_edges"),
        ):
            for source, relation, target in sentence.get(key, []):
                edge = {"source": source, "relation": relation, "target": target, "sentence": sid, "dimension": dimension}
                dimensions[dimension].append(edge)
                self.edges.append(edge)
        self.sentence_graphs.append(
            {
                "id": sid,
                "nodes": [self.nodes[node["id"]] for node in sentence["nodes"]],
                "dimensions": dimensions,
            }
        )
        self.discourse_sentence_nodes.append(
            {
                "id": sid,
                "kind": "sentence",
                "order": len(self.discourse_sentence_nodes) + 1,
                "proposition_event": sentence["event"],
            }
        )

    def add_coreference(self, mention: str, entity: str, sentence_id: str) -> None:
        edge = {
            "source": mention,
            "relation": "corefers_with",
            "target": entity,
            "sentence": sentence_id,
            "dimension": "linking",
        }
        self.edges.append(edge)
        sentence_graph = next(graph for graph in self.sentence_graphs if graph["id"] == sentence_id)
        sentence_graph["dimensions"]["linking"].append(edge)

    def add_lexical_choice(
        self, head: str, entry: dict[str, Any], sentence_id: str
    ) -> None:
        entry_id = entry["entry_id"]
        edge = {
            "source": head,
            "relation": "selected_entry",
            "target": entry_id,
            "sentence": sentence_id,
            "dimension": "LEX",
        }
        self.lexicon_edges.append(edge)
        self.runtime_lexicon[entry_id] = entry
        sentence_graph = next(graph for graph in self.sentence_graphs if graph["id"] == sentence_id)
        sentence_graph["dimensions"]["LEX"].append(edge)

    def jsonable(self, rows: dict[str, list[tuple[Any, ...]]]) -> dict[str, Any]:
        discourse_id_edges = [
            {"source": parent, "target": child, "relation": role}
            for parent, child, role in rows.get("discourse_id_edge", [])
        ]
        discourse_relation_edges = [
            {"source": source, "target": target, "relation": relation}
            for source, target, relation in rows.get("discourse_relation_edge", [])
        ]
        discourse_qud_edges = [
            {"source": source, "target": target, "relation": relation, "issue": issue}
            for source, target, relation, issue in rows.get("discourse_qud_edge", [])
        ]

        entity_event_edges: list[dict[str, str]] = []
        for sentence_graph in self.sentence_graphs:
            mention_targets = {
                edge["source"]: edge["target"]
                for edge in sentence_graph["dimensions"]["linking"]
                if edge["relation"] in {"refers_to", "corefers_with"}
            }
            entity_event_edges.extend(
                {
                    "source": mention,
                    "relation": "refers_to",
                    "target": entity,
                    "sentence": sentence_graph["id"],
                }
                for mention, entity in mention_targets.items()
            )
            entity_event_edges.extend(
                {
                    "source": edge["source"],
                    "relation": edge["relation"],
                    "target": mention_targets[edge["target"]],
                    "sentence": sentence_graph["id"],
                }
                for edge in sentence_graph["dimensions"]["PA"]
                if edge["target"] in mention_targets
            )
            entity_event_edges.extend(
                {
                    "source": edge["source"],
                    "relation": edge["relation"],
                    "target": edge["target"],
                    "sentence": sentence_graph["id"],
                }
                for edge in sentence_graph["dimensions"]["event_structure"]
            )
        return {
            "sentence_xdgs": list(self.sentence_graphs),
            "discourse_xdg": {
                "nodes": list(self.discourse_sentence_nodes),
                "dimensions": {
                    "ID": {
                        "roots": [root[0] for root in rows.get("discourse_root", [])],
                        "edges": discourse_id_edges,
                    },
                    "DR": {"edges": discourse_relation_edges},
                    "QUD": {"edges": discourse_qud_edges},
                },
            },
            "entity_event_multigraph": {
                "nodes": list(self.discourse_nodes.values()),
                "edges": entity_event_edges,
            },
            "runtime_lexicon": {
                "entries": list(self.runtime_lexicon.values()),
                "edges": list(self.lexicon_edges),
            },
        }


def facts_by_predicate(facts: ZSet) -> dict[str, list[tuple[Any, ...]]]:
    grouped: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
    for (predicate, args), weight in facts.inner.items():
        if weight > 0:
            grouped[predicate].append(args)
    return grouped
