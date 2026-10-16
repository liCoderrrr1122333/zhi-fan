"""案例查询工具:按城市/背景检索成功案例(mock 数据)。

当策略要求"已了解客户情况后给出具体案例"时,由 Agent 调用它拿到真实案例数据,
避免笼统地空谈"我们有很多案例"。
"""
from __future__ import annotations
from typing import Any

from .base import Tool
from ...data.cases import all_cases


class OwnerCasesTool(Tool):
    name = "owner_cases"
    description = ("按城市或车况(车型、年款、贴膜、改色、车衣)检索车主案例,返回具体案例"
                   "(姓名、城市、车况、结果)。当需要用真实案例给客户信心时调用。")

    def run(self, query: str = "", **kwargs: Any) -> dict[str, Any]:
        q = (query or "").lower()
        hits = [c for c in all_cases()
                if any(k.lower() in q for k in c.get("keywords", []))]
        if not hits:
            hits = all_cases()[:3]
        cases = [{"name": c["name"], "city": c["city"],
                  "background": c["background"], "outcome": c["outcome"]} for c in hits[:4]]
        return {"count": len(cases), "cases": cases}
