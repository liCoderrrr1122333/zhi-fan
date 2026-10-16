"""汽车项目检索:根据问题匹配贴膜、改色、车衣的客观信息。"""
from __future__ import annotations
from typing import Any

from .base import Tool
from ...data.projects import all_projects
from ...knowledge import embedding


class ProjectSearchTool(Tool):
    name = "project_search"
    description = "检索汽车项目目录,返回最相关的贴膜、改色或车衣(名称、价格、工期、适合什么车、内容、注意点)。"

    def run(self, query: str = "", **kwargs: Any) -> dict[str, Any]:
        qvec = embedding.embed(query)
        best = None
        best_score = 0.0
        for item in all_projects():
            text = " ".join([item["name"], item["category"], item["audience"],
                             item["content"], item["highlight"], " ".join(item.get("keywords", []))])
            score = embedding.cosine(qvec, embedding.embed(text))
            if score > best_score:
                best_score, best = score, item
        if best and best_score >= 0.06:
            return {"found": True, "score": round(best_score, 3),
                    "project": {k: best[k] for k in ("id", "name", "category", "price",
                                                     "duration", "audience", "content", "highlight")}}
        return {"found": False, "score": round(best_score, 3),
                "projects": [{"name": item["name"], "price": item["price"],
                              "audience": item["audience"]} for item in all_projects()]}
