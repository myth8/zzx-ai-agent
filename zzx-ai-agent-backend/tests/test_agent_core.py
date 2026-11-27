"""Unit tests for the hand-written MultiStepAgent engine.

These tests use fake models so they are deterministic and never call DeepSeek.
"""
import json
import unittest
from unittest import mock

from app.agent_core import CodeAgent, ToolCallingAgent
from app.agent_core.local_python_executor import InterpreterError, LocalPythonExecutor
from app.agent_core.memory import ActionStep, AgentMemory, TaskStep
from app.agent_core.observability import AgentTrace
from app.agent_core.registry import (
    chat_type_for_engine,
    engine_for_chat_type,
    normalize_engine,
)
from app.agent_core.tools import build_tool_specs
from app.agent_core import runner
from app.agent_core.types import (
    ActionOutput,
    AgentEvent,
    ChatMessage,
    MessageRole,
    Timing,
    TokenUsage,
    ToolCall,
)
from app.llm.tool_registry import build_agent_tools


class ScriptedModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def generate(self, messages, stop_sequences=None, tools=None):
        self.calls += 1
        if not self.responses:
            raise AssertionError("ScriptedModel ran out of responses")
        response = self.responses.pop(0)
        return ChatMessage(
            role=MessageRole.ASSISTANT,
            content=response.get("content"),
            tool_calls=response.get("tool_calls", []),
            token_usage=TokenUsage(input_tokens=10, output_tokens=5),
        )


def make_tools():
    return list(build_tool_specs(build_agent_tools()).values())


class ToolSpecTest(unittest.TestCase):
    def test_specs_cover_the_same_catalogue_as_langchain(self):
        langchain_names = {tool.name for tool in build_agent_tools()}
        spec_names = {spec.name for spec in make_tools()}
        self.assertEqual(langchain_names, spec_names)

    def test_calc_spec_invokes_langchain_tool(self):
        specs = {spec.name: spec for spec in make_tools()}
        self.assertEqual(specs["calc"].invoke({"expr": "6 * 7"}), "42")

    def test_openai_schema_exposes_required_arguments(self):
        specs = {spec.name: spec for spec in make_tools()}
        schema = specs["calc"].to_openai_schema()["function"]
        self.assertEqual(schema["name"], "calc")
        self.assertIn("expr", schema["parameters"]["properties"])
        self.assertEqual(schema["parameters"]["required"], ["expr"])


class CodeAgentTest(unittest.TestCase):
    def test_python_action_can_compute_and_answer(self):
        model = ScriptedModel([
            {"content": 'Thought: calculate\n```python\nresult = calc(expr="2 + 3")\nprint(result)\n```'},
            {"content": 'Thought: finish\n```python\nfinal_answer(result * 2)\n```'},
        ])
        agent = CodeAgent(tools=make_tools(), model=model, max_steps=3)
        events = []
        final = None
        for item in agent.run_stream("compute"):
            if isinstance(item, AgentEvent):
                events.append(item)
            elif item.is_final_answer:
                final = item.output

        self.assertEqual(final, "55")
        self.assertEqual(agent.step_count, 2)
        self.assertEqual(agent.token_usage.input_tokens, 20)
        self.assertEqual(agent.token_usage.output_tokens, 10)
        self.assertTrue(any(event.kind == "code" for event in events))
        self.assertTrue(any(event.kind == "observe" for event in events))
        self.assertTrue(any(event.kind == "final" for event in events))

    def test_tool_calls_are_counted_from_real_invocations(self):
        model = ScriptedModel([
            {"content": '```python\nprint(calc(expr="6*7"))\n```'},
            {"content": '```python\nfinal_answer("42")\n```'},
        ])
        agent = CodeAgent(tools=make_tools(), model=model, max_steps=3)
        for _ in agent.run_stream("count"):
            pass
        # calc() is the only real tool call; print/final_answer are not tools.
        self.assertEqual(agent.tool_call_count, 1)
        self.assertEqual(agent.tool_error_count, 0)
        self.assertEqual(agent.llm_calls, 2)

    def test_code_without_tools_reports_zero_tool_calls(self):
        model = ScriptedModel([
            {"content": "```python\nfinal_answer(1 + 1)\n```"},
        ])
        agent = CodeAgent(tools=make_tools(), model=model, max_steps=2)
        for _ in agent.run_stream("pure math"):
            pass
        self.assertEqual(agent.tool_call_count, 0)

    def test_execution_error_is_fed_back_then_recovers(self):
        model = ScriptedModel([
            {"content": "```python\nunknown_tool(query='x')\n```"},
            {"content": "```python\nfinal_answer('recovered')\n```"},
        ])
        agent = CodeAgent(tools=make_tools(), model=model, max_steps=3)
        final = None
        for item in agent.run_stream("recover"):
            if not isinstance(item, AgentEvent) and item.is_final_answer:
                final = item.output
        self.assertEqual(final, "recovered")
        self.assertIsNotNone(agent.memory.steps[1].error)

    def test_dangerous_import_is_rejected(self):
        executor = LocalPythonExecutor([], timeout_seconds=5)
        with self.assertRaises(InterpreterError):
            executor("import os\nos.system('echo unsafe')")


