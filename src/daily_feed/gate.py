"""LangGraph gate. A streamer posts once an hour, and only while live. Other posts wait for 3pm Chicago and a real change. Nothing with a ping gets through."""

from __future__ import annotations

from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from daily_feed.safety import find_pings


class GateState(TypedDict, total=False):
    has_twitch: bool
    live: bool
    hour_due: bool
    day_due: bool
    changed: bool
    text: str
    route: str
    decision: str


def _route(state: GateState) -> Literal["streamer", "daily"]:
    if state.get("has_twitch"):
        return "streamer"
    return "daily"


def _classify(state: GateState) -> GateState:
    return {"route": _route(state)}


def _streamer(state: GateState) -> GateState:
    post = bool(state.get("live")) and bool(state.get("hour_due"))
    return {"decision": "post" if post else "skip"}


def _daily(state: GateState) -> GateState:
    post = bool(state.get("day_due")) and bool(state.get("changed"))
    return {"decision": "post" if post else "skip"}


def _safety(state: GateState) -> GateState:
    if state.get("decision") != "post":
        return {"decision": "skip"}
    if find_pings(state.get("text") or ""):
        return {"decision": "skip"}
    return {"decision": "post"}


def _build():
    graph = StateGraph(GateState)
    graph.add_node("classify", _classify)
    graph.add_node("streamer", _streamer)
    graph.add_node("daily", _daily)
    graph.add_node("safety", _safety)
    graph.add_edge(START, "classify")
    graph.add_conditional_edges("classify", _route, {"streamer": "streamer", "daily": "daily"})
    graph.add_edge("streamer", "safety")
    graph.add_edge("daily", "safety")
    graph.add_edge("safety", END)
    return graph.compile()


_GRAPH = _build()


def allow_post(
    *,
    has_twitch: bool,
    live: bool,
    hour_due: bool,
    day_due: bool,
    changed: bool,
    text: str,
) -> bool:
    """True only when this item may be sent."""
    result = _GRAPH.invoke(
        {
            "has_twitch": has_twitch,
            "live": live,
            "hour_due": hour_due,
            "day_due": day_due,
            "changed": changed,
            "text": text,
        }
    )
    return result.get("decision") == "post"
