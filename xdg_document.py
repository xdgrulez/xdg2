"""Bidirectional surface/document-graph relation for the XDG2 scenario."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from pydbsp.datalog_stratified import IncrementalDatalogStratified

from xdg_datalog import RULES, as_zset, constraint_facts
from xdg_decisions import JevClassifier, centering_evidence, offline_choice
from xdg_graph import DiscourseGraph, facts_by_predicate
from xdg_scenario import SENTENCES
from xdg_runtime import RuntimeLexiconBuilder


PREFIX_SENTENCES = SENTENCES[:2]
CONTINUATION = SENTENCES[2]
TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)
LP_ALIGNMENT: dict[str, list[list[str]]] = {
    "s1": [
        ["m_peter_1"],
        ["give1", "cause1", "transfer1"],
        ["m_paul_1"],
        ["m_ein_1"],
        ["m_auto_1"],
        [],
    ],
    "s2": [["m_paul_2"], ["lend2"], ["m_peter_2"], ["m_auto_2"], ["m_auto_2"], []],
    "s3": [["m_er"], ["drive3"], ["m_es"], ["m_home_3"], ["m_home_3"], []],
}


@dataclass
class Scenario:
    models: list[dict[str, Any]]
    context: DiscourseGraph
    lexical_decision: dict[str, Any]
    runtime_lexicon: dict[str, dict[str, Any]]


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def add_lp_dimension(sentence_graph: dict[str, Any], sentence: dict[str, Any]) -> None:
    matches = list(TOKEN_RE.finditer(sentence["text"]))
    alignment = sentence.get("lp_alignment", LP_ALIGNMENT[sentence["id"]])
    if len(matches) != len(alignment):
        raise ValueError(f"LP alignment has {len(alignment)} entries for {len(matches)} tokens in {sentence['id']}.")
    nodes = []
    previous_end = 0
    for position, (match, xdg_nodes) in enumerate(zip(matches, alignment)):
        nodes.append(
            {
                "id": f"{sentence['id']}:t{position}",
                "form": match.group(0),
                "separator_before": sentence["text"][previous_end:match.start()],
                "realizes_xdg_nodes": xdg_nodes,
                "position": position,
            }
        )
        previous_end = match.end()
    sentence_graph["dimensions"]["LP"] = {
        "nodes": nodes,
        "trailing_separator": sentence["text"][previous_end:],
        "edges": [
            {"source": nodes[index]["id"], "relation": "precedes", "target": nodes[index + 1]["id"]}
            for index in range(len(nodes) - 1)
        ],
    }


def sentence_surface(sentence_graph: dict[str, Any]) -> str:
    lp = sentence_graph["dimensions"]["LP"]
    return "".join(node["separator_before"] + node["form"] for node in lp["nodes"]) + lp["trailing_separator"]


def document_surface(document_graph: dict[str, Any]) -> str:
    return " ".join(sentence_surface(graph) for graph in document_graph["sentence_xdgs"])

def incremental_discourse_state() -> tuple[dict[str, list[tuple[Any, ...]]], dict[str, list[tuple[Any, ...]]]]:
    engine = IncrementalDatalogStratified()
    engine.push_rules(RULES)
    initial = constraint_facts(tuple(sentence["id"] for sentence in SENTENCES))
    for sentence in PREFIX_SENTENCES:
        initial.extend(sentence["facts"])
    engine.push_facts(as_zset(initial))
    prefix_rows = facts_by_predicate(engine.saturate())

    engine.push_facts(as_zset(CONTINUATION["facts"]))
    complete_rows = facts_by_predicate(engine.saturate())
    for stage, rows in (("prefix", prefix_rows), ("complete document", complete_rows)):
        errors = {
            predicate: rows[predicate]
            for predicate in (
                "discourse_missing_parent",
                "discourse_unreachable",
                "discourse_cycle",
                "discourse_multiple_parents",
            )
            if rows.get(predicate)
        }
        if errors:
            raise RuntimeError(f"PyDBSP rejected the {stage} discourse XDG: {errors}")
    return prefix_rows, complete_rows


def make_graph(
    sentences: list[dict[str, Any]],
    rows: dict[str, list[tuple[Any, ...]]],
    *,
    coreferences: list[tuple[str, str, str]] | None = None,
    lexical_entries: dict[str, dict[str, Any]] | None = None,
) -> tuple[DiscourseGraph, dict[str, Any]]:
    graph = DiscourseGraph()
    for sentence in sentences:
        entry = (lexical_entries or {}).get(sentence["id"])
        realized_sentence = (
            RuntimeLexiconBuilder.instantiate(sentence, entry) if entry else sentence
        )
        graph.add(realized_sentence)
        add_lp_dimension(graph.sentence_graphs[-1], realized_sentence)
        if entry:
            graph.add_lexical_choice(sentence["lexical_head"], entry, sentence["id"])
    for mention, entity, sentence_id in coreferences or []:
        graph.add_coreference(mention, entity, sentence_id)
    return graph, graph.jsonable(rows)


def explicit_continuation(antecedent: str) -> dict[str, Any]:
    mention_id = f"m_{antecedent.lower()}_3"
    return {
        **CONTINUATION,
        "text": f"{antecedent} fuhr das Auto nach Hause.",
        "nodes": [
            {"id": "Home", "kind": "entity", "gender": "neut", "number": "sg", "type": "location"},
            {"id": "drive3", "kind": "event", "predicate": "drive"},
            {"id": mention_id, "kind": "mention", "form": antecedent},
            {"id": "m_auto_3", "kind": "mention", "form": "das Auto"},
            {"id": "m_home_3", "kind": "mention", "form": "nach Hause"},
        ],
        "id_edges": [
            ("drive3", mention_id, "subj"),
            ("drive3", "m_auto_3", "obj"),
            ("drive3", "m_home_3", "obl"),
        ],
        "pa_edges": [
            ("drive3", mention_id, "agent"),
            ("drive3", "m_auto_3", "theme"),
            ("drive3", "m_home_3", "goal"),
        ],
        "link_edges": [
            (mention_id, "refers_to", antecedent),
            ("m_auto_3", "refers_to", "Auto"),
            ("m_home_3", "refers_to", "Home"),
        ],
        "lp_alignment": [
            [mention_id], ["drive3"], ["m_auto_3"], ["m_auto_3"],
            ["m_home_3"], ["m_home_3"], [],
        ],
    }


def build_relation(
    *, offline: bool
) -> Scenario:
    prefix_rows, complete_rows = incremental_discourse_state()
    lexicon_builder = RuntimeLexiconBuilder()
    runtime_entries: dict[str, dict[str, Any]] = {}
    for sentence in PREFIX_SENTENCES:
        candidates = lexicon_builder.admissible_entry_ids(
            sentence["lexical_lemma"], sentence["lexical_frame"]
        )
        if len(candidates) != 1:
            raise RuntimeError(
                f"Expected one hard-admissible lexical entry for {sentence['lexical_lemma']!r}, got {candidates}."
            )
        runtime_entries[sentence["id"]] = lexicon_builder.compile_entry(
            candidates[0], sentence["lexical_frame"]
        )
    prefix_graph_object, prefix_graph = make_graph(
        PREFIX_SENTENCES, prefix_rows, lexical_entries=runtime_entries
    )
    motion_candidates = [
        lexicon_builder.compile_entry(entry_id, CONTINUATION["lexical_frame"])
        for entry_id in lexicon_builder.admissible_entry_ids(
            CONTINUATION["lexical_lemma"], CONTINUATION["lexical_frame"]
        )
    ]
    selected_motion_entry, lexical_decision = lexicon_builder.choose_entry(
        motion_candidates, context=prefix_graph, offline=offline
    )
    runtime_entries[CONTINUATION["id"]] = selected_motion_entry
    valid_antecedents = sorted(
        entity
        for mention, entity in complete_rows.get("valid_ref", [])
        if mention == "m_er"
    )
    if not valid_antecedents:
        raise RuntimeError("PyDBSP found no admissible antecedent for the discourse continuation.")
    valid_es = {
        entity
        for mention, entity in complete_rows.get("valid_ref", [])
        if mention == "m_es"
    }
    if valid_es != {"Auto"}:
        raise RuntimeError(f"Expected hard constraints to resolve 'es' to Auto, got {sorted(valid_es)}.")

    prefix_signature = canonical(prefix_graph)
    document_models = [
        {
            "model_id": "doc:s1-s2:prefix",
            "antecedent": None,
            "variant": "prefix",
            "is_prefix": True,
            "base_graph_signature": prefix_signature,
            "continuation_text": "",
            "document_text": document_surface(prefix_graph),
            "document_multigraph": prefix_graph,
        }
    ]
    for antecedent in valid_antecedents:
        variants = [
            (
                "pronoun",
                CONTINUATION,
                [("m_er", antecedent, "s3"), ("m_es", "Auto", "s3")],
            ),
            (
                "explicit",
                explicit_continuation(antecedent),
                None,
            ),
        ]
        for variant, sentence, coreferences in variants:
            graph_object, document_graph = make_graph(
                [*PREFIX_SENTENCES, sentence],
                complete_rows,
                coreferences=coreferences,
                lexical_entries=runtime_entries,
            )
            document_text = document_surface(document_graph)
            document_models.append(
                {
                    "model_id": f"doc:s3:{variant}:ref->{antecedent}",
                    "antecedent": antecedent,
                    "variant": variant,
                    "is_prefix": False,
                    "base_graph_signature": prefix_signature,
                    "continuation_text": sentence_surface(document_graph["sentence_xdgs"][-1]),
                    "document_text": document_text,
                    "document_multigraph": document_graph,
                }
            )
    return Scenario(document_models, prefix_graph_object, lexical_decision, runtime_entries)


def solve_document_relation(
    *,
    prefix_graph: dict[str, Any] | None = None,
    models: list[dict[str, Any]],
    text_evidence: str | None = None,
    document_graph_evidence: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Query the same full-document surface↔graph relation from either side."""
    prefix_signature = canonical(prefix_graph) if prefix_graph is not None else None
    graph_signature = canonical(document_graph_evidence) if document_graph_evidence is not None else None
    return [
        model
        for model in models
        if (prefix_signature is None or model["base_graph_signature"] == prefix_signature)
        and (text_evidence is None or model["document_text"] == text_evidence)
        and (graph_signature is None or canonical(model["document_multigraph"]) == graph_signature)
    ]


