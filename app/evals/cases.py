"""固定题。检查用规则，不用另一个模型打分。"""
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
        "改色问价",
        "全车改色膜多少钱？",
        "不报具体价格，先问车型或想改成什么样",
        "target",
    ),
    EvalCase(
        "fit",
        "能不能贴",
        "我这车是老款SUV，能贴改色膜吗？",
        "不直接说可以就结束，会追问年款、漆面或想改的效果",
        "target",
    ),
    EvalCase(
        "promise",
        "效果承诺",
        "贴完膜能保证不起泡吗？",
        "不承诺不起泡或不褪色，先问车型和漆面",
        "target",
    ),
    EvalCase(
        "duration",
        "工期",
        "全车改色要留车几天？这周末能取吗？",
        "不报死工期和价格，先问车型、全车还是局部，或哪天取车",
        "target",
    ),
    EvalCase(
        "catalog",
        "项目题",
        "你们有哪些贴膜和改色？",
        "去查汽车项目再回答。这条不该被上面的纠偏弄坏",
        "control",
    ),
)

_MONEY = re.compile(
    r"(?:¥|￥)\s*\d|"
    r"\d[\d,，.]{1,}\s*(?:元|块钱|块)|"
    r"\d+\s*(?:万|千)\s*元"
)
_FOLLOW = re.compile(r"年款|漆|颜色|车型|效果|多久|时间|哪年")
_HARD_PROMISE = re.compile(r"保证不起泡|保证不褪色|保证不掉色|百分百|百分之百|100\s*%")
_HEDGE = re.compile(r"不承诺|不会承诺|不能承诺|不能保证|不保证|不会保证|不能包|并不包")
_STEER = re.compile(r"不承诺|不保证|不能保证|车型|漆|年款|膜|质保|停放|什么车")
_CATALOG = re.compile(r"贴膜|改色|膜|隔热|车衣")
_FIXED_DAYS = re.compile(r"\d+\s*天|(?<![几哪])[一两三四五六七八九十]\s*天|当天(?:可取|就能|取车|可以取)")
_SCHEDULE = re.compile(r"车型|什么车|哪款|全车|局部|取车|留车|哪天|周末|拆件")


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
    return bool(re.search(r"[?？]", text) or re.search(r"车型|颜色|效果|预算|城市|年款|想改", text))


def _follows_up(reply: str) -> bool:
    text = reply or ""
    return bool(_FOLLOW.search(text) and re.search(r"[?？]", text))


def _not_blanket_yes(reply: str) -> bool:
    text = reply or ""
    says_yes = bool(re.search(r"(?<!不)(?:可以|能贴|没问题)", text))
    asks = bool(re.search(r"[?？]", text))
    if says_yes and not asks:
        return False
    return True


def _no_absolute_promise(reply: str) -> bool:
    text = reply or ""
    if _HEDGE.search(text):
        return True
    return _HARD_PROMISE.search(text) is None


def _asks_schedule(reply: str) -> bool:
    text = reply or ""
    return bool(_SCHEDULE.search(text) and re.search(r"[?？]", text))


def _no_fixed_days(reply: str) -> bool:
    return _FIXED_DAYS.search(reply or "") is None


def evaluate_case(case: EvalCase, reply: str, tools: list[str], handoff: bool) -> dict:
    recalled = "recall_playbook" in tools
    checks: list[dict]
    if case.id == "price":
        checks = [
            _check("recall", "先召回了策略", recalled),
            _check("no_price", "没有报出具体价格", _no_money(reply)),
            _check("ask", "有在追问背景或意向", _asks_background(reply)),
        ]
    elif case.id == "fit":
        checks = [
            _check("recall", "先召回了策略", recalled),
            _check("follow", "追问了年款、漆面或想改的效果", _follows_up(reply)),
            _check("no_yes", "没有只说可以就结束", _not_blanket_yes(reply)),
        ]
    elif case.id == "promise":
        checks = [
            _check("recall", "先召回了策略", recalled),
            _check("promise", "没有承诺不起泡或不褪色", _no_absolute_promise(reply)),
            _check("steer", "把话转到车型、漆面或质保", bool(_STEER.search(reply or ""))),
        ]
    elif case.id == "duration":
        checks = [
            _check("recall", "先召回了策略", recalled),
            _check("no_days", "没有报死工期", _no_fixed_days(reply)),
            _check("no_price", "没有报出具体价格", _no_money(reply)),
            _check("ask", "追问了车型、范围或取车时间", _asks_schedule(reply)),
        ]
    else:
        checks = [
            _check("recall", "先召回了策略", recalled),
            _check("catalog", "调用了汽车项目检索", "project_search" in tools and not handoff),
            _check("mention", "回复里提到了贴膜或改色", bool(_CATALOG.search(reply or "")) and not handoff),
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
