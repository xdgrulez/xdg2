"""Reversible XDG realization with many-to-many lexical mappings.

XDG units are distinct from surface words. A unit may expand to an ID
subgraph, and a word component may contribute a PA subgraph. Derivation trees
record graph composition sites, not phrase-structure constituents.
"""

from __future__ import annotations

import json
from itertools import permutations, product
from pathlib import Path
from typing import Any

try:
    from pydbsp import datalog as dlg
    from pydbsp.datalog_stratified import IncrementalDatalogStratified
    from pydbsp.zset import ZSet
except ImportError as exc:  # pragma: no cover - installation guidance
    raise SystemExit("PyDBSP fehlt. Installiere die Abhängigkeiten mit `python -m pip install -r requirements.txt`.") from exc

from xdg_lexicon import load_xdg_lexicon


LEXICON_DIR = Path(__file__).parent / "Lexicon"
ENGLISH_LEXICON = load_xdg_lexicon("en")
CONSTRUCTIONS = json.loads(
    (LEXICON_DIR / "constructions_en.json").read_text(encoding="utf-8")
)["constructions"]


def pa_signature(fragment: dict[str, Any]) -> str:
    """Canonicalize predicate-node IDs while preserving thematic argument identity."""
    predicate_nodes = {
        node["id"]: node["predicate"]
        for node in fragment["nodes"]
        if node.get("kind") == "predicate" or "predicate" in node
    }
    groups: dict[str, list[str]] = {}
    for node_id, predicate in predicate_nodes.items():
        groups.setdefault(predicate, []).append(node_id)

    ordered_groups = [(predicate, sorted(ids)) for predicate, ids in sorted(groups.items())]
    group_permutations = [list(permutations(ids)) for _, ids in ordered_groups]
    signatures = []
    for assignment in product(*group_permutations) if group_permutations else [()]:
        labels: dict[str, str] = {}
        next_index = 0
        for (predicate, _), node_ids in zip(ordered_groups, assignment):
            for node_id in node_ids:
                labels[node_id] = f"@p{next_index}"
                next_index += 1
        node_labels = {
            node["id"]: labels.get(node["id"], node["id"])
            for node in fragment["nodes"]
        }
        edges = sorted(
            (
                node_labels.get(edge["source"], edge["source"]),
                edge["role"],
                node_labels.get(edge["target"], edge["target"]),
            )
            for edge in fragment.get("thematic_edges", [])
        )
        nodes = sorted(
            json.dumps(
                {"id": node_labels[node["id"]], **{key: value for key, value in node.items() if key != "id"}},
                sort_keys=True,
                separators=(",", ":"),
            )
            for node in fragment["nodes"]
        )
        signatures.append(json.dumps({"nodes": nodes, "edges": edges}, sort_keys=True, separators=(",", ":")))
    return min(signatures, default=json.dumps({"nodes": [], "edges": []}, separators=(",", ":")))


def validate_constructions() -> None:
    for construction in CONSTRUCTIONS:
        components = construction["components"]
        component_ids = [component["component_id"] for component in components]
        if len(component_ids) != len(set(component_ids)):
            raise ValueError(f"Duplicate component ID in {construction['construction_id']!r}.")
        if set(construction["yield_order"]) != set(component_ids) or len(construction["yield_order"]) != len(component_ids):
            raise ValueError(f"Yield order must contain every component exactly once in {construction['construction_id']!r}.")
        if any(component["entry_id"] not in ENGLISH_LEXICON for component in components):
            raise ValueError(f"Unknown lexical entry in {construction['construction_id']!r}.")
        if any(
            edge[endpoint] not in component_ids
            for edge in construction["id_edges"]
            for endpoint in ("head", "dependent")
        ):
            raise ValueError(f"ID edge refers to a missing component in {construction['construction_id']!r}.")

        pa_nodes = {node["id"]: node for node in construction["pa_fragment"]["nodes"]}
        pa_node_ids = set(pa_nodes)
        if not pa_node_ids:
            raise ValueError(f"Construction has no PA contribution: {construction['construction_id']!r}.")
        anchored_pa_nodes = {
            node_id
            for component in components
            for node_id in component["pa_nodes"]
        }
        if not anchored_pa_nodes <= pa_node_ids:
            raise ValueError(f"Unknown PA node anchor in {construction['construction_id']!r}.")
        if anchored_pa_nodes != pa_node_ids:
            raise ValueError(f"Every PA predicate needs a lexical anchor in {construction['construction_id']!r}.")
        for component in components:
            entry_predicates = set(ENGLISH_LEXICON[component["entry_id"]]["xdg"]["PA"].get("predicates", []))
            anchored_predicates = {pa_nodes[node_id]["predicate"] for node_id in component["pa_nodes"]}
            if not anchored_predicates <= entry_predicates:
                raise ValueError(f"PA contribution does not match its lexical entry in {construction['construction_id']!r}.")
        for edge in construction["pa_fragment"].get("thematic_edges", []):
            if edge["source"] not in pa_nodes or pa_nodes[edge["source"]].get("kind") != "predicate":
                raise ValueError(f"Thematic edge has a non-predicate source in {construction['construction_id']!r}.")
            if edge["target"] not in pa_nodes and not edge["target"].startswith("$"):
                raise ValueError(f"Thematic edge has an unresolved target in {construction['construction_id']!r}.")


