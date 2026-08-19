#!/usr/bin/env python3
"""Small stdio MCP bridge for one MistakeMate account.

Run this on the machine that runs Hermes, not inside the MistakeMate container.
It intentionally exposes only study and print-preparation actions.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

BASE_URL = os.environ.get("MISTAKEMATE_URL", "http://127.0.0.1:8080").rstrip("/")
ACCESS_TOKEN = os.environ.get("MISTAKEMATE_TOKEN", "").strip()


def api(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    if not ACCESS_TOKEN:
        raise RuntimeError("未设置 MISTAKEMATE_TOKEN。请先在 MistakeMate 的账户设置中创建 Hermes 令牌。")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = Request(
        f"{BASE_URL}{path}",
        data=body,
        method=method,
        headers={"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(detail).get("detail", detail)
        except json.JSONDecodeError:
            pass
        raise RuntimeError(f"MistakeMate 返回 {error.code}：{detail}") from error
    except URLError as error:
        raise RuntimeError(f"无法连接 MistakeMate：{error.reason}") from error


TOOLS = [
    {
        "name": "list_today_tasks",
        "description": "读取当前账户的今日复练题、完成进度、正确率和每题优先原因。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_question",
        "description": "读取一题已确认错题的题干、选项、知识点与练习历史。",
        "inputSchema": {"type": "object", "properties": {"question_id": {"type": "string"}}, "required": ["question_id"]},
    },
    {
        "name": "mark_attempt",
        "description": "记录本次练习结果。只能传 correct 或 incorrect；会影响之后的复习优先级。",
        "inputSchema": {
            "type": "object",
            "properties": {"question_id": {"type": "string"}, "result": {"type": "string", "enum": ["correct", "incorrect"]}},
            "required": ["question_id", "result"],
        },
    },
    {
        "name": "prepare_print",
        "description": "校验题目并生成 MistakeMate 打印工作台链接。该工具不会发出实体打印，必须由用户在已登录浏览器预览并确认。",
        "inputSchema": {"type": "object", "properties": {"question_id": {"type": "string"}}, "required": ["question_id"]},
    },
]


def call_tool(name: str, arguments: dict[str, Any]) -> Any:
    if name == "list_today_tasks":
        return api("GET", "/api/integrations/hermes/tasks/today")
    if name == "get_question":
        return api("GET", f"/api/integrations/hermes/questions/{quote(str(arguments['question_id']), safe='')}")
    if name == "mark_attempt":
        return api("POST", f"/api/integrations/hermes/questions/{quote(str(arguments['question_id']), safe='')}/attempts", {"result": arguments["result"]})
    if name == "prepare_print":
        question = api("GET", f"/api/integrations/hermes/questions/{quote(str(arguments['question_id']), safe='')}")
        return {
            "question_id": arguments["question_id"],
            "title": f"{question['subject']} · 第 {question['question']['position']} 题",
            "print_workspace_url": f"{BASE_URL}/?print={quote(str(arguments['question_id']), safe='')}",
            "notice": "请在已登录的 MistakeMate 浏览器中打开此链接，核对纸张和模板后，由用户明确确认再点击打印。",
        }
    raise RuntimeError(f"未知工具：{name}")


def send(message: dict[str, Any]) -> None:
    encoded = json.dumps(message, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(encoded)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        key, _, value = line.decode("ascii", errors="replace").partition(":")
        headers[key.lower()] = value.strip()
    size = int(headers.get("content-length", "0"))
    if size <= 0:
        return None
    return json.loads(sys.stdin.buffer.read(size).decode("utf-8"))


def main() -> None:
    while message := read_message():
        request_id = message.get("id")
        method = message.get("method")
        if method == "notifications/initialized":
            continue
        if method == "initialize":
            result: Any = {"protocolVersion": message.get("params", {}).get("protocolVersion", "2024-11-05"), "capabilities": {"tools": {}}, "serverInfo": {"name": "mistakemate-hermes", "version": "0.1.0"}}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            try:
                params = message.get("params", {})
                result = {"content": [{"type": "text", "text": json.dumps(call_tool(params.get("name", ""), params.get("arguments", {})), ensure_ascii=False)}]}
            except (RuntimeError, KeyError, TypeError) as error:
                result = {"content": [{"type": "text", "text": str(error)}], "isError": True}
        else:
            if request_id is None:
                continue
            send({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Unknown method: {method}"}})
            continue
        if request_id is not None:
            send({"jsonrpc": "2.0", "id": request_id, "result": result})


if __name__ == "__main__":
    main()
