"""The single running example: three linked sentences and their graph candidates."""

from __future__ import annotations

from typing import Any

from xdg_datalog import fact


SENTENCES: list[dict[str, Any]] = [
    {
        "id": "s1",
        "text": "Peter schenkte Paul ein Auto.",
        "event": "transfer1",
        "lexical_lemma": "schenken",
        "lexical_frame": "transfer",
        "lexical_head": "give1",
        "nodes": [
            {"id": "Peter", "kind": "entity", "gender": "masc", "number": "sg", "type": "person"},
            {"id": "Paul", "kind": "entity", "gender": "masc", "number": "sg", "type": "person"},
            {"id": "Auto", "kind": "entity", "gender": "neut", "number": "sg", "type": "vehicle"},
            {"id": "give1", "kind": "lexical_unit", "form": "schenkte"},
            {"id": "cause1", "kind": "event", "predicate": "cause"},
            {"id": "transfer1", "kind": "event", "predicate": "transfer"},
            {"id": "m_peter_1", "kind": "mention", "form": "Peter"},
            {"id": "m_paul_1", "kind": "mention", "form": "Paul"},
            {"id": "m_ein_1", "kind": "word", "form": "ein"},
            {"id": "m_auto_1", "kind": "mention", "form": "ein Auto"},
        ],
        "id_edges": [
            ("give1", "m_peter_1", "subj"),
            ("give1", "m_paul_1", "iobj"),
            ("give1", "m_auto_1", "obj"),
            ("m_auto_1", "m_ein_1", "det"),
        ],
        "pa_edges": [
            ("cause1", "m_peter_1", "agent"),
            ("cause1", "transfer1", "theme"),
            ("transfer1", "m_peter_1", "agent"),
            ("transfer1", "m_paul_1", "recipient"),
            ("transfer1", "m_auto_1", "theme"),
        ],
        "link_edges": [
            ("m_peter_1", "refers_to", "Peter"),
            ("m_paul_1", "refers_to", "Paul"),
            ("m_auto_1", "refers_to", "Auto"),
        ],
        "facts": [
            fact("entity", "Peter", "masc", "sg", "person"),
            fact("entity", "Paul", "masc", "sg", "person"),
            fact("entity", "Auto", "neut", "sg", "vehicle"),
            fact("discourse_sentence", "s1"),
            fact("discourse_root", "s1"),
        ],
    },
    {
        "id": "s2",
        "text": "Paul lieh Peter das Auto.",
        "event": "lend2",
        "lexical_lemma": "leihen",
        "lexical_frame": "transfer",
        "lexical_head": "lend2",
        "nodes": [
            {"id": "Paul", "kind": "entity", "gender": "masc", "number": "sg", "type": "person"},
            {"id": "lend2", "kind": "event", "predicate": "lend"},
            {"id": "m_paul_2", "kind": "mention", "form": "Paul"},
            {"id": "m_peter_2", "kind": "mention", "form": "Peter"},
            {"id": "m_auto_2", "kind": "mention", "form": "das Auto"},
        ],
        "id_edges": [
            ("lend2", "m_paul_2", "subj"),
            ("lend2", "m_peter_2", "iobj"),
            ("lend2", "m_auto_2", "obj"),
        ],
        "pa_edges": [
            ("lend2", "m_paul_2", "agent"),
            ("lend2", "m_peter_2", "recipient"),
            ("lend2", "m_auto_2", "theme"),
        ],
        "link_edges": [
            ("m_paul_2", "refers_to", "Paul"),
            ("m_peter_2", "refers_to", "Peter"),
            ("m_auto_2", "refers_to", "Auto"),
        ],
        "facts": [
            fact("entity", "Paul", "masc", "sg", "person"),
            fact("discourse_sentence", "s2"),
            fact("discourse_id_candidate", "s1", "s2", "attachment"),
            fact("discourse_relation_candidate", "s1", "s2", "narration"),
            fact("discourse_qud_candidate", "s1", "s2", "maintains", "car_possession"),
        ],
    },
    {
        "id": "s3",
        "text": "Er fuhr es nach Hause.",
        "event": "drive3",
        "lexical_lemma": "fahren",
        "lexical_frame": "motion",
        "lexical_head": "drive3",
        "nodes": [
            {"id": "Home", "kind": "entity", "gender": "neut", "number": "sg", "type": "location"},
            {"id": "drive3", "kind": "event", "predicate": "drive"},
            {"id": "m_er", "kind": "pronoun", "form": "er", "gender": "masc", "number": "sg"},
            {"id": "m_es", "kind": "pronoun", "form": "es", "gender": "neut", "number": "sg"},
            {"id": "m_home_3", "kind": "mention", "form": "nach Hause"},
        ],
        "id_edges": [
            ("drive3", "m_er", "subj"),
            ("drive3", "m_es", "obj"),
            ("drive3", "m_home_3", "obl"),
        ],
        "pa_edges": [
            ("drive3", "m_er", "agent"),
            ("drive3", "m_es", "theme"),
            ("drive3", "m_home_3", "goal"),
        ],
        "link_edges": [("m_home_3", "refers_to", "Home")],
        # A deliberately broad candidate generator: offer each known entity.
        # PyDBSP then applies agreement and semantic-role constraints.
        "facts": [
            fact("entity", "Home", "neut", "sg", "location"),
            fact("pronoun", "m_er", "masc", "sg"),
            fact("pronoun", "m_es", "neut", "sg"),
            fact("mention_role", "m_er", "agent"),
            fact("mention_role", "m_es", "theme"),
            *(fact("candidate_ref", mention, entity) for mention in ("m_er", "m_es") for entity in ("Peter", "Paul", "Auto", "Home")),
            fact("discourse_sentence", "s3"),
            fact("discourse_id_candidate", "s2", "s3", "attachment"),
            fact("discourse_relation_candidate", "s2", "s3", "continuation"),
            fact("discourse_qud_candidate", "s2", "s3", "resolves", "car_possession"),
        ],
    },
]
