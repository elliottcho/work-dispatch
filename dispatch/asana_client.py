from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests


ASANA_BASE = "https://app.asana.com/api/1.0"


@dataclass
class AsanaProject:
    gid: str
    name: str


class AsanaClient:
    def __init__(self, token: str | None = None) -> None:
        token = token or os.environ.get("ASANA_ACCESS_TOKEN")
        if not token:
            raise ValueError("ASANA_ACCESS_TOKEN is required for Asana sync")
        self._session = requests.Session()
        self._session.headers.update(
            {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        )

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = self._session.get(f"{ASANA_BASE}{path}", params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        resp = self._session.post(
            f"{ASANA_BASE}{path}",
            json={"data": data},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def list_projects(self, workspace_gid: str) -> list[AsanaProject]:
        payload = self._get(
            "/projects",
            params={"workspace": workspace_gid, "limit": 100, "archived": "false"},
        )
        return [AsanaProject(gid=p["gid"], name=p["name"]) for p in payload.get("data", [])]

    def find_project_by_name(self, workspace_gid: str, name: str) -> AsanaProject | None:
        target = name.strip().lower()
        for project in self.list_projects(workspace_gid):
            if project.name.strip().lower() == target:
                return project
        return None

    def create_task(
        self,
        *,
        name: str,
        notes: str,
        project_gid: str,
        due_on: str | None = None,
    ) -> str:
        data: dict[str, Any] = {
            "name": name,
            "notes": notes,
            "projects": [project_gid],
        }
        if due_on:
            data["due_on"] = due_on
        payload = self._post("/tasks", data)
        return payload["data"]["gid"]
