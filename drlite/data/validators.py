from __future__ import annotations
from typing import List
from drlite.data.types import Effect
from drlite.models import Question, Demon
from drlite.utils import canonical_item_id
from drlite.models import Question

def validate_questions_against_items(questions: List[Question], item_catalog: Dict[str, Any]) -> None:
    """
    Scan all choices for ask_item events and ensure items exist in ITEM_CATALOG.
    Raise ValueError on first mismatch (fail fast).
    """
    for q in questions:
        for label, eff in q.choices.items():
            evt = eff.get("event")
            if isinstance(evt, dict) and str(evt.get("type", "")).lower() == "ask_item":
                iid = canonical_item_id(evt.get("item", ""))
                if iid not in item_catalog:
                    raise ValueError(
                        f"Question '{q.id}' choice '{label}' references unknown item '{iid}'."
                        " Add it to data/items.json or fix the name."
                    )

def validate_events_against_items(events_registry: Dict[str, Any], item_catalog: Dict[str, Any]) -> None:
    for eid, ev in events_registry.items():
        if ev.get("type") == "ask_item":
            iid = canonical_item_id(ev.get("item", ""))
            if iid not in item_catalog:
                raise ValueError(f"Event '{eid}' references unknown item '{iid}'.")

def validate_event_refs(questions: List[Question], events_registry: Dict[str, Any]) -> None:
    """
    Validate that all event_ref in questions exist in the provided events_registry.
    """
    for q in questions:
        for label, eff in q.choices.items():
            # Obtener event_ref de forma segura (sea dict o objeto)
            ref = eff.get("event_ref") if isinstance(eff, dict) else getattr(eff, "event_ref", None)
            
            # Usamos el registro inyectado (events_registry), no una global
            if ref and ref not in events_registry:
                raise ValueError(f"Question '{q.id}' choice '{label}' references unknown event_ref '{ref}'.")