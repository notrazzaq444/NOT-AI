"""Tool registry - schemas + implementations for local & web tools."""
from __future__ import annotations

import ast
import datetime as dt
import operator
import platform
import sys
from typing import Any, Callable
from zoneinfo import ZoneInfo

import httpx
from tavily import TavilyClient
from app.config.settings import get_settings

# ---------- Time Tool (Timezone-aware) ----------
def get_current_time(timezone: str = "UTC") -> str:
    try:
        if not timezone or timezone.lower() in ("local", "auto"):
            tz = dt.datetime.now().astimezone().tzinfo
        else:
            tz = ZoneInfo(timezone)
    except Exception as e:
        print(f"[TimeTool] Invalid timezone '{timezone}': {e}")
        tz = ZoneInfo("UTC")
    now = dt.datetime.now(tz)
    return now.strftime("%A, %d %B %Y, %I:%M:%S %p (%Z)")

# ---------- Math Tool ----------
_SAFE_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}

def _safe_eval(node):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("Only numbers allowed")
    if isinstance(node, ast.BinOp):
        return _SAFE_OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp):
        return _SAFE_OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError(f"Unsupported: {type(node).__name__}")

def calculate(expression: str) -> str:
    try:
        tree = ast.parse(expression, mode="eval")
        result = _safe_eval(tree.body)
        return f"{expression} = {result}"
    except Exception as e:
        return f"Error: {e}"

# ---------- System Info Tool ----------
def get_system_info() -> str:
    return f"OS: {platform.system()} {platform.release()}\nMachine: {platform.machine()}\nPython: {sys.version.split()[0]}\nHostname: {platform.node()}"

# ---------- Web Search Tool ----------
def search_web(query: str) -> str:
    settings = get_settings()
    if not settings.tavily_api_key:
        return "Error: Tavily API key missing."
    try:
        client = TavilyClient(api_key=settings.tavily_api_key)
        response = client.search(query=query, search_depth="advanced", max_results=5, include_answer=True)
        output = f"**Search Results for '{query}':**\n\n"
        if response.get("answer"):
            output += f"**Summary:** {response['answer']}\n\n"
        output += "**Sources:**\n"
        for i, result in enumerate(response.get("results", []), 1):
            output += f"{i}. {result.get('title', 'No title')}\n   URL: {result.get('url', 'No URL')}\n\n"
        return output
    except Exception as e:
        return f"Error searching web: {e}"

# ---------- Weather Tool ----------
def get_weather(city: str) -> str:
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=en&format=json"
        geo_data = httpx.get(geo_url, timeout=10).json()
        if not geo_data.get("results"):
            return f"Error: Could not find city '{city}'."
        lat = geo_data["results"][0]["latitude"]
        lon = geo_data["results"][0]["longitude"]
        country = geo_data["results"][0].get("country", "Unknown")
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,wind_speed_10m&timezone=auto"
        w = httpx.get(weather_url, timeout=10).json().get("current", {})
        return f"Weather in {city}, {country}:\nTemp: {w.get('temperature_2m')}°C\nHumidity: {w.get('relative_humidity_2m')}%\nWind: {w.get('wind_speed_10m')} km/h"
    except Exception as e:
        return f"Error fetching weather: {e}"

# ---------- News Tool ----------
def get_news(topic: str = "world") -> str:
    settings = get_settings()
    if not settings.tavily_api_key:
        return "Error: Tavily API key missing."
    try:
        client = TavilyClient(api_key=settings.tavily_api_key)
        response = client.search(query=f"latest news on {topic} today", search_depth="advanced", max_results=5, include_answer=True)
        output = f"**Latest News on '{topic}':**\n\n"
        if response.get("answer"):
            output += f"**Summary:** {response['answer']}\n\n"
        for i, result in enumerate(response.get("results", []), 1):
            output += f"{i}. {result.get('title')}\n   URL: {result.get('url')}\n\n"
        return output
    except Exception as e:
        return f"Error fetching news: {e}"

# ---------- Camera Tool (Special) ----------
def look_through_camera(prompt: str = "Describe what is visible in this image in detail.") -> str:
    # Yeh function trigger signal deta hai, asal kaam WebSocket karega
    return "CAMERA_REQUEST_TRIGGERED"

# ---------- Schema Registry ----------
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {"type": "function", "function": {"name": "get_current_time", "description": "Get current time in user's timezone.", "parameters": {"type": "object", "properties": {"timezone": {"type": "string"}}, "required": ["timezone"]}}},
    {"type": "function", "function": {"name": "calculate", "description": "Evaluate a math expression.", "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]}}},
    {"type": "function", "function": {"name": "get_system_info", "description": "Return system OS and info.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "search_web", "description": "Search the live internet for current information.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "get_weather", "description": "Get current weather for a city.", "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}},
    {"type": "function", "function": {"name": "get_news", "description": "Get latest news headlines.", "parameters": {"type": "object", "properties": {"topic": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "look_through_camera", "description": "Open the user's camera, capture an image, and analyze what is visible. Use this when the user asks you to 'look', 'see', 'check what is in front of me', or 'use the camera'.", "parameters": {"type": "object", "properties": {"prompt": {"type": "string", "description": "What to look for in the image."}}, "required": []}}},
]

TOOL_IMPLEMENTATIONS: dict[str, Callable[..., str]] = {
    "get_current_time": get_current_time,
    "calculate": calculate,
    "get_system_info": get_system_info,
    "search_web": search_web,
    "get_weather": get_weather,
    "get_news": get_news,
    "look_through_camera": look_through_camera,
}

def execute_tool(name: str, arguments: dict[str, Any]) -> str:
    fn = TOOL_IMPLEMENTATIONS.get(name)
    if fn is None:
        return f"Error: tool '{name}' not found."
    try:
        return fn(**arguments)
    except TypeError as e:
        return f"Error: bad args for '{name}': {e}"
    except Exception as e:
        return f"Error running '{name}': {e}"