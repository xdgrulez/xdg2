"""Command-line walkthrough of the shared parse/generate relation."""

from __future__ import annotations

import argparse
from typing import Any

from xdg_document import (
    build_relation,
    document_surface,
    generate_continuations,
    generate_from_document_graph,
    graph_summary,
    parse_document,
    parse_prefix,
    select_document_model,
)


def run_demo(*, offline: bool) -> None:
    scenario = build_relation(offline=offline)
    prefix_text = next(model["document_text"] for model in scenario.models if model["is_prefix"])
    parsed_prefix_graph = parse_prefix(prefix_text, models=scenario.models)
    continuations = generate_continuations(
        prefix_graph=parsed_prefix_graph, models=scenario.models
    )

    print("XDG2: Parse und Generierung über dieselbe Dokumentrelation")
    print("\nLaufzeit-Lexikon:")
    for sentence_id, entry in scenario.runtime_lexicon.items():
        print(f"  {sentence_id}: {entry['entry_id']} / frame={entry['frame']}")
    print(f"  Jev-Auswahl: {scenario.lexical_decision['choice']}")
    print("\nGeparster Präfix:")
    print(graph_summary(parsed_prefix_graph))
    print(f"\nDatalog lässt 'er' auflösen zu: {sorted({m['antecedent'] for m in continuations})}")
    print("Mögliche Fortsetzungen:")
    for model in continuations:
        print(f"  {model['variant']} / {model['antecedent']}: {model['document_text']}")

    pronoun_text = next(model["document_text"] for model in continuations if model["variant"] == "pronoun")
    parsed_candidates = parse_document(
        pronoun_text,
        prefix_graph=parsed_prefix_graph,
        models=scenario.models,
    )
    parsed, parse_decision = select_document_model(
        parsed_candidates,
        prefix_graph=parsed_prefix_graph,
        prefix_graph_object=scenario.context,
        offline=offline,
    )
    generated, generation_decision = select_document_model(
        continuations,
        prefix_graph=parsed_prefix_graph,
        prefix_graph_object=scenario.context,
        offline=offline,
    )
    parse_roundtrip = parse_document(
        generated["document_text"],
        models=scenario.models,
        document_graph_evidence=generated["document_multigraph"],
    )
    generation_roundtrip = generate_from_document_graph(
        parsed["document_multigraph"], models=scenario.models
    )
    print(f"\nParsing {pronoun_text!r} liefert {len(parsed_candidates)} Graphmodelle.")
    print(f"Jev-Parseauswahl: {parse_decision['choice']}")
    print(f"Jev-Fortsetzung: {generated['continuation_text']} ({generation_decision['choice']})")
    print(f"Graph → Text → derselbe Graph: {len(parse_roundtrip) == 1}")
    print(
        "Text → Graph → dieselbe Oberfläche: "
        f"{any(model['document_text'] == parsed['document_text'] for model in generation_roundtrip)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Choose with Centering evidence without a TypeSafe call.")
    run_demo(offline=parser.parse_args().offline)
