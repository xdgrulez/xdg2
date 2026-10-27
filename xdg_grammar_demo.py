"""A tiny two-dimension XDG-style grammar evaluated with PyDBSP Datalog."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from pydbsp import datalog as dlg
from pydbsp.datalog_stratified import IncrementalDatalogStratified
from pydbsp.zset import ZSet
from xdg_lexicon import load_xdg_lexicon


def fact(predicate: str, *args: Any) -> dlg.Fact:
    return predicate, tuple(args)


def rule(head: dlg.Atom, *body: dlg.Atom) -> dlg.Rule:
    return (head, *body)


RULES = ZSet(
    {
        # ID dimension: an edge is licensed by the head's lexical entry and
        # the dependent's semantic/syntactic type.
        rule(
            ("id_edge", ("?H", "?D", "?IR")),
            ("id_candidate", ("?H", "?D", "?IR")),
            ("lemma", ("?H", "?L")),
            ("semantic_type", ("?D", "?T")),
            ("id_licenses", ("?L", "?IR", "?RequiredType")),
            ("id_type_compatible", ("?T", "?RequiredType")),
        ): 1,
        # PA dimension: thematic roles are independently licensed by the
        # predicate's lexical entry and the argument's semantic type.
        rule(
            ("pa_edge", ("?P", "?A", "?PR")),
            ("pa_candidate", ("?P", "?A", "?PR")),
            ("lemma", ("?P", "?L")),
            ("semantic_type", ("?A", "?T")),
            ("pa_licenses", ("?L", "?PR", "?RequiredType")),
            ("pa_type_compatible", ("?T", "?RequiredType")),
        ): 1,
        # XDG linking: the same dependent must realize the paired ID and PA
        # roles licensed by the predicate's linking entry.
        rule(
            ("linked_argument", ("?P", "?A", "?IR", "?PR")),
            ("id_edge", ("?P", "?A", "?IR")),
            ("pa_edge", ("?P", "?A", "?PR")),
            ("lemma", ("?P", "?L")),
            ("role_link", ("?L", "?IR", "?PR")),
        ): 1,
        rule(
            ("unlinked_pa_candidate", ("?P", "?A", "?PR")),
            ("pa_edge", ("?P", "?A", "?PR")),
            ("!linked_pa_edge", ("?P", "?A", "?PR")),
        ): 1,
        rule(
            ("linked_pa_edge", ("?P", "?A", "?PR")),
            ("linked_argument", ("?P", "?A", "?IR", "?PR")),
        ): 1,
        rule(
            ("rejected_id_candidate", ("?H", "?D", "?IR")),
            ("id_candidate", ("?H", "?D", "?IR")),
            ("!id_edge", ("?H", "?D", "?IR")),
        ): 1,
        rule(
            ("rejected_pa_candidate", ("?P", "?A", "?PR")),
            ("pa_candidate", ("?P", "?A", "?PR")),
            ("!pa_edge", ("?P", "?A", "?PR")),
        ): 1,
        # ID tree well-formedness: every non-root token has a head, all tokens
        # are reachable from the root, and no cycle is present.
        rule(("has_id_head", ("?D",)), ("id_edge", ("?H", "?D", "?IR"))): 1,
        rule(
            ("missing_id_head", ("?W",)),
            ("token", ("?W",)),
            ("!id_root", ("?W",)),
            ("!has_id_head", ("?W",)),
        ): 1,
        rule(
            ("id_reach", ("?R", "?D")),
            ("id_root", ("?R",)),
            ("id_edge", ("?R", "?D", "?IR")),
        ): 1,
        rule(
            ("id_reach", ("?R", "?D2")),
            ("id_reach", ("?R", "?D1")),
            ("id_edge", ("?D1", "?D2", "?IR")),
        ): 1,
        rule(
            ("rooted_id_node", ("?D",)),
            ("id_root", ("?R",)),
            ("id_reach", ("?R", "?D")),
        ): 1,
        rule(
            ("unreachable_id_node", ("?W",)),
            ("token", ("?W",)),
            ("!id_root", ("?W",)),
            ("!rooted_id_node", ("?W",)),
        ): 1,
        rule(("id_path", ("?H", "?D")), ("id_edge", ("?H", "?D", "?IR"))): 1,
        rule(
            ("id_path", ("?H", "?D2")),
            ("id_path", ("?H", "?D1")),
            ("id_edge", ("?D1", "?D2", "?IR")),
        ): 1,
        rule(("id_cycle", ("?W",)), ("id_path", ("?W", "?W"))): 1,
        rule(
            ("multiple_id_heads", ("?D",)),
            ("id_edge", ("?H1", "?D", "?R1")),
            ("id_edge", ("?H2", "?D", "?R2")),
            ("different_id_arcs", ("?H1", "?R1", "?H2", "?R2")),
        ): 1,
    }
)


FACTS: list[dlg.Fact] = [
    # Four word nodes and a small lexicon.
    fact("token", "w_peter"),
    fact("token", "w_buy"),
    fact("token", "w_det"),
    fact("token", "w_car"),
    fact("lemma", "w_peter", "peter"),
    fact("lemma", "w_buy", "kaufen"),
    fact("lemma", "w_det", "a"),
    fact("lemma", "w_car", "Auto"),
    fact("semantic_type", "w_peter", "person"),
    fact("semantic_type", "w_buy", "event"),
    fact("semantic_type", "w_det", "determiner"),
    fact("semantic_type", "w_car", "vehicle"),
    fact("id_root", "w_buy"),
    # ID candidates include a few bad alternatives so Datalog can demonstrate
    # lexical filtering, alongside the intended dependency tree.
    fact("id_candidate", "w_buy", "w_peter", "subj"),
    fact("id_candidate", "w_buy", "w_car", "obj"),
    fact("id_candidate", "w_car", "w_det", "det"),
    fact("id_candidate", "w_peter", "w_buy", "subj"),
    fact("id_candidate", "w_buy", "w_det", "obj"),
    fact("id_candidate", "w_buy", "w_peter", "obj"),
    # PA candidates are independent of the ID dimension. 'actor' is a valid
    # lexical role but is not linked to the subject role in this tiny grammar.
    fact("pa_candidate", "w_buy", "w_peter", "agent"),
    fact("pa_candidate", "w_buy", "w_car", "theme"),
    fact("pa_candidate", "w_buy", "w_peter", "actor"),
    fact("pa_candidate", "w_buy", "w_car", "agent"),
    # Ontology subsumption lets a specific base sense satisfy a general frame.
    fact("id_type_compatible", "person", "person"),
    fact("id_type_compatible", "vehicle", "vehicle"),
    fact("id_type_compatible", "determiner", "determiner"),
    fact("id_type_compatible", "asset", "asset"),
    fact("pa_type_compatible", "person", "person"),
    fact("pa_type_compatible", "vehicle", "vehicle"),
    fact("pa_type_compatible", "asset", "asset"),
    fact("id_type_compatible", "vehicle", "asset"),
    fact("pa_type_compatible", "vehicle", "asset"),
]

COMPILED_LEXICON = load_xdg_lexicon()
for entry_id in ("kaufen.v.purchase", "auto.n.vehicle"):
    lexical_entry = COMPILED_LEXICON[entry_id]
    lemma = lexical_entry["lemma"]
    xdg = lexical_entry["xdg"]
    for license_entry in xdg["ID"].get("licenses", []):
        FACTS.append(fact("id_licenses", lemma, license_entry["role"], license_entry["dependent_type"]))
    for license_entry in xdg["PA"].get("licenses", []):
        FACTS.append(fact("pa_licenses", lemma, license_entry["role"], license_entry["argument_type"]))
    for link in xdg.get("LINK", []):
        FACTS.append(fact("role_link", lemma, link["id_role"], link["pa_role"]))

TOKENS = ("w_peter", "w_buy", "w_det", "w_car")
ID_CANDIDATES = [args for predicate, args in FACTS if predicate == "id_candidate"]
FACTS.extend(
    fact("different_id_arcs", left_head, left_role, right_head, right_role)
    for left_head, left_dep, left_role in ID_CANDIDATES
    for right_head, right_dep, right_role in ID_CANDIDATES
    if left_dep == right_dep and (left_head, left_role) != (right_head, right_role)
)


def rows_by_predicate(result: ZSet) -> dict[str, list[tuple[Any, ...]]]:
    rows: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
    for (predicate, args), weight in result.inner.items():
        if weight > 0:
            rows[predicate].append(args)
    return rows


def print_edges(title: str, rows: list[tuple[Any, ...]]) -> None:
    print(title)
    for args in sorted(set(rows)):
        print("  " + " ".join(str(arg) for arg in args))


def main() -> None:
    engine = IncrementalDatalogStratified()
    engine.push_rules(RULES)
    engine.push_facts(ZSet({row: 1 for row in FACTS}))
    rows = rows_by_predicate(engine.saturate())

    print("Sentence: Peter kaufte ein Auto.")
    print("\nID dimension (head dependent syntactic-role):")
    for head, dependent, role_name in sorted(rows.get("id_edge", [])):
        print(f"  {head} -{role_name}-> {dependent}")

    print("\nPA dimension (predicate argument thematic-role):")
    for predicate, argument, role_name in sorted(rows.get("linked_pa_edge", [])):
        print(f"  {predicate} -{role_name}-> {argument}")

    print("\nLinking constraints (ID role paired with PA role):")
    for predicate, argument, id_role, pa_role in sorted(rows.get("linked_argument", [])):
        print(f"  {predicate} -{id_role}/{pa_role}-> {argument}")

    print("\nHard-constraint rejections:")
    print_edges("  Unlicensed ID candidates:", rows.get("rejected_id_candidate", []))
    print_edges("  Unlicensed PA candidates:", rows.get("rejected_pa_candidate", []))
    print_edges("  Licensed PA candidates with no ID/PA link:", rows.get("unlinked_pa_candidate", []))

    errors = {
        name: rows.get(name, [])
        for name in ("missing_id_head", "unreachable_id_node", "id_cycle", "multiple_id_heads")
        if rows.get(name)
    }
    print("\nID tree constraints:")
    if errors:
        print(f"  INVALID: {errors}")
        raise SystemExit(1)
    print("  one root, every token reachable, one head per dependent, no cycles")


if __name__ == "__main__":
    main()
