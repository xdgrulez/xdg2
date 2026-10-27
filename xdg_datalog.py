"""Hard XDG constraints and small PyDBSP helpers."""

from __future__ import annotations

from typing import Any

try:
    from pydbsp import datalog as dlg
    from pydbsp.zset import ZSet
except ImportError as exc:  # pragma: no cover - installation guidance
    raise SystemExit(
        "PyDBSP fehlt. Installiere die Abhängigkeiten mit "
        "`python -m pip install -r requirements.txt`."
    ) from exc


def fact(predicate: str, *args: Any) -> dlg.Fact:
    return predicate, tuple(args)


def rule(head: dlg.Atom, *body: dlg.Atom) -> dlg.Rule:
    return (head, *body)


def as_zset(items: list[tuple[Any, ...]]) -> ZSet:
    """Make a set-valued DBSP delta, dropping duplicate rows."""
    return ZSet({item: 1 for item in items})


# Every rule below is a hard constraint: missing compatibility means invalid.
RULES = ZSet(
    {
        rule(
            ("agreement_candidate", ("?M", "?E", "?T")),
            ("candidate_ref", ("?M", "?E")),
            ("pronoun", ("?M", "?PG", "?PN")),
            ("entity", ("?E", "?EG", "?EN", "?T")),
            ("gender_ok", ("?PG", "?EG")),
            ("number_ok", ("?PN", "?EN")),
        ): 1,
        rule(
            ("valid_ref", ("?M", "?E")),
            ("agreement_candidate", ("?M", "?E", "?T")),
            ("mention_role", ("?M", "?R")),
            ("role_type_ok", ("?R", "?T")),
        ): 1,
        rule(
            ("rejected_ref", ("?M", "?E", "gender_mismatch")),
            ("candidate_ref", ("?M", "?E")),
            ("pronoun", ("?M", "?PG", "?PN")),
            ("entity", ("?E", "?EG", "?EN", "?T")),
            ("gender_bad", ("?PG", "?EG")),
        ): 1,
        rule(
            ("rejected_ref", ("?M", "?E", "number_mismatch")),
            ("candidate_ref", ("?M", "?E")),
            ("pronoun", ("?M", "?PG", "?PN")),
            ("entity", ("?E", "?EG", "?EN", "?T")),
            ("number_bad", ("?PN", "?EN")),
        ): 1,
        rule(
            ("rejected_ref", ("?M", "?E", "role_type_mismatch")),
            ("candidate_ref", ("?M", "?E")),
            ("mention_role", ("?M", "?R")),
            ("entity", ("?E", "?G", "?N", "?T")),
            ("role_type_bad", ("?R", "?T")),
        ): 1,
        rule(
            ("discourse_id_edge", ("?P", "?S", "?R")),
            ("discourse_id_candidate", ("?P", "?S", "?R")),
            ("discourse_sentence", ("?P",)),
            ("discourse_sentence", ("?S",)),
            ("discourse_id_role", ("?R",)),
        ): 1,
        rule(
            ("discourse_relation_edge", ("?S1", "?S2", "?R")),
            ("discourse_relation_candidate", ("?S1", "?S2", "?R")),
            ("discourse_sentence", ("?S1",)),
            ("discourse_sentence", ("?S2",)),
            ("discourse_relation_type", ("?R",)),
        ): 1,
        rule(
            ("discourse_qud_edge", ("?S1", "?S2", "?R", "?Q")),
            ("discourse_qud_candidate", ("?S1", "?S2", "?R", "?Q")),
            ("discourse_sentence", ("?S1",)),
            ("discourse_sentence", ("?S2",)),
            ("qud_relation_type", ("?R",)),
        ): 1,
        rule(("discourse_has_parent", ("?S",)), ("discourse_id_edge", ("?P", "?S", "?R"))): 1,
        rule(
            ("discourse_missing_parent", ("?S",)),
            ("discourse_sentence", ("?S",)),
            ("!discourse_root", ("?S",)),
            ("!discourse_has_parent", ("?S",)),
        ): 1,
        rule(
            ("discourse_reach", ("?R", "?S")),
            ("discourse_root", ("?R",)),
            ("discourse_id_edge", ("?R", "?S", "?Role")),
        ): 1,
        rule(
            ("discourse_reach", ("?R", "?S2")),
            ("discourse_reach", ("?R", "?S1")),
            ("discourse_id_edge", ("?S1", "?S2", "?Role")),
        ): 1,
        rule(
            ("discourse_rooted", ("?S",)),
            ("discourse_root", ("?R",)),
            ("discourse_reach", ("?R", "?S")),
        ): 1,
        rule(
            ("discourse_unreachable", ("?S",)),
            ("discourse_sentence", ("?S",)),
            ("!discourse_root", ("?S",)),
            ("!discourse_rooted", ("?S",)),
        ): 1,
        rule(("discourse_path", ("?S1", "?S2")), ("discourse_id_edge", ("?S1", "?S2", "?Role"))): 1,
        rule(
            ("discourse_path", ("?S1", "?S3")),
            ("discourse_path", ("?S1", "?S2")),
            ("discourse_id_edge", ("?S2", "?S3", "?Role")),
        ): 1,
        rule(("discourse_cycle", ("?S",)), ("discourse_path", ("?S", "?S"))): 1,
        rule(
            ("discourse_multiple_parents", ("?S",)),
            ("discourse_id_edge", ("?P1", "?S", "?R1")),
            ("discourse_id_edge", ("?P2", "?S", "?R2")),
            ("different_discourse_sentences", ("?P1", "?P2")),
        ): 1,
    }
)


def constraint_facts(sentence_ids: tuple[str, ...]) -> list[dlg.Fact]:
    """Static agreement, semantic-role, and discourse vocabulary facts."""
    genders = ("masc", "fem", "neut")
    numbers = ("sg", "pl")
    role_types = {"agent": ("person",), "theme": ("vehicle",), "goal": ("location",)}
    rows = [fact("gender_ok", gender, gender) for gender in genders]
    rows += [fact("gender_bad", left, right) for left in genders for right in genders if left != right]
    rows += [fact("number_ok", number, number) for number in numbers]
    rows += [fact("number_bad", left, right) for left in numbers for right in numbers if left != right]
    rows += [
        fact("role_type_ok", role, entity_type)
        for role, entity_types in role_types.items()
        for entity_type in entity_types
    ]
    rows += [
        fact("role_type_bad", role, entity_type)
        for role in role_types
        for entity_type in ("person", "vehicle", "location")
        if entity_type not in role_types[role]
    ]
    rows += [fact("discourse_id_role", "attachment")]
    rows += [fact("discourse_relation_type", relation) for relation in ("narration", "continuation", "elaboration")]
    rows += [fact("qud_relation_type", relation) for relation in ("maintains", "resolves", "opens")]
    rows += [
        fact("different_discourse_sentences", left, right)
        for left in sentence_ids
        for right in sentence_ids
        if left != right
    ]
    return rows