validate_constructions()


def fact(predicate: str, *args: Any) -> dlg.Fact:
    return predicate, tuple(args)


def rule(head: dlg.Atom, *body: dlg.Atom) -> dlg.Rule:
    return (head, *body)


RULES = ZSet(
    {
        rule(
            ("licensed_construction_id_edge", ("?C", "?H", "?D", "?R")),
            ("construction_id_edge", ("?C", "?H", "?D", "?R")),
            ("construction_component", ("?C", "?H", "?EH")),
            ("construction_component", ("?C", "?D", "?ED")),
            ("id_license", ("?EH", "?R", "?RequiredType")),
            ("base_lex_semantic_type", ("?ED", "?ActualType")),
            ("id_type_compatible", ("?ActualType", "?RequiredType")),
        ): 1,
        rule(
            ("invalid_construction_id_edge", ("?C",)),
            ("construction_id_edge", ("?C", "?H", "?D", "?R")),
            ("!licensed_construction_id_edge", ("?C", "?H", "?D", "?R")),
        ): 1,
        rule(
            ("admissible_construction", ("?Q", "?C")),
            ("construction_candidate", ("?C",)),
            ("construction_pa_signature", ("?C", "?PA")),
            ("construction_id_slot", ("?C", "?S")),
            ("realization_query", ("?Q", "?PA", "?S")),
            ("!invalid_construction_id_edge", ("?C",)),
        ): 1,
        rule(
            ("admissible_construction", ("?Q", "?C")),
            ("construction_candidate", ("?C",)),
            ("construction_id_slot", ("?C", "?S")),
            ("realization_slot_query", ("?Q", "?S")),
            ("!invalid_construction_id_edge", ("?C",)),
        ): 1,
    }
)


class ConstructionIndex:
    """Incrementally filter lexical bundles by PA graph and ID context."""

    def __init__(self) -> None:
        self.engine = IncrementalDatalogStratified()
        self.engine.push_rules(RULES)
        static_facts = []
        for construction in CONSTRUCTIONS:
            construction_id = construction["construction_id"]
            static_facts.extend(
                [
                    fact("construction_candidate", construction_id),
                    fact("construction_pa_signature", construction_id, pa_signature(construction["pa_fragment"])),
                    fact("construction_id_slot", construction_id, construction["required_id_slot"]),
                ]
            )
            static_facts.extend(
                fact("construction_component", construction_id, component["component_id"], component["entry_id"])
                for component in construction["components"]
            )
            static_facts.extend(
                fact("construction_id_edge", construction_id, edge["head"], edge["dependent"], edge["relation"])
                for edge in construction["id_edges"]
            )
        semantic_types = {entry["semantic_type"] for entry in ENGLISH_LEXICON.values()}
        static_facts.extend(
            fact("base_lex_semantic_type", entry_id, entry["semantic_type"])
            for entry_id, entry in ENGLISH_LEXICON.items()
        )
        static_facts.extend(
            fact("id_type_compatible", semantic_type, semantic_type)
            for semantic_type in semantic_types
        )
        static_facts.extend(
            fact("id_license", entry_id, license["role"], license["dependent_type"])
            for entry_id, entry in ENGLISH_LEXICON.items()
            for license in entry["xdg"]["ID"].get("licenses", [])
        )
        self.engine.push_facts(ZSet({row: 1 for row in static_facts}))
        self.query_number = 0

    def admissible(self, pa_fragment: dict[str, Any] | None, id_slot: str) -> set[str]:
        query_id = f"q{self.query_number}"
        self.query_number += 1
        if pa_fragment is None:
            query_fact = fact("realization_slot_query", query_id, id_slot)
        else:
            query_fact = fact("realization_query", query_id, pa_signature(pa_fragment), id_slot)
        self.engine.push_facts(ZSet({query_fact: 1}))
        result = self.engine.saturate()
        return {
            args[1]
            for (predicate, args), weight in result.inner.items()
            if weight > 0 and predicate == "admissible_construction" and args[0] == query_id
        }


