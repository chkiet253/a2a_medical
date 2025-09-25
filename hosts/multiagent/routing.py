# hosts/multiagent/routing.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict
import re

@dataclass
class RoutingDecision:
    agents: List[str]   # agents cần gọi
    reason: str
    chained: bool       # có cần chain không

KEYWORDS = {
    "diagnose": [r"chẩn đoán", r"triệu chứng", r"symptom", r"diagnose"],
    "cost":     [r"chi phí", r"cost", r"price", r"giá"],
    "schedule": [r"lịch", r"đặt hẹn", r"schedule", r"appointment"],
}
KNOWN_DISEASE = [
    r"viêm", r"ung thư", r"cảm", r"flu", r"asthma", r"covid",
    r"tiểu đường", r"diabetes", r"disease", r"bệnh"
]

def decide_route(user_text: str) -> RoutingDecision:
    text = user_text.lower()
    matches: Dict[str, bool] = {
        agent: any(re.search(p, text) for p in pats)
        for agent, pats in KEYWORDS.items()
    }
    chosen = [a for a, ok in matches.items() if ok]
    knows_disease = any(re.search(p, text) for p in KNOWN_DISEASE)

    # 1. biết bệnh + cost/schedule
    if knows_disease:
        if matches["cost"] and matches["schedule"]:
            return RoutingDecision(["cost", "schedule"],
                                   "User knows disease, wants cost+schedule",
                                   chained=False)
        if matches["cost"]:
            return RoutingDecision(["cost"], "User knows disease, wants cost", chained=False)
        if matches["schedule"]:
            return RoutingDecision(["schedule"], "User knows disease, wants schedule", chained=False)

    # 2. triệu chứng
    if "diagnose" in chosen:
        if matches["cost"] and matches["schedule"]:
            return RoutingDecision(["diagnose", "cost", "schedule"],
                                   "Symptoms + cost + schedule",
                                   chained=True)
        if matches["cost"]:
            return RoutingDecision(["diagnose", "cost"],
                                   "Symptoms + cost",
                                   chained=True)
        if matches["schedule"]:
            return RoutingDecision(["diagnose", "schedule"],
                                   "Symptoms + schedule",
                                   chained=True)
        return RoutingDecision(["diagnose"], "Symptoms only", chained=False)

    # 3. chỉ cost/schedule
    if chosen:
        return RoutingDecision(chosen, f"Direct intents {chosen}", chained=False)

    # 4. fallback
    return RoutingDecision(["diagnose"], "Default fallback to diagnose", chained=False)
    