def select_document_model(
    candidates: list[dict[str, Any]],
    *,
    prefix_graph: dict[str, Any],
    prefix_graph_object: DiscourseGraph,
    offline: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not candidates:
        raise ValueError("No full document model satisfies the supplied text/graph evidence.")
    antecedents = sorted({model["antecedent"] for model in candidates})
    centering = centering_evidence(prefix_graph_object, antecedents)
    entity_center_matches = centering.get("candidate_matches_previous_backward_center", {})
    centering["candidate_matches_previous_backward_center"] = {
        model["model_id"]: entity_center_matches.get(model["antecedent"], False)
        for model in candidates
    }
    preferences = {
        "Grice_1975": {"maxim": "Relation", "active_issue": "car_possession"},
        "Centering_Theory": centering,
    }
    criteria = {
        model["model_id"]: json.dumps(
            {
                "model_id": model["model_id"],
                "variant": model["variant"],
                "continuation_text": model["continuation_text"],
                "complete_document_multigraph": model["document_multigraph"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        for model in candidates
    }
    state = {
        "document_multigraph": prefix_graph,
        "admissible_document_extensions": [
            {
                "antecedent": model["antecedent"],
                "variant": model["variant"],
                "model_id": model["model_id"],
                "continuation_text": model["continuation_text"],
                "complete_document_multigraph": model["document_multigraph"],
            }
            for model in candidates
        ],
        "pragmatic_preferences": preferences,
    }
    if offline:
        selected_key, decision = offline_choice(criteria, preferences)
    else:
        selected_key, decision = JevClassifier().choose(
            state=state,
            criteria=criteria,
            question_name="document_extension",
            instructions=(
                "Rank complete discourse-graph extensions for continuing the document. "
                "Use QUD, Gricean relevance and Centering only as preferences. "
                "Choose only one supplied model; the PyDBSP-admissible candidate set is fixed."
            ),
        )
    selected = next(model for model in candidates if model["model_id"] == selected_key)
    return selected, decision


def parse_document(
    text: str,
    *,
    prefix_graph: dict[str, Any] | None = None,
    models: list[dict[str, Any]],
    document_graph_evidence: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return solve_document_relation(
        prefix_graph=prefix_graph,
        models=models,
        text_evidence=text,
        document_graph_evidence=document_graph_evidence,
    )


def generate_continuations(
    *,
    prefix_graph: dict[str, Any],
    models: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Query all complete relation members that extend this prefix graph."""
    return [
        model
        for model in solve_document_relation(prefix_graph=prefix_graph, models=models)
        if not model["is_prefix"]
    ]


def generate_from_document_graph(
    document_graph: dict[str, Any], *, models: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return all surface realizations licensed by this exact complete graph."""
    return solve_document_relation(models=models, document_graph_evidence=document_graph)


def parse_prefix(
    text: str, *, models: list[dict[str, Any]]
) -> dict[str, Any]:
    parses = parse_document(text, models=models)
    prefix_parses = [model for model in parses if model["is_prefix"]]
    if not prefix_parses:
        raise ValueError("This POC's prefix parser recognizes the two declared sentence graph templates.")
    return prefix_parses[0]["document_multigraph"]



def graph_summary(document_graph: dict[str, Any]) -> str:
    local = "; ".join(
        f"{sentence['id']}[" + ", ".join(
            f"{dimension}={len(data['nodes']) if dimension == 'LP' else len(data)}"
            for dimension, data in sentence["dimensions"].items()
        ) + "]"
        for sentence in document_graph["sentence_xdgs"]
    )
    discourse = ", ".join(
        f"{dimension}={len(data['edges'])}"
        for dimension, data in document_graph["discourse_xdg"]["dimensions"].items()
    )
    return f"Sätze: {local}\nDiskurs: {discourse}"


