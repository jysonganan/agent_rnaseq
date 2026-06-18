from __future__ import annotations

import abc
from typing import Any

from src.agents.state import RunState, StageState


class MockToolRegistry:
    """Maps tool names to canned fixture dicts for dry-run mode."""

    def __init__(self) -> None:
        self._fixtures: dict[str, dict] = {}

    def register(self, tool_name: str, fixture: dict) -> None:
        self._fixtures[tool_name] = fixture

    def get_mock_output(self, tool_name: str) -> dict:
        return self._fixtures.get(tool_name, {})


class BaseStageAgent(abc.ABC):
    """Common interface for all specialist sub-agents.

    Subclasses implement ``_run`` with actual tool calls.
    When ``dry_run=True``, ``_run`` is never called; mock fixtures are returned instead.
    """

    def __init__(
        self,
        stage_name: str,
        dry_run: bool = False,
        mock_registry: MockToolRegistry | None = None,
    ) -> None:
        self.stage_name = stage_name
        self.dry_run = dry_run
        self._mock_registry: MockToolRegistry = mock_registry or MockToolRegistry()

    def execute(self, state: RunState) -> StageState:
        """Execute this stage; return a completed or failed StageState."""
        if self.dry_run:
            output = self._mock_registry.get_mock_output(self.stage_name)
            return StageState(
                stage_name=self.stage_name,
                status="completed",
                output=output,
                error=None,
            )
        try:
            output = self._run(state)
            return StageState(
                stage_name=self.stage_name,
                status="completed",
                output=output,
                error=None,
            )
        except Exception as exc:
            return StageState(
                stage_name=self.stage_name,
                status="failed",
                output=None,
                error=str(exc),
            )

    @abc.abstractmethod
    def _run(self, state: RunState) -> dict[str, Any]:
        """Subclasses implement actual deterministic tool calls here."""
