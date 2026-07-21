# mcp_tools.py
import asyncio
from typing import List, Any
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.tools import StructuredTool
import json

_tools = None
_initialized = False

def _make_sync_tool(async_tool) -> StructuredTool:
    """
    将 MCP 异步工具包装为同步工具（带超时和独立事件循环）。
    即使换成 streamable-http，工具仍然是异步的，此包装依然必要。
    """
    async def async_wrapper(**kwargs):
        return await async_tool.ainvoke(kwargs)

    def sync_func(**kwargs):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                asyncio.wait_for(async_wrapper(**kwargs), timeout=30.0)
            )
        finally:
            loop.close()

    return StructuredTool(
        name=async_tool.name,
        description=async_tool.description,
        args_schema=async_tool.args_schema,
        func=sync_func,
        coroutine=async_wrapper,
    )

def _load_tools_sync() -> List[Any]:
    """同步加载 MCP 工具（内部使用）"""
    client = MultiServerMCPClient({
        "weather_service": {
            "transport": "streamable_http",          # ← 改为 streamable_http
            "url": "http://127.0.0.1:8000/mcp",     # ← 指向服务器 path 端点
        }
    })
    async_tools = asyncio.run(client.get_tools())
    return [_make_sync_tool(t) for t in async_tools]

def get_mcp_tools() -> List[Any]:
    global _tools, _initialized
    if not _initialized:
        _tools = _load_tools_sync()
        _initialized = True
    return _tools

# ---------- 测试工具可用性（仅当直接运行此文件时执行） ----------
if __name__ == "__main__":
    print("🔍 正在加载 MCP 工具...")
    tools = get_mcp_tools()
    print(f"✅ 成功加载 {len(tools)} 个工具:")
    for t in tools:
        print(f"  - {t.name}")

    # 测试 get_weather 工具（如果存在）
    weather_tool = next((t for t in tools if t.name == "get_weather"), None)
    if weather_tool:
        print("\n🌤️ 测试 get_weather 工具（查询保定天气）...")
        try:
            # 使用异步调用（工具是异步函数）
            result = asyncio.run(weather_tool.ainvoke({"location": "保定"}))
            print("✅ 工具调用成功，返回结果：")
            print(json.dumps(result, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"❌ 工具调用失败: {e}")
    else:
        print("\n⚠️ 未找到 get_weather 工具，跳过测试。")