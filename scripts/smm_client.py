#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: scripts/smm_client.py
描述: SMM (上海有色网) MCP HTTP JSON-RPC 客户端封装
"""

import json
import urllib.request
import urllib.error


class SmmMcpClient:
    """SMM MCP 客户端封装"""

    def __init__(self, api_key: str):
        self.url = "https://datapromcp.smm.cn/mcp"
        self.api_key = api_key
        self.session_id = None
        self.req_id = 0

    def _call(self, method: str, params: dict = None):
        self.req_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self.req_id,
            "method": method,
            "params": params or {}
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "api_key": self.api_key,
            "User-Agent": "Antigravity-Client/1.0"
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id

        req = urllib.request.Request(self.url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                if "Mcp-Session-Id" in resp.headers:
                    self.session_id = resp.headers["Mcp-Session-Id"]
                content = resp.read().decode("utf-8")
                return json.loads(content)
        except urllib.error.HTTPError as e:
            return {"error": {"code": e.code, "message": e.read().decode("utf-8")}}
        except Exception as e:
            return {"error": {"message": str(e)}}

    def initialize(self):
        """初始化 MCP 会话"""
        return self._call("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "antigravity", "version": "1.0.0"}
        })

    def call_tool(self, name: str, arguments: dict):
        """调用 SMM MCP 工具"""
        res = self._call("tools/call", {"name": name, "arguments": arguments})
        content = res.get("result", {}).get("content", [])
        text_payload = ""
        for c in content:
            if c.get("type") == "text":
                text_payload += c.get("text", "")
        try:
            return json.loads(text_payload)
        except Exception:
            return text_payload
