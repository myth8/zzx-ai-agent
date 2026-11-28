"""Reproducible benchmark for the three agent engines.

Run from the backend directory:

    python scripts/benchmark_agents.py --runs 3

The script calls the same tools, model and system prompt as production, but
does not go through Flask/JWT. Each engine gets its own agent instance and the
reported metrics come from the engine's [META] event, so this is the same data
the UI displays.
"""
import argparse
import json
import logging
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import Config  # noqa: E402
from app.llm.agent import stream_agent  # noqa: E402
from app.llm.skill_middleware import create_agent  # noqa: E402
from app.llm.tool_registry import BASE_TOOLS, build_agent_tools, skill_middleware  # noqa: E402
from app.agent_core.runner import stream_multistep_agent  # noqa: E402


SYSTEM_PROMPT = (
    "You are AI Super Agent, a versatile assistant."
    "Answer in Chinese. Be clear, structured, and helpful."
)

TASKS = [
    {
        "id": "no_tool",
        "category": "baseline",
        "prompt": "用三句话解释 ReAct Agent 和普通 Chain 的区别，不要调用任何工具。",
    },
    {
        "id": "single_time",
        "category": "single-tool",
        "prompt": "现在几点了？请调用工具获取准确时间，并直接回答。",
    },
    {
        "id": "single_calc",
        "category": "single-tool",
        "prompt": "请计算 (128 * 7 - 56) / 4，最终只给出结果。",
    },
    {
        "id": "multi_tool",
        "category": "multi-tool",
        "prompt": "一次回答里同时告诉我三件事：1) 现在几点；2) 23 * 17 的结果；3) 上海现在的天气。",
    },
    {
        "id": "rag_advice",
        "category": "rag",
        "prompt": "异地恋总是没有安全感，有什么具体可执行的建议？请先检索知识库，再分点回答。",
    },
    {
        "id": "code_compute",
        "category": "computation-heavy",
        "prompt": (
            "请计算 1 到 100 中所有偶数的和，并告诉我其中有多少个偶数能被 3 整除。"
            "请使用可用工具或代码完成，不要凭记忆直接给答案。"
        ),
    },
    {
        "id": "skill_confession",
        "category": "skills",
        "prompt": "我想今晚向女朋友表白，帮我写一段约 200 字的表白文案。",
    },
]

TIME_PATTERN = re.compile(r"\d{4}[-年]\d{1,2}[-月]\d{1,2}")
CLOCK_PATTERN = re.compile(r"\d{1,2}:\d{2}")
ANSWER_CHECKS = {
    "no_tool": lambda text, m: len(text) >= 20 and m.get("tool_calls", 0) == 0,
    "single_time": lambda text, m: bool(CLOCK_PATTERN.search(text)),
    "single_calc": lambda text, m: "210" in text,
    "multi_tool": lambda text, m: (
        "391" in text
        and bool(CLOCK_PATTERN.search(text))
        and ("上海" in text and any(word in text for word in ("阴", "17", "°", "天气")))
    ),
    "rag_advice": lambda text, m: (
        len(text) >= 80 and any(word in text for word in ("沟通", "安全感", "信任", "建议"))
    ),
    "code_compute": lambda text, m: "2550" in text and "16" in text,
    "skill_confession": lambda text, m: (
        100 <= len(text) <= 700
        and any(word in text for word in ("喜欢", "爱", "表白", "女朋友", "在一起", "做我"))
    ),
}


def _parse_events(chunks):
    final = ""
    meta = None
    for chunk in chunks:
        if chunk.startswith("[META]"):
            meta = json.loads(chunk[6:].strip())
        elif chunk.startswith("[FINAL]"):
            final = chunk[7:].strip()
    return final, meta


def _run_react(task):
    executor = create_agent(
        SYSTEM_PROMPT,
        middleware=[skill_middleware],
        extra_tools=BASE_TOOLS,
    )
    return _parse_events(stream_agent(executor, task["prompt"], None, ""))


def _run_multistep(engine, task):
    return _parse_events(
        stream_multistep_agent(engine, task["prompt"], SYSTEM_PROMPT)
    )


def _run_engine(engine, task):
    if engine == "react":
        return _run_react(task)
    return _run_multistep(engine, task)


def _warm_up():
    """Load embedding/reranker, MCP and each engine before measuring.

    The first RAG query can load a sentence-transformer model and the first
    weather call starts an MCP connection. Those costs would otherwise land on
    whichever task happens to run first.
    """
    tools = {tool.name: tool for tool in build_agent_tools()}
    try:
        tools["rag_search"].invoke({"query": "异地恋 沟通 安全感"})
    except Exception as exc:  # noqa: BLE001
        print(f"[warmup] rag_search failed: {exc}", flush=True)
    try:
        tools["get_now_weather"].invoke({"location": "上海"})
    except Exception as exc:  # noqa: BLE001
        print(f"[warmup] weather failed: {exc}", flush=True)

    warm_task = {"prompt": "只回复 OK 两个字，不要调用任何工具。"}
    for engine in ("react", "toolcalling", "code"):
        try:
            _run_engine(engine, warm_task)
        except Exception as exc:  # noqa: BLE001
            print(f"[warmup] engine {engine} failed: {exc}", flush=True)


