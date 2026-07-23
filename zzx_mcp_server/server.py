# mcp_http_server.py
import httpx
import os
import logging
from fastmcp import FastMCP

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建 MCP 实例
mcp = FastMCP("ZZX_MCP_SERVER")

# ---------- 工具定义 ----------
@mcp.tool()
async def get_weather(location: str) -> dict:
    """
   查询指定位置的实时天气信息

   Args:
       location: 所查询的位置，支持城市名（如"上海"）、城市拼音（如"shanghai"）、
                 经纬度（如"31.23:121.47"）等

   Returns:
       包含实时天气信息的字典，包括温度、天气现象、更新时间等
    """
    logger.info(f"Weather query: {location}")
    url = "https://api.seniverse.com/v3/weather/now.json"
    params = {
        "key": "S6RhdAuuJQduDCSig",          # 建议改为环境变量
        "location": location,
        "language": "zh-Hans",
        "unit": "c",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

    if data.get("results"):
        result = data["results"][0]
        location_info = result.get("location", {})
        now = result.get("now", {})
        return {
            "location": location_info.get("name", "未知"),
            "country": location_info.get("country", "未知"),
            "weather": now.get("text", "未知"),
            "temperature": now.get("temperature", "未知"),
            "last_update": result.get("last_update", "未知"),
            "raw": data,
        }
    return {"error": "未获取到天气数据", "raw": data}

# ---------- 启动服务器 ----------
if __name__ == "__main__":
    # mcp.run(transport="sse")
    # 关键修改：transport 改为 streamable-http，并显式指定 host/port/路径
    mcp.run(
        transport="streamable-http",
        host="127.0.0.1",      # 监听地址
        port=8000,             # 端口
        path="/mcp"            # MCP 端点路径，客户端需要精确匹配
    )