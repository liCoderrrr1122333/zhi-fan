"""评测闭环：固定四题，跑完和上一轮对比。评测不写咨询统计，也不留下工单。"""
from __future__ import annotations
import json
from typing import Any

from .. import config
from ..db import cursor
from ..evals.cases import CASES, case_by_id, evaluate_case, public_cases, tools_from_trace
from . import chat_service, playbook_service, settings_service


def _snapshot() -> dict[str, Any]:
    samples = playbook_service.list_samples()
    summary = (settings_service.get_summary() or "").strip().replace("\n", " ")
    return {
        "provider": config.LLM_PROVIDER,
        "sample_count": len(samples),
        "sample_ids": [s["id"] for s in samples],
        "summary_excerpt": summary[:80],
    }


def _loads(raw: str | None) -> list[dict]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _row_to_run(row: dict) -> dict[str, Any]:
    return {
        "id": row["id"],
        "status": row["status"],
        "created_at": row["created_at"],
        "provider": row["provider"],
        "sample_count": row["sample_count"],
        "summary_excerpt": row["summary_excerpt"] or "",
        "passed": row["passed"],
        "total": row["total"],
        "results": _loads(row["results_json"]),
    }


def _done_runs() -> list[dict]:
    with cursor() as cur:
        cur.execute("SELECT * FROM eval_runs WHERE status='done' ORDER BY id DESC")
        rows = [dict(r) for r in cur.fetchall()]
    return [_row_to_run(r) for r in rows]


def _has_model_error(results: list[dict]) -> bool:
    return any(item.get("error") for item in results or [])


def _scored_before(runs: list[dict], before_id: int | None) -> dict | None:
    """上一轮只取模型答完的评测。没答上的轮次不拿来比变好或退步。"""
    for run in runs:
        if before_id is not None and run["id"] >= before_id:
            continue
        if not _has_model_error(run.get("results") or []):
            return run
    return None


def _skipped_unscored(runs: list[dict], before_id: int | None, current_unscored: bool) -> bool:
    if current_unscored:
        return False
    for run in runs:
        if before_id is not None and run["id"] >= before_id:
            continue
        return _has_model_error(run.get("results") or [])
    return False


def delta_of(passed: bool, previous_passed: bool | None) -> str:
    if previous_passed is None:
        return "new"
    if passed and not previous_passed:
        return "improved"
    if previous_passed and not passed:
        return "regressed"
    if passed and previous_passed:
        return "held"
    return "still"


def _attach_delta(results: list[dict], previous: dict | None) -> list[dict]:
    if _has_model_error(results):
        return [dict(item, delta="") for item in results]
    prev_map = {item["id"]: item for item in (previous or {}).get("results") or []}
    out = []
    for item in results:
        before = prev_map.get(item["id"])
        copied = dict(item)
        copied["delta"] = delta_of(bool(item.get("passed")), None if before is None else bool(before.get("passed")))
        out.append(copied)
    return out


def build_headline(results: list[dict], previous: dict | None, passed: int, total: int) -> str:
    if any(item.get("error") for item in results):
        return "有题目没跑完，这轮不能当成策略成绩。模型接口恢复后再跑一遍。"
    if not previous:
        failed = [item["short"] for item in results if not item.get("passed")]
        if not failed:
            return f"当前策略 {passed}/{total} 题都通过。改一条策略后再跑，就能看见有没有被带坏。"
        return f"当前策略通过 {passed}/{total}。{'、'.join(failed)}还没过。改完策略再跑一遍，就能看见哪题变了。"
    prev_passed = previous.get("passed") or 0
    prev_total = previous.get("total") or len(previous.get("results") or [])
    prev_map = {item["id"]: item for item in previous.get("results") or []}
    improved, regressed, held_control = [], [], []
    for item in results:
        before = prev_map.get(item["id"])
        if not before:
            continue
        if item.get("passed") and not before.get("passed"):
            improved.append(item["short"])
        elif before.get("passed") and not item.get("passed"):
            regressed.append(item["short"])
        elif item.get("role") == "control" and item.get("passed") and before.get("passed"):
            held_control.append(item["short"])
    parts = [f"上一轮 {prev_passed}/{prev_total}，这一轮 {passed}/{total}。"]
    if improved:
        parts.append("、".join(improved) + "变好了。")
    if regressed:
        parts.append("、".join(regressed) + "退步了。")
    if held_control:
        parts.append("、".join(held_control) + "仍然通过。")
    if not improved and not regressed:
        parts.append("和上一轮一样，这四题的通过情况没有变。")
    return "".join(parts)


def _provider_note(provider: str) -> str:
    if provider == "mock":
        return "当前是离线桩。它会把查到的价格拼进回复，价格题会一直失败，不能用来证明策略变好。"
    return "这次用的是真实模型。同一句话可能有浮动，看的是规则过没过。"


_SKIPPED_NOTE = "上一轮模型没答上，不拿来对比。"


