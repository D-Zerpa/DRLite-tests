from __future__ import annotations
from typing import TypedDict, Literal, NotRequired, List, Dict, Any
from drlite.models import Rarity

class EventPayload(TypedDict, total=False):
    type: Literal["ask_gold", "ask_item", "trap", "whim"]
    message: NotRequired[str]
    # ask_gold
    amount: NotRequired[int]
    pay_rapport: NotRequired[int]
    refuse_rapport: NotRequired[int]
    flee_on_refuse: NotRequired[bool]
    join_on_pay: NotRequired[bool]
    # ask_item
    item: NotRequired[str]
    amount: NotRequired[int]
    amount_range: NotRequired[List[int]]
    consume: NotRequired[bool]
    give_rapport: NotRequired[int]
    decline_rapport: NotRequired[int]
    join_on_give: NotRequired[bool]
    # trap
    penalty_rapport: NotRequired[int]
    flee_chance: NotRequired[float]
    # whim
    kind: NotRequired[str]
    only_if_has_item: NotRequired[bool]
    weight: NotRequired[int]

class Effect(TypedDict, total=False):
    dLC: int
    dLD: int
    dRapport: int
    tags: List[str]
    event: EventPayload
    event_ref: str

class ItemDef(TypedDict, total=False):
    display_name: str
    rarity: Rarity
    value: int
    stackable: bool
    description: str
