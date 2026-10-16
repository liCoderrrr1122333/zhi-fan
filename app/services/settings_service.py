"""业务设定:人工可在工作台维护的『全局人设 + 语气 + 铁律』,会注入系统提示词。

这是与"逐条策略样本"不同的一层——承载全局策略(简洁、绝不直接报价等),
这类硬规则不适合靠逐条样本归纳,由由人工直接维护更可靠。
"""
from __future__ import annotations

from ..db import cursor

_KEY = "business_directive"
_SUMMARY_KEY = "playbook_summary"


def _get(key: str, default: str = "") -> str:
    with cursor() as cur:
        cur.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = cur.fetchone()
    return row["value"] if row else default


def _set(key: str, value: str) -> None:
    with cursor() as cur:
        cur.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

DEFAULT_DIRECTIVE = (
    "【语气】回复简洁口语化,一次一般不超过 2-3 句;先回应重点,别长篇大论、别堆砌。\n"
    "【铁律】\n"
    "1. 绝不主动报出具体价格数字。客户问价时,不要直接给价格。\n"
    "2. 面对询价:先问车型、年款,以及是贴膜、改色还是车衣,不要急着推进。\n"
    "3. 客户表达出明确意向后,不要自己谈价,而是引导他跟顾问一对一对接"
    "(由顾问谈价格与优惠)。\n"
    "4. 任何时候都遵循策略库中已有的策略,信息不足先挖掘需求。"
)


def get_directive() -> str:
    return _get(_KEY, DEFAULT_DIRECTIVE)


def set_directive(text: str) -> dict:
    _set(_KEY, text)
    return {"ok": True}


def get_summary() -> str:
    """已保存的策略总纲(可能被人工手动改写过);空串表示还没生成过。"""
    return _get(_SUMMARY_KEY, "")


def set_summary(text: str) -> dict:
    _set(_SUMMARY_KEY, text)
    return {"ok": True}