class ToolCallingAgentTest(unittest.TestCase):
    def test_native_tool_call_then_final_answer(self):
        model = ScriptedModel([
            {"content": None, "tool_calls": [ToolCall("calc", {"expr": "2 + 3"}, "c1")]},
            {"content": None, "tool_calls": [ToolCall("final_answer", {"answer": "5"}, "c2")]},
        ])
        agent = ToolCallingAgent(tools=make_tools(), model=model, max_steps=3)
        events = []
        final = None
        for item in agent.run_stream("compute"):
            if isinstance(item, AgentEvent):
                events.append(item)
            elif item.is_final_answer:
                final = item.output

        self.assertEqual(final, "5")
        self.assertEqual(agent.tool_call_count, 1)
        self.assertEqual(agent.step_count, 2)
        self.assertTrue(any("calc" in event.text for event in events))

    def test_direct_text_answer_is_accepted(self):
        model = ScriptedModel([{"content": "I think the answer is 5."}])
        agent = ToolCallingAgent(tools=make_tools(), model=model, max_steps=3)
        final = None
        for item in agent.run_stream("compute"):
            if not isinstance(item, AgentEvent) and item.is_final_answer:
                final = item.output
        self.assertEqual(final, "I think the answer is 5.")
        self.assertEqual(agent.llm_calls, 1)
        self.assertIsNone(agent.memory.steps[-1].error)

    def test_empty_model_output_gets_retry_observation(self):
        model = ScriptedModel([
            {"content": ""},
            {"content": None, "tool_calls": [ToolCall("final_answer", {"answer": "5"}, "c1")]},
        ])
        agent = ToolCallingAgent(tools=make_tools(), model=model, max_steps=3)
        final = None
        for item in agent.run_stream("compute"):
            if not isinstance(item, AgentEvent) and item.is_final_answer:
                final = item.output
        self.assertEqual(final, "5")
        self.assertIsNotNone(agent.memory.steps[1].error)

    def test_unknown_tool_is_returned_as_observation(self):
        model = ScriptedModel([
            {"content": None, "tool_calls": [ToolCall("missing_tool", {}, "c1")]},
            {"content": None, "tool_calls": [ToolCall("final_answer", {"answer": "ok"}, "c2")]},
        ])
        agent = ToolCallingAgent(tools=make_tools(), model=model, max_steps=3)
        final = None
        for item in agent.run_stream("test"):
            if not isinstance(item, AgentEvent) and item.is_final_answer:
                final = item.output
        self.assertEqual(final, "ok")
        responses = agent.memory.steps[1].tool_responses
        self.assertIn("未知工具", responses[0].content)


class ContextManagementTest(unittest.TestCase):
    def test_old_action_steps_are_omitted_and_messages_are_truncated(self):
        memory = AgentMemory("system prompt")
        memory.append(TaskStep(task="task"))
        for index in range(6):
            step = ActionStep(step_number=index + 1, timing=Timing(start_time=0, end_time=1))
            step.model_output_message = ChatMessage(
                role=MessageRole.ASSISTANT,
                content=f"assistant-{index} " + ("x" * 800),
            )
            step.observations = "observation-" + ("y" * 800)
            memory.append(step)

        messages = memory.to_messages(
            max_chars=3000,
            keep_recent_steps=2,
            max_message_chars=300,
        )
        stats = memory.last_context_stats
        self.assertGreaterEqual(stats["omitted_steps"], 4)
        self.assertLessEqual(stats["kept_steps"], 2)
        self.assertGreater(stats["truncated_messages"], 0)
        self.assertLessEqual(sum(len(m.content or "") for m in messages), 3000)
        self.assertTrue(any("上下文压缩" in (m.content or "") for m in messages))

    def test_no_compaction_without_budget(self):
        memory = AgentMemory("system")
        memory.append(TaskStep(task="task"))
        messages = memory.to_messages()
        self.assertEqual(len(messages), 2)