CONSTRUCTION_INDEX = ConstructionIndex()


def construction_candidates(
    pa_fragment: dict[str, Any] | None, id_slot: str
) -> list[dict[str, Any]]:
    admissible = CONSTRUCTION_INDEX.admissible(pa_fragment, id_slot)
    return [
        construction
        for construction in CONSTRUCTIONS
        if construction["construction_id"] in admissible
    ]


def rank_construction(candidates: list[dict[str, Any]], *, state: dict[str, Any]) -> dict[str, Any]:
    if len(candidates) == 1:
        return candidates[0]
    try:
        from typesafe_sdk import Choice, TypeSafeClient
    except ImportError as exc:  # pragma: no cover - installation guidance
        raise RuntimeError("typesafe-sdk fehlt; installiere requirements.txt.") from exc

    criteria = {
        candidate["construction_id"]: json.dumps(candidate, ensure_ascii=False, sort_keys=True)
        for candidate in candidates
    }
    with TypeSafeClient(model="jev-latest") as client:
        response = client.system_one(
            state={**state, "admissible_graph_configurations": candidates},
            questions={
                "realization": Choice(
                    instructions=(
                        "Rank the complete XDG realization alternatives. Choose only a supplied construction ID; "
                        "do not add or alter graph constraints."
                    ),
                    criteria=criteria,
                )
            },
        )
    selected_id = response.answers["realization"].choice
    selected = next((candidate for candidate in candidates if candidate["construction_id"] == selected_id), None)
    if selected is None:
        raise RuntimeError(f"Jev returned a construction outside the admissible set: {selected_id!r}")
    return selected


def materialize_construction(
    construction: dict[str, Any], *, xdg_unit_id: str, admissible_ids: list[str]
) -> dict[str, Any]:
    pa_fragment = construction["pa_fragment"]
    pa_id_map = {node["id"]: f"{xdg_unit_id}:{node['id']}" for node in pa_fragment["nodes"]}
    pa_nodes = [
        {**node, "id": pa_id_map[node["id"]]}
        for node in pa_fragment["nodes"]
    ]
    pa_edges = [
        {
            "source": pa_id_map[edge["source"]],
            "role": edge["role"],
            "target": pa_id_map.get(edge["target"], edge["target"]),
        }
        for edge in pa_fragment.get("thematic_edges", [])
    ]
    components_by_id = {component["component_id"]: component for component in construction["components"]}
    id_nodes = {
        component_id: {
            "id": f"{xdg_unit_id}:{component_id}",
            "form": components_by_id[component_id]["surface"],
            "lexical_entry": components_by_id[component_id]["entry_id"],
            "realizes_xdg_unit": xdg_unit_id,
            "realizes_pa_nodes": [pa_id_map[node_id] for node_id in components_by_id[component_id]["pa_nodes"]],
        }
        for component_id in construction["yield_order"]
    }
    id_edges = [
        {
            "head": f"{xdg_unit_id}:{edge['head']}",
            "dependent": f"{xdg_unit_id}:{edge['dependent']}",
            "relation": edge["relation"],
        }
        for edge in construction["id_edges"]
    ]
    return {
        "xdg_unit_id": xdg_unit_id,
        "construction_id": construction["construction_id"],
        "admissible_constructions": admissible_ids,
        "PA": {"nodes": pa_nodes, "thematic_edges": pa_edges},
        "ID_realization_subgraph": {
            "nodes": [id_nodes[component_id] for component_id in construction["yield_order"]],
            "edges": id_edges,
        },
        "yield": [components_by_id[component_id]["surface"] for component_id in construction["yield_order"]],
        "derivation_operation": construction["derivation_operation"],
        "required_id_slot": construction["required_id_slot"],
        "_construction_data": construction,
    }


def solve_realizations(
    *,
    id_slot: str,
    pa_evidence: dict[str, Any] | None = None,
    surface_evidence: list[str] | None = None,
    construction_id: str | None = None,
    xdg_unit_id: str = "u_candidate",
) -> list[dict[str, Any]]:
    """Query one shared PA↔ID realization relation in either direction."""
    candidates = construction_candidates(pa_evidence, id_slot)
    models = []
    for construction in candidates:
        if construction_id is not None and construction["construction_id"] != construction_id:
            continue
        model = materialize_construction(
            construction,
            xdg_unit_id=xdg_unit_id,
            admissible_ids=[candidate["construction_id"] for candidate in candidates],
        )
        if pa_evidence is not None and pa_signature(model["PA"]) != pa_signature(pa_evidence):
            continue
        if surface_evidence is not None and model["yield"] != surface_evidence:
            continue
        models.append(model)
    return models


