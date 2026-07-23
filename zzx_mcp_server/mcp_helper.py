"""
MCP Helper — runs in zzx-mcp-server env (Python 3.11).
Uses official mcp library + langchain_mcp_adapters.
Outputs "READY\n" on stdout when ready.
Then reads JSON-RPC commands from stdin (binary, UTF-8).
"""

import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

_script_dir = os.path.dirname(os.path.abspath(__file__))
MCP_SERVER_SCRIPT = os.path.join(_script_dir, "server.py")


async def main():
    params = StdioServerParameters(
        command=sys.executable,
        args=[MCP_SERVER_SCRIPT],
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Signal readiness
            sys.stdout.buffer.write(b"READY\n")
            sys.stdout.buffer.flush()

            loop = asyncio.get_event_loop()

            while True:
                # Read from stdin (binary, UTF-8)
                line_bytes = await loop.run_in_executor(
                    None, sys.stdin.buffer.readline
                )
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8").strip()
                if not line:
                    continue

                try:
                    cmd = json.loads(line)
                except json.JSONDecodeError:
                    continue

                req_id = cmd.get("id")
                method = cmd.get("method")
                params = cmd.get("params", {})

                try:
                    if method == "tools/list":
                        result = await session.list_tools()
                        tools_data = []
                        for t in getattr(result, "tools", []):
                            tools_data.append({
                                "name": t.name,
                                "description": t.description,
                                "inputSchema": getattr(t, "inputSchema", {}),
                            })
                        _respond(req_id, {"tools": tools_data})

                    elif method == "tools/call":
                        name = params.get("name", "")
                        arguments = params.get("arguments", {})
                        call_result = await session.call_tool(name, arguments)
                        content = []
                        for item in getattr(call_result, "content", []):
                            if hasattr(item, "text"):
                                content.append({"type": "text", "text": item.text})
                            else:
                                content.append({"type": "text", "text": str(item)})
                        _respond(req_id, {"content": content})

                    else:
                        _respond(req_id, error=f"Unknown method: {method}")

                except Exception as e:
                    _respond(req_id, error=str(e))


def _respond(req_id, result=None, error=None):
    """Write JSON-RPC response (binary, UTF-8)."""
    resp = {"jsonrpc": "2.0", "id": req_id}
    if error:
        resp["error"] = {"code": -1, "message": str(error)}
    else:
        resp["result"] = result
    sys.stdout.buffer.write(
        (json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8")
    )
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        _respond(None, error=str(e))
        sys.exit(1)