class ObservabilityTest(unittest.TestCase):
    def test_trace_sink_receives_the_same_redacted_payload(self):
        received = []
        trace = AgentTrace("react", session_id="s", request_id="r", run_id="run-1", sink=received.append)
        trace.run_start(task_chars=10)
        trace.run_finish(status="success", steps=1)
        self.assertEqual([item["event"] for item in received], ["run_start", "run_finish"])
        self.assertEqual(received[0]["run_id"], "run-1")
        self.assertNotIn("message", received[0])

    def test_telemetry_recorder_is_inert_without_flask_context(self):
        from app.telemetry import TelemetryRecorder

        recorder = TelemetryRecorder("code", "session", "request", user_id=1)
        self.assertFalse(recorder.start())
        self.assertFalse(recorder.enabled)

    def test_structured_trace_events_are_json_and_content_free(self):
        with self.assertLogs("agent.trace", level="INFO") as captured:
            trace = AgentTrace("code", session_id="session-1", request_id="request-1")
            trace.run_start(task_chars=42, tools=6)
            trace.step_end(step=1, duration_ms=12, tool_calls=2, context={"chars": 100})
            trace.run_finish(status="success", steps=1)

        payloads = []
        for line in captured.output:
            if "agent_trace " in line:
                payloads.append(json.loads(line.split("agent_trace ", 1)[1]))
        self.assertEqual([p["event"] for p in payloads], ["run_start", "step_end", "run_finish"])
        self.assertEqual(payloads[0]["engine"], "code")
        self.assertEqual(payloads[0]["session_id"], "session-1")
        self.assertEqual(payloads[1]["duration_ms"], 12)
        self.assertNotIn("task", payloads[0])


class AgentMetricsCallbackTest(unittest.TestCase):
    def test_extracts_tokens_from_llm_output(self):
        from types import SimpleNamespace
        from app.llm.agent_metrics import AgentMetricsCallback

        metrics = AgentMetricsCallback()
        response = SimpleNamespace(
            llm_output={"token_usage": {"prompt_tokens": 12, "completion_tokens": 3}},
            generations=[],
        )
        metrics.on_llm_end(response)
        self.assertEqual(metrics.llm_calls, 1)
        self.assertEqual(metrics.prompt_tokens, 12)
        self.assertEqual(metrics.completion_tokens, 3)

    def test_nested_tool_calls_are_not_double_counted(self):
        from app.llm.agent_metrics import AgentMetricsCallback

        metrics = AgentMetricsCallback()
        metrics.on_tool_start({}, "outer", run_id="outer-id", parent_run_id="agent-id")
        metrics.on_tool_start({}, "inner", run_id="inner-id", parent_run_id="outer-id")
        self.assertEqual(metrics.tool_calls, 1)
        metrics.on_tool_end("ok", run_id="inner-id", parent_run_id="outer-id")
        metrics.on_tool_end("ok", run_id="outer-id", parent_run_id="agent-id")
        self.assertEqual(metrics.tool_calls, 1)


class RunnerTest(unittest.TestCase):
    def test_stream_maps_events_and_meta(self):
        class FakeAgent:
            step_count = 2
            llm_calls = 2
            tool_call_count = 1
            tool_error_count = 0
            token_usage = TokenUsage(input_tokens=30, output_tokens=12)

            def run_stream(self, task):
                yield AgentEvent("think", "working")
                yield AgentEvent("code", "print(1)")
                yield AgentEvent("final", "done")
                yield ActionOutput(output="done", is_final_answer=True)

        with mock.patch.object(runner, "_build_agent", return_value=FakeAgent()):
            chunks = list(runner.stream_multistep_agent("code", "task", "system"))
        self.assertIn("[THINK] working", chunks)
        self.assertIn("[CODE] print(1)", chunks)
        self.assertIn("[FINAL] done", chunks)
        meta = json.loads(next(chunk for chunk in chunks if chunk.startswith("[META]")).split(" ", 1)[1])
        self.assertEqual(meta["engine"], "code")
        self.assertEqual(meta["steps"], 2)
        self.assertEqual(meta["tool_calls"], 1)


class EngineResolutionTest(unittest.TestCase):
    def test_session_engine_cannot_be_switched(self):
        from app.routes.manus import _resolve_engine
        session = {"chat_type": "agent"}
        self.assertEqual(_resolve_engine("", session), "react")
        self.assertEqual(_resolve_engine("langchain", session), "react")
        with self.assertRaises(ValueError):
            _resolve_engine("code", session)


class EngineRegistryTest(unittest.TestCase):
    def test_aliases_and_chat_types(self):
        self.assertEqual(normalize_engine("langchain"), "react")
        self.assertEqual(chat_type_for_engine("react"), "agent")
        self.assertEqual(chat_type_for_engine("toolcalling"), "toolcalling")
        self.assertEqual(engine_for_chat_type("code"), "code")
        with self.assertRaises(ValueError):
            normalize_engine("not-an-engine")


if __name__ == "__main__":
    unittest.main()
