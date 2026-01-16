from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional
import httpx

@dataclass(frozen=True)
class Card:
    name: str
    version: str
    url: str
    skills: List[str]

def fetch_card(base_url: str, timeout_s: float = 5.0) -> Card:
    base = base_url.rstrip("/")
    url = base + "/.well-known/agent.json"
    with httpx.Client(timeout=timeout_s) as client:
        r = client.get(url)
        r.raise_for_status()
        raw = r.json()
    return Card(
        name=str(raw.get("name", "")),
        version=str(raw.get("version", "")),
        url=str(raw.get("url", base)),
        skills=list(raw.get("skills") or []),
    )

def build_registry(agent_base_urls: List[str]) -> List[Card]:
    return [fetch_card(u) for u in agent_base_urls]

def select_by_skill(cards: List[Card], required_skill: str) -> Optional[Card]:
    for c in cards:
        if required_skill in c.skills:
            return c
    return None