def select_model(models: list[dict[str, Any]], *, state: dict[str, Any]) -> dict[str, Any]:
    if not models:
        raise ValueError("No complete XDG model satisfies the supplied evidence.")
    selected_construction = rank_construction(
        [model["_construction_data"] for model in models],
        state=state,
    )
    return next(model for model in models if model["construction_id"] == selected_construction["construction_id"])


def generate_unit(
    *,
    xdg_unit_id: str,
    pa_fragment: dict[str, Any],
    id_slot: str,
    construction_id: str | None = None,
) -> dict[str, Any]:
    models = solve_realizations(
        id_slot=id_slot,
        pa_evidence=pa_fragment,
        construction_id=construction_id,
        xdg_unit_id=xdg_unit_id,
    )
    return select_model(
        models,
        state={"mode": "generation", "focus_xdg_unit": xdg_unit_id, "PA": pa_fragment, "ID_slot": id_slot},
    )


def parse_unit(
    *,
    tokens: list[str],
    id_slot: str,
    construction_id: str | None = None,
    xdg_unit_id: str = "u_parsed",
) -> dict[str, Any]:
    models = solve_realizations(
        id_slot=id_slot,
        surface_evidence=tokens,
        construction_id=construction_id,
        xdg_unit_id=xdg_unit_id,
    )
    return select_model(
        models,
        state={"mode": "parsing", "surface_tokens": tokens, "ID_slot": id_slot},
    )


def show_roundtrip(title: str, pa_fragment: dict[str, Any], id_slot: str, xdg_unit_id: str) -> dict[str, Any]:
    generated = generate_unit(xdg_unit_id=xdg_unit_id, pa_fragment=pa_fragment, id_slot=id_slot)
    parsed = parse_unit(
        tokens=generated["yield"],
        id_slot=id_slot,
        construction_id=generated["construction_id"],
        xdg_unit_id=xdg_unit_id,
    )
    print(f"\n[{title}]")
    print("PA input:")
    print(json.dumps(pa_fragment, ensure_ascii=False, indent=2))
    print(f"Admissible constructions: {generated['admissible_constructions']}")
    print(f"Surface yield: {' '.join(generated['yield'])}")
    print("Generated ID subgraph:")
    print(json.dumps(generated["ID_realization_subgraph"], ensure_ascii=False, indent=2))
    print("Parsed PA fragment:")
    print(json.dumps(parsed["PA"], ensure_ascii=False, indent=2))
    same_model = (
        generated["construction_id"] == parsed["construction_id"]
        and generated["yield"] == parsed["yield"]
        and pa_signature(generated["PA"]) == pa_signature(parsed["PA"])
    )
    print(f"Same realization model in both directions: {same_model}")
    return generated


def main() -> None:
    give_pa = {
        "nodes": [
            {"id": "cause", "kind": "predicate", "predicate": "cause"},
            {"id": "transfer", "kind": "predicate", "predicate": "transfer"},
        ],
        "thematic_edges": [
            {"source": "cause", "role": "agent", "target": "$arg0"},
            {"source": "cause", "role": "theme", "target": "transfer"},
            {"source": "transfer", "role": "theme", "target": "$arg1"},
            {"source": "transfer", "role": "recipient", "target": "$arg2"},
        ],
    }

    to_give = show_roundtrip("to give: two predicates, two ID words", give_pa, "to_infinitive", "e_give")
    derivation_tree = {
        "elementary_xdg": {"host": "want"},
        "children": [
            {
                "operation": to_give["derivation_operation"],
                "dimension": "ID",
                "slot": "xcomp",
                "child": {
                    "construction": to_give["construction_id"],
                    "xdg_unit": to_give["xdg_unit_id"],
                    "lexical_components": to_give["ID_realization_subgraph"]["nodes"],
                },
            }
        ],
    }
    print("TAG-like derivation tree (XDG fragments and substitution sites, no phrase nodes):")
    print(json.dumps(derivation_tree, ensure_ascii=False, indent=2))

    show_roundtrip("bare give: same PA graph, different ID context", give_pa, "bare_infinitive", "e_give_bare")


if __name__ == "__main__":
    main()