def overview() -> dict[str, Any]:
    done = _done_runs()
    latest = dict(done[0]) if done else None
    unscored = bool(latest and _has_model_error(latest.get("results") or []))
    previous = None if latest is None or unscored else _scored_before(done, latest["id"])
    if latest:
        latest["unscored"] = unscored
        latest["results"] = _attach_delta(latest["results"], previous)
    headline = "四道固定题。先跑一遍看当前策略，改完再跑，变好和被带坏都会标出来。"
    if latest:
        headline = build_headline(latest["results"], previous, latest["passed"], latest["total"])
    skipped = _skipped_unscored(done, None if latest is None else latest["id"], unscored)
    return {
        "cases": public_cases(),
        "provider": config.LLM_PROVIDER,
        "provider_note": _provider_note(config.LLM_PROVIDER),
        "latest": latest,
        "previous": previous,
        "headline": headline,
        "skipped_note": _SKIPPED_NOTE if skipped else "",
    }


def begin_run() -> dict[str, Any]:
    snap = _snapshot()
    with cursor() as cur:
        cur.execute("UPDATE eval_runs SET status='abandoned' WHERE status='running'")
        cur.execute(
            """
            INSERT INTO eval_runs
                (status, provider, sample_count, sample_ids, summary_excerpt, passed, total, results_json)
            VALUES ('running', ?, ?, ?, ?, 0, ?, '[]')
            """,
            (
                snap["provider"],
                snap["sample_count"],
                json.dumps(snap["sample_ids"]),
                snap["summary_excerpt"],
                len(CASES),
            ),
        )
        run_id = cur.lastrowid
    return {
        "id": run_id,
        "provider": snap["provider"],
        "provider_note": _provider_note(snap["provider"]),
        "sample_count": snap["sample_count"],
        "summary_excerpt": snap["summary_excerpt"],
        "cases": public_cases(),
    }


def _blank_failure(case, message: str) -> dict:
    return {
        "id": case.id,
        "short": case.short,
        "question": case.question,
        "expect": case.expect,
        "role": case.role,
        "reply": message,
        "tools": [],
        "handoff": False,
        "error": True,
        "checks": [{"key": "error", "label": "模型没有返回，这题未计入", "ok": False}],
        "passed": False,
    }


def run_case(run_id: int, case_id: str) -> dict[str, Any]:
    case = case_by_id(case_id)
    if case is None:
        return {"ok": False, "error": "没有这道题"}
    with cursor() as cur:
        cur.execute("SELECT * FROM eval_runs WHERE id=?", (run_id,))
        row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "这次评测不存在"}
    row = dict(row)
    if row["status"] != "running":
        return {"ok": False, "error": "这次评测已经结束"}

    session_id = f"eval:{run_id}:{case.id}"
    chat_service.reset_session(session_id)
    try:
        result = chat_service.handle_chat(case.question, session_id=session_id)
        if result.ticket_id:
            with cursor() as cur:
                cur.execute("DELETE FROM tickets WHERE id=?", (result.ticket_id,))
        judged = evaluate_case(
            case,
            result.reply or "",
            tools_from_trace(result.trace),
            bool(result.handoff),
        )
    except Exception:
        judged = _blank_failure(case, "模型这次没有答上，这题不计入成绩。")
    finally:
        chat_service.reset_session(session_id)

    results = _loads(row["results_json"])
    results = [item for item in results if item.get("id") != case.id]
    results.append(judged)
    order = {c.id: i for i, c in enumerate(CASES)}
    results.sort(key=lambda item: order.get(item.get("id"), 99))
    finished = len(results) >= len(CASES)
    passed = sum(1 for item in results if item.get("passed"))
    status = "done" if finished else "running"
    with cursor() as cur:
        cur.execute(
            "UPDATE eval_runs SET results_json=?, passed=?, total=?, status=? WHERE id=?",
            (json.dumps(results, ensure_ascii=False), passed, len(CASES), status, run_id),
        )

    done = _done_runs()
    unscored = _has_model_error(results)
    previous = None if unscored else _scored_before(done, run_id)
    judged = dict(judged)
    if unscored:
        judged["delta"] = ""
    else:
        prev_item = next((item for item in (previous or {}).get("results") or [] if item.get("id") == case.id), None)
        judged["delta"] = delta_of(
            bool(judged.get("passed")),
            None if prev_item is None else bool(prev_item.get("passed")),
        )
    headline = None
    if finished:
        headline = build_headline(results, previous, passed, len(CASES))
    return {
        "ok": True,
        "result": judged,
        "finished": finished,
        "passed": passed,
        "total": len(CASES),
        "headline": headline,
        "unscored": unscored,
        "skipped_note": "" if unscored or not _skipped_unscored(done, run_id, unscored) else _SKIPPED_NOTE,
        "sample_count": row["sample_count"],
        "summary_excerpt": row["summary_excerpt"] or "",
        "provider": row["provider"],
    }
