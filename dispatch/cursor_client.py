from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests


API_BASE = "https://api.cursor.com/v1"


@dataclass
class AgentSummary:
    id: str
    name: str
    status: str
    url: str | None
    env_type: str | None


class CursorClient:
    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or os.environ.get("CURSOR_API_KEY")
        if not key:
            raise ValueError("CURSOR_API_KEY is required for Cursor API calls")
        self._session = requests.Session()
        self._session.auth = (key, "")

    def list_agents(self, limit: int = 50) -> list[AgentSummary]:
        resp = self._session.get(f"{API_BASE}/agents", params={"limit": limit}, timeout=30)
        resp.raise_for_status()
        items = resp.json().get("items", [])
        return [
            AgentSummary(
                id=item["id"],
                name=item.get("name", ""),
                status=item.get("status", ""),
                url=item.get("url"),
                env_type=(item.get("env") or {}).get("type"),
            )
            for item in items
        ]

    def create_agent(
        self,
        *,
        prompt_text: str,
        repo_url: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "prompt": {"text": prompt_text},
            "model": {"id": "composer-2.5"},
        }
        if repo_url:
            body["repos"] = [{"url": repo_url, "startingRef": "main"}]
        if name:
            body["name"] = name
        resp = self._session.post(f"{API_BASE}/agents", json=body, timeout=60)
        resp.raise_for_status()
        return resp.json()

    def send_followup(self, agent_id: str, prompt_text: str) -> dict[str, Any]:
        resp = self._session.post(
            f"{API_BASE}/agents/{agent_id}/runs",
            json={"prompt": {"text": prompt_text}},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()


def try_sdk_send(agent_id: str, prompt_text: str, cwd: str) -> dict[str, Any] | None:
    """Use cursor-sdk for local agents when installed (Python 3.10+)."""
    try:
        from cursor_sdk import Agent, AgentOptions  # type: ignore
    except ImportError:
        return None

    with Agent.resume(agent_id, AgentOptions(api_key=os.environ.get("CURSOR_API_KEY"))) as agent:
        run = agent.send(prompt_text)
        result = run.wait()
        return {"agent_id": agent.agent_id, "run_id": result.id, "status": result.status}
