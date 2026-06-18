from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.graph import END, StateGraph

from src.agents.state import RunState

ALL_PIPELINE_STAGES: list[str] = [
    "qc",
    "alignment",
    "quantification",
    "variant_calling",
    "splicing",
    "differential_expression",
    "gsea",
    "scrna_seq",
    "visualization",
    "report",
]


def _next_stage(state: RunState) -> str:
    """Conditional edge: return the next unexecuted stage, or END."""
    if state.get("failed_stage"):
        return END
    planned: list[str] = state.get("stages", [])
    completed: list[str] = state.get("completed_stages", [])
    for stage in planned:
        if stage not in completed:
            return stage
    return END


def _router_node(state: RunState) -> dict:
    """No-op control node. Routing is handled by the outgoing conditional edge."""
    return {}


def _make_stub_node(stage_name: str) -> Callable[[RunState], dict]:
    """Return a stub stage node that marks the stage as completed in RunState."""

    def _node(state: RunState) -> dict:
        completed = list(state.get("completed_stages", []))
        if stage_name not in completed:
            completed.append(stage_name)
        return {
            "completed_stages": completed,
            "current_stage": stage_name,
        }

    _node.__name__ = f"{stage_name}_node"
    return _node


def build_pipeline_graph() -> Any:
    """Build and compile the LangGraph StateGraph for the RNA-seq pipeline."""
    graph: StateGraph = StateGraph(RunState)

    graph.add_node("router", _router_node)
    graph.set_entry_point("router")

    for stage in ALL_PIPELINE_STAGES:
        graph.add_node(stage, _make_stub_node(stage))
        graph.add_edge(stage, "router")

    stage_map: dict[str, str] = {s: s for s in ALL_PIPELINE_STAGES}
    graph.add_conditional_edges("router", _next_stage, {**stage_map, END: END})

    return graph.compile()
