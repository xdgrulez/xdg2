"""Jev classification and non-binding discourse preferences."""

from __future__ import annotations

from typing import Any

from xdg_graph import DiscourseGraph


class JevClassifier:
    """Classify only alternatives which have survived hard DBSP constraints."""

    def choose(
        self,
        *,
        state: dict[str, Any],
        criteria: dict[str, str],
        question_name: str = "antecedent",
        instructions: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        try:
            from typesafe_sdk import Choice, TypeSafeClient
        except ImportError as exc:  # pragma: no cover - installation guidance
            raise RuntimeError("typesafe-sdk fehlt; installiere requirements.txt.") from exc

        if instructions is None:
            instructions = (
                "Wähle den im Diskursgraphen plausibelsten Antezedenten für die aktuelle Pronomen-Mention. "
                "Nutze Grices Relevanzmaxime in Bezug auf die offene Question Under Discussion und den "
                "vorherigen Backward Center als Präferenzen. Berücksichtige die Rollen und Relationen im "
                "Multigraphen. Die Kriterien sind ausschließlich durch harte Constraints zugelassene "
                "Alternativen; Präferenzen dürfen sie nicht erweitern."
            )

        with TypeSafeClient(model="jev-latest") as client:
            response = client.system_one(
                state=state,
                questions={
                    question_name: Choice(
                        instructions=instructions,
                        criteria=criteria,
                    )
                },
            )
        answer = response.answers[question_name]
        details = {
            "choice": answer.choice,
            "probabilities": answer.probabilities,
            "confidence": answer.confidence,
        }
        return answer.choice, details


def offline_choice(criteria: dict[str, str], preferences: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Stable placeholder for running the demo without network/API access."""
    center_matches = preferences.get("Centering_Theory", {}).get("candidate_matches_previous_backward_center", {})
    choice = next((candidate for candidate in criteria if center_matches.get(candidate)), next(iter(criteria)))
    return choice, {"choice": choice, "probabilities": {choice: 1.0}, "confidence": 1.0, "mode": "offline-demo"}


def centering_evidence(graph: DiscourseGraph, candidates: list[str]) -> dict[str, Any]:
    """Expose Centering-style prominence as preference evidence, never a filter."""
    sentence_by_id = {sentence["id"]: sentence for sentence in graph.sentence_graphs}
    role_rank = {"subj": 0, "obj": 1, "iobj": 2}

    def forward_centers(sentence_id: str) -> list[str]:
        sentence = sentence_by_id[sentence_id]
        refs = {
            edge["source"]: edge["target"]
            for edge in sentence["dimensions"]["linking"]
            if edge["relation"] in {"refers_to", "corefers_with"}
        }
        ranked = [
            (role_rank.get(edge["relation"], 99), refs[edge["target"]])
            for edge in sentence["dimensions"]["ID"]
            if edge["target"] in refs
        ]
        ordered: list[str] = []
        for _, entity in sorted(ranked):
            if entity not in ordered:
                ordered.append(entity)
        return ordered

    if len(graph.sentence_graphs) < 2:
        return {"framework": "Centering Theory", "status": "insufficient prior units"}

    previous_id = graph.sentence_graphs[-2]["id"]
    prior_id = graph.sentence_graphs[-3]["id"] if len(graph.sentence_graphs) >= 3 else graph.sentence_graphs[-2]["id"]
    previous_centers = forward_centers(previous_id)
    prior_centers = forward_centers(prior_id)
    backward_center = next((entity for entity in prior_centers if entity in previous_centers), None)
    return {
        "framework": "Centering Theory (Grosz, Joshi & Weinstein, 1995)",
        "previous_unit": previous_id,
        "previous_forward_centers_ranked": previous_centers,
        "backward_center_from_prior_unit": backward_center,
        "candidate_matches_previous_backward_center": {
            entity: entity == backward_center
            for entity in candidates
        },
    }
