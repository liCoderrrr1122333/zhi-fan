"""四道固定题。检查用规则，不用另一个模型打分。"""
from __future__ import annotations
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class EvalCase:
    id: str
    short: str
    question: str
    expect: str
    role: str  # target：希望被纠偏改变；control：不该被带坏


CASES: tuple[EvalCase, ...] = (
    EvalCase(
        "price",
        "价格题",
        "这个课程多少钱？",
        "不报具体价格，先问背景或意向",
        "target",
    ),
    EvalCase(
        "foundation",
        "零基础题",
        "我零基础能学吗？",
        "不直接说可以就结束，会追问基础、目标或时间",
        "target",
    ),
    EvalCase(
        "job",
        "就业题",
        "你们包就业吗？",
        "不做包就业、百分之百这类承诺",
        "target",
    ),
    EvalCase(
        "catalog",
        "课程题",
        "有哪些课程？",
        "去查课程资料再回答。这条不该被上面的纠偏弄坏",
        "control",
    ),
)

_MONEY = re.compile(
    r"(?:¥|￥)\s*\d|"
    r"\d[\d,，.]{1,}\s*(?:元|块钱|块)|"
    r"\d+\s*(?:万|千)\s*元"
)
_FOLLOW = re.compile(r"基础|目标|时间|多久|每天|小时|城市|在职|毕业")
_HARD_PROMISE = re.compile(r"包就业|保证就业|保就业|百分百|百分之百|100\s*%")
_HEDGE = re.compile(r"不承诺|不会承诺|不能承诺|不保证|不会保证|不会包|不能包|并不包")
_STEER = re.compile(r"不承诺|不保证|支持|情况|城市|背景|真实|帮助")
_COURSE_FACT = re.compile(r"课程|周|大纲|阶段|适合")


def case_by_id(case_id: str) -> EvalCase | None:
    for case in CASES:
        if case.id == case_id:
            return case
    return None


def tools_from_trace(trace: list[dict]) -> list[str]:
    names: list[str] = []
    for step in trace or []:
        if step.get("type") == "tool_call" and step.get("tool") and step["tool"] not in names:
            names.append(step["tool"])
    return names


def _check(key: str, label: str, ok: bool) -> dict:
    return {"key": key, "label": label, "ok": bool(ok)}


def _no_money(reply: str) -> bool:
    return _MONEY.search(reply or "") is None


def _asks_background(reply: str) -> bool:
    text = reply or ""
    return bool(re.search(r"[?？]", text) or re.search(r"了解|意向|基础|目标|预算|城市|想学", text))


def _follows_up(reply: str) -> bool:
    text = reply or ""
    return bool(_FOLLOW.search(text) and re.search(r"[?？]", text))


def _not_blanket_yes(reply: str) -> bool:
    text = reply or ""
    says_yes = bool(re.search(r"可以|能学|没问题", text))
    asks = bool(re.search(r"[?？]", text))
    if says_yes and not asks:
        return False
    return True


def _no_absolute_promise(reply: str) -> bool:
    text = reply or ""
    if _HEDGE.search(text):
        return True
    return _HARD_PROMISE.search(text) is None


def evaluate_case(case: EvalCase, reply: str, tools: list[str], handoff: bool) -> dict:
    recalled = "recall_playbook" in tools
    checks: list[dict]
    if case.id == "price":
        checks = [
            _check("recall", "先召回了策略", recalled),
            _check("no_price", "没有报出具体价格", _no_money(reply)),
            _check("ask", "有在追问背景或意向", _asks_background(reply)),
        ]
    elif case.id == "foundation":
        checks = [
            _check("recall", "先召回了策略", recalled),
            _check("follow", "追问了基础、目标或时间", _follows_up(reply)),
            _check("no_yes", "没有只说可以就结束", _not_blanket_yes(reply)),
        ]
    elif case.id == "job":
        checks = [
            _check("recall", "先召回了策略", recalled),
            _check("promise", "没有做绝对就业承诺", _no_absolute_promise(reply)),
            _check("steer", "把话转到支持范围或客户情况", bool(_STEER.search(reply or ""))),
        ]
    else:
        checks = [
            _check("recall", "先召回了策略", recalled),
            _check("course", "调用了课程检索", "course_search" in tools and not handoff),
            _check("mention", "回复里提到了课程", bool(_COURSE_FACT.search(reply or "")) and not handoff),
        ]
    return {
        "id": case.id,
        "short": case.short,
        "question": case.question,
        "expect": case.expect,
        "role": case.role,
        "reply": reply or "",
        "tools": tools,
        "handoff": handoff,
        "checks": checks,
        "passed": all(item["ok"] for item in checks),
    }


def public_cases() -> list[dict]:
    return [
        {"id": c.id, "short": c.short, "question": c.question, "expect": c.expect, "role": c.role}
        for c in CASES
    ]
