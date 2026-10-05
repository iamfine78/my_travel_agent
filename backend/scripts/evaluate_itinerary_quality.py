# ============================================
# 行程质量评估（evaluate_itinerary_quality.py）
# 职责：对一次真实生成的行程做端到端量化评估
# 指标：
#   结构完整性   ：天数一致 / 三时段非空率 / summary·tips·budget_split 存在 /
#                  play_guide 覆盖率 / lodging 覆盖率
#   预算合理性   ：budget_split 五项之和 vs 总预算偏差（≤15% 满分）
#   景点覆盖率   ：每天平均景点数
#   天气一致性   ：预报有雨/雪/高温时，tips 是否包含对应提醒
#   偏好满足度   ：用户偏好关键词（美食/夜景/轻松…）在行程文本中的命中率
# 用法：
#   python backend/scripts/evaluate_itinerary_quality.py --city 西安 --days 2 --budget 800 --preferences "美食、夜景、轻松"
# ============================================
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from app.api.main import app

SLOTS = ("morning", "afternoon", "evening")


def parse_cost(c) -> float:
    """cost 可能是数字或"成人120元"这类描述：提取第一个数字。"""
    if isinstance(c, (int, float)):
        return float(c)
    m = re.search(r"\d+(?:\.\d+)?", str(c or ""))
    return float(m.group()) if m else 0.0


def all_activities(itin: dict) -> list[dict]:
    acts = []
    for d in itin.get("days", []):
        for s in SLOTS:
            acts.extend(d.get(s, []))
    return acts


def itinerary_text(itin: dict) -> str:
    """行程全文（用于偏好词命中检查）。"""
    parts = [itin.get("summary", ""), itin.get("destination", "")]
    parts.extend(itin.get("tips", []))
    for d in itin.get("days", []):
        parts.append(d.get("lodging", ""))
        parts.append(d.get("note", ""))
        parts.extend(d.get("meals", []))
        for a in all_activities(itin):
            parts.extend([a.get("place", ""), a.get("description", ""), a.get("play_guide", "")])
    return "\n".join(parts)


def evaluate(itin: dict, weather: dict, req_days: int, req_budget: float, preferences: str) -> dict:
    scores = {}
    detail = {}

    # 1) 结构完整性
    days = itin.get("days", [])
    detail["day_count_ok"] = len(days) == req_days
    slots_ok = 0
    slots_total = 0
    for d in days:
        for s in SLOTS:
            slots_total += 1
            if d.get(s):
                slots_ok += 1
    detail["slots_fill"] = f"{slots_ok}/{slots_total}"
    acts = all_activities(itin)
    play_ok = sum(1 for a in acts if a.get("play_guide"))
    lodging_ok = sum(1 for d in days if d.get("lodging"))
    detail["play_guide_coverage"] = f"{play_ok}/{len(acts)}"
    detail["lodging_coverage"] = f"{lodging_ok}/{len(days)}"
    has_basic = bool(itin.get("summary")) and bool(itin.get("tips")) and bool(itin.get("budget_split"))
    detail["has_basic"] = has_basic
    # 评分（满分 100，各要素加权）
    s1 = 0
    s1 += 20 if detail["day_count_ok"] else 0
    s1 += 20 * (slots_ok / max(slots_total, 1))
    s1 += 15 * (play_ok / max(len(acts), 1))
    s1 += 15 * (lodging_ok / max(len(days), 1))
    s1 += 30 if has_basic else 0
    scores["structure"] = round(s1, 1)

    # 2) 预算合理性：budget_split 之和 vs 总预算偏差
    bs = itin.get("budget_split", {})
    keys = ("transport", "lodging", "food", "tickets", "other")
    total = sum(parse_cost(bs.get(k, 0)) for k in keys)
    deviation = abs(total - req_budget) / req_budget * 100 if req_budget else 100
    detail["budget_sum"] = f"{total:.0f} vs {req_budget:.0f}（偏差 {deviation:.0f}%）"
    scores["budget"] = 100 if deviation <= 15 else max(0, 100 - deviation)

    # 3) 景点覆盖率：每天平均景点数（3~8 视为合理）
    per_day = [len([a for s in SLOTS for a in d.get(s, [])]) for d in days] or [0]
    avg = sum(per_day) / len(per_day)
    detail["spots_per_day"] = f"{avg:.1f} 个/天"
    scores["coverage"] = 100 if 3 <= avg <= 8 else max(0, 100 - abs(avg - 5) * 15)

    # 4) 天气一致性：预报有雨/雪/高温 → tips 有对应提醒
    forecasts = (weather or {}).get("forecasts", [])
    tips_text = "\n".join(itin.get("tips", []))
    weather_ok = True
    for cast in forecasts[:3]:
        w = cast.get("dayweather", "")
        if "雨" in w and "雨" not in tips_text:
            weather_ok = False
        elif "雪" in w and "雪" not in tips_text:
            weather_ok = False
        elif "晴" in w and int(cast.get("daytemp", 0) or 0) >= 30 and "高温" not in tips_text:
            weather_ok = False
    detail["weather_aligned"] = weather_ok
    scores["weather"] = 100 if weather_ok else 50

    # 5) 偏好满足度：偏好关键词在行程全文的命中率
    text = itinerary_text(itin)
    prefs = [p for p in re.split(r"[,，、;；\s]+", preferences or "") if p]
    hit = sum(1 for p in prefs if p in text)
    detail["pref_hit"] = f"{hit}/{len(prefs)}（{prefs}）"
    scores["preference"] = round(100 * hit / max(len(prefs), 1), 1)

    # 总分（结构40 + 预算20 + 覆盖15 + 天气10 + 偏好15）
    total_score = (
        scores["structure"] * 0.4
        + scores["budget"] * 0.2
        + scores["coverage"] * 0.15
        + scores["weather"] * 0.10
        + scores["preference"] * 0.15
    )
    return {"scores": scores, "total": round(total_score, 1), "detail": detail}


def main():
    parser = argparse.ArgumentParser(description="行程质量量化评估")
    parser.add_argument("--city", default="西安")
    parser.add_argument("--days", type=int, default=2)
    parser.add_argument("--budget", type=float, default=800)
    parser.add_argument("--preferences", default="美食、夜景、轻松")
    args = parser.parse_args()

    print(f"评估 {args.city} {args.days} 天（预算 {args.budget}，偏好: {args.preferences}）…")
    client = TestClient(app)
    r = client.post("/api/trip/plan", json={
        "destination": args.city,
        "days": args.days,
        "budget": args.budget,
        "preferences": args.preferences,
    })
    if r.status_code != 200:
        print(f"生成失败: {r.status_code} {r.text[:300]}")
        sys.exit(1)
    body = r.json()
    itin, weather = body["itinerary"], body.get("weather")

    result = evaluate(itin, weather, args.days, args.budget, args.preferences)
    print("\n指标明细:")
    for k, v in result["detail"].items():
        print(f"  {k:<20} {v}")
    print("\n得分:")
    for k, v in result["scores"].items():
        print(f"  {k:<10} {v}")
    print(f"\n总分: {result['total']} / 100")
    print(f"本次 token: {body.get('token_usage', {})}")


if __name__ == "__main__":
    main()
