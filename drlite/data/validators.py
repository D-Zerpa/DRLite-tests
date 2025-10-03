from __future__ import annotations
from typing import List
from drlite.models import Question, Demon


def validate_questions_against_items(questions: List[Question]) -> None:
    """
    Scan all choices for ask_item events and ensure items exist in ITEM_CATALOG.
    Raise ValueError on first mismatch (fail fast).
    """
    for q in questions:
        for label, eff in q.choices.items():
            evt = eff.get("event")
            if isinstance(evt, dict) and str(evt.get("type", "")).lower() == "ask_item":
                iid = canonical_item_id(evt.get("item", ""))
                if iid not in ITEM_CATALOG:
                    raise ValueError(
                        f"Question '{q.id}' choice '{label}' references unknown item '{iid}'."
                        " Add it to data/items.json or fix the name."
                    )

def validate_event_refs(questions: List[Question]) -> None:
    for q in questions:
        for label, eff in q.choices.items():
            ref = eff.get("event_ref")
            if ref and ref not in EVENTS_REGISTRY:
                raise ValueError(f"Question '{q.id}' choice '{label}' references unknown event_ref '{ref}'.")