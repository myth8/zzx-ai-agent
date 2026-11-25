"""Structured observability for Agent runs.

Borrowed from smolagents' logger/monitor idea: each run and each step should be
inspectable without dumping user content. This module emits one JSON object per
log line under the ``agent.trace`` logger. It records lengths, timings, token
deltas and tool counts, never raw prompts, tool arguments or answers.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from app.config import Config


logger = logging.getLogger("agent.trace")


class AgentTrace:
    def __init__(
        self,
        engine: str,
        session_id: str = "",
        request_id: str = "",
        run_id: str = "",
        sink: Callable[[dict[str, Any]], None] | None = None,
    ):
        self.engine = engine
        self.session_id = session_id or "-"
        self.request_id = request_id or "-"
        self.run_id = run_id or "-"
        self.sink = sink

    def _emit(self, event: str, **fields: Any) -> None:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "engine": self.engine,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "request_id": self.request_id,
        }
        payload.update(fields)
        if Config.AGENT_TRACE_LOG_ENABLED:
            logger.info(
                "agent_trace %s",
                json.dumps(payload, ensure_ascii=False, default=str),
            )
        if self.sink is not None:
            try:
                self.sink(payload)
            except Exception:  # noqa: BLE001 - observability must not break a run
                logger.exception("agent trace sink failed")

    def event(self, event: str, **fields: Any) -> None:
        self._emit(event, **fields)

    def run_start(self, **fields: Any) -> None:
        self._emit("run_start", **fields)

    def run_finish(self, **fields: Any) -> None:
        self._emit("run_finish", **fields)

    def step_end(self, **fields: Any) -> None:
        self._emit("step_end", **fields)

    def step_error(self, **fields: Any) -> None:
        self._emit("step_error", **fields)

    def max_steps_reached(self, **fields: Any) -> None:
        self._emit("max_steps_reached", **fields)

    def llm_end(self, **fields: Any) -> None:
        self._emit("llm_end", **fields)

    def tool_start(self, **fields: Any) -> None:
        self._emit("tool_start", **fields)

    def tool_error(self, **fields: Any) -> None:
        self._emit("tool_error", **fields)