def _median(values):
    return statistics.median(values) if values else None


def _summarize(runs):
    successful = [run for run in runs if run["success"]]
    # Performance medians include every completed run, including a run whose
    # answer failed a quality check: a failed attempt still costs tokens/time.
    completed = [run for run in runs if run["error"] is None and run["steps"] is not None]
    numeric = completed or runs
    return {
        "runs": len(runs),
        "success": len(successful),
        "success_rate": round(len(successful) / len(runs), 3) if runs else 0,
        "steps_median": _median([r["steps"] for r in numeric]) if numeric else None,
        "tool_calls_median": _median([r["tool_calls"] for r in numeric]) if numeric else None,
        "tokens_median": _median([r["total_tokens"] for r in numeric]) if numeric else None,
        "time_ms_median": _median([r["duration_ms"] for r in numeric]) if numeric else None,
        "answer_chars_median": _median([r["answer_chars"] for r in numeric]) if numeric else None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3, help="runs per engine/task")
    parser.add_argument(
        "--tasks",
        default=",".join(task["id"] for task in TASKS),
        help="comma-separated task ids",
    )
    parser.add_argument("--engines", default="react,toolcalling,code")
    parser.add_argument(
        "--out",
        default=str(ROOT.parent / "docs" / "dev" / "agent-benchmark-latest.json"),
    )
    parser.add_argument("--no-warmup", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    requested_tasks = set(args.tasks.split(","))
    tasks = [task for task in TASKS if task["id"] in requested_tasks]
    engines = [engine.strip() for engine in args.engines.split(",") if engine.strip()]

    if not args.no_warmup:
        print("Warming up tools and engines...", flush=True)
        _warm_up()

    payload = {
        "meta": {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "model": Config.MULTISTEP_MODEL,
            "temperature": Config.MULTISTEP_TEMPERATURE,
            "max_steps": Config.MULTISTEP_MAX_STEPS,
            "runs_per_task": args.runs,
            "prompt_version": "project-adapted-v2",
            "system_prompt": SYSTEM_PROMPT,
            "note": "Metrics come from each engine's [META] event; duration excludes browser/DB.",
        },
        "tasks": tasks,
        "results": {},
    }

    for task in tasks:
        payload["results"][task["id"]] = {}
        for engine in engines:
            runs = []
            print(f"\n=== {task['id']} / {engine} ===", flush=True)
            for index in range(1, args.runs + 1):
                wall_start = time.time()
                error = None
                final, meta = "", None
                try:
                    final, meta = _run_engine(engine, task)
                except Exception as exc:  # noqa: BLE001
                    error = f"{type(exc).__name__}: {exc}"
                    print(f"[run {index}] ERROR {error}", flush=True)

                wall_ms = int((time.time() - wall_start) * 1000)
                metrics = meta or {}
                answer_chars = len(final or "")
                total_tokens = (
                    int(metrics.get("prompt_tokens", 0))
                    + int(metrics.get("completion_tokens", 0))
                )
                success = False
                if error is None and final:
                    check = ANSWER_CHECKS.get(task["id"])
                    success = bool(check(final, metrics)) if check else True
                run = {
                    "task_id": task["id"],
                    "category": task["category"],
                    "engine": engine,
                    "run": index,
                    "success": success,
                    "error": error,
                    "answer": final,
                    "answer_chars": answer_chars,
                    "steps": metrics.get("steps"),
                    "tool_calls": metrics.get("tool_calls"),
                    "tool_errors": metrics.get("tool_errors", 0),
                    "prompt_tokens": metrics.get("prompt_tokens"),
                    "completion_tokens": metrics.get("completion_tokens"),
                    "total_tokens": total_tokens,
                    "duration_ms": metrics.get("duration_ms"),
                    "wall_ms": wall_ms,
                }
                runs.append(run)
                print(
                    f"[run {index}] success={success} steps={run['steps']} "
                    f"tools={run['tool_calls']} tokens={run['total_tokens']} "
                    f"time={run['duration_ms']}ms chars={answer_chars}",
                    flush=True,
                )
            payload["results"][task["id"]][engine] = {
                "runs": runs,
                "summary": _summarize(runs),
            }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== SUMMARY (median, successful runs) ===", flush=True)
    print("task\tengine\tsuccess\tsteps\ttools\ttokens\ttime_ms", flush=True)
    for task in tasks:
        for engine in engines:
            summary = payload["results"][task["id"]][engine]["summary"]
            print(
                f"{task['id']}\t{engine}\t{summary['success']}/{summary['runs']}\t"
                f"{summary['steps_median']}\t{summary['tool_calls_median']}\t"
                f"{summary['tokens_median']}\t{summary['time_ms_median']}",
                flush=True,
            )
    print(f"\nRaw results: {out_path}", flush=True)


if __name__ == "__main__":
    main()
