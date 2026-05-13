"""
2026-05-13 KBO 픽 — 수동 데이터 입력으로 predictor.py 로직 시뮬레이션

샌드박스에서 KBO 사이트 직접 크롤링이 막혀 있어서, WebSearch로 수집한
공개 정보를 dict로 채워넣고 predictor의 가중치 로직을 그대로 적용함.

데이터 출처:
- KBO 순위: 톱스타뉴스 (5/12 기준)
- 선발투수 폼: 나무위키, 머니투데이, 네이트스포츠 등
- 경기 일정: 톱스타뉴스 5/13 일정 기사
"""
from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from datetime import datetime


# ──────────────────────────────────────────────────────────────────
# 1. 입력 데이터 (수기 정리, 5/13 18:30 경기 5개)
# ──────────────────────────────────────────────────────────────────

# 팀 순위 (5/12 기준)
STANDINGS = {
    "KT":  {"w": 23, "d": 1, "l": 13, "wr": 0.639, "rank": 1},
    "삼성": {"w": 21, "d": 1, "l": 14, "wr": 0.600, "rank": 2},
    "LG":  {"w": 22, "d": 0, "l": 15, "wr": 0.595, "rank": 3},
    "SSG": {"w": 20, "d": 1, "l": 16, "wr": 0.556, "rank": 4},
    "두산": {"w": 18, "d": 1, "l": 19, "wr": 0.486, "rank": 5},
    "한화": {"w": 17, "d": 0, "l": 20, "wr": 0.459, "rank": 6},
    "KIA": {"w": 17, "d": 1, "l": 20, "wr": 0.459, "rank": 7},
    "NC":  {"w": 16, "d": 1, "l": 20, "wr": 0.444, "rank": 8},
    "롯데": {"w": 14, "d": 1, "l": 21, "wr": 0.400, "rank": 9},
    "키움": {"w": 13, "d": 1, "l": 24, "wr": 0.351, "rank": 10},
}

# 선발투수 데이터 (era, recent_form, notes)
# recent_form: +2 = 매우 호조 / +1 = 호조 / 0 = 평범 / -1 = 부진 / -2 = 매우 부진
PITCHERS = {
    "원태인":   {"era": 3.24, "form": +1, "notes": "에이스급, 부상 복귀 후 2번째 등판, 이닝 제한 가능", "complete": False},
    "톨허스트": {"era": 4.50, "form":  0, "notes": "ERA 4.50, 3승1패, 26IP/19K — 평균적", "complete": True},
    "에르난데스": {"era": 5.00, "form": -1, "notes": "투구수·위기관리 불안 지적", "complete": True},
    "박정훈":   {"era": 5.50, "form": -1, "notes": "키움 약체 마운드, 5선발급 추정", "complete": True},
    "타게다":   {"era": 4.20, "form":  0, "notes": "SSG 일본인 선발, 기복형", "complete": True},
    "보쉴리":   {"era": 0.00, "form": +2, "notes": "★ KBO 유일 ERA 0.00 (3경기 17IP 무자책)", "complete": True},
    "최준호":   {"era": 4.80, "form": -1, "notes": "두산 영건, 변동성 큼", "complete": True},
    "양현종":   {"era": 3.90, "form": +1, "notes": "KBO 최초 2,200K, 4월 25일 달성", "complete": True},
    "테일러":   {"era": 4.40, "form":  0, "notes": "NC 외국인 선발, 평균", "complete": True},
    "비슬리":   {"era": 3.80, "form": +1, "notes": "롯데 외국인 선발, 안정적", "complete": True},
}

# 오늘 경기 (원정 vs 홈)
GAMES = [
    {"away": "삼성", "home": "LG",  "away_p": "원태인",   "home_p": "톨허스트", "venue": "잠실"},
    {"away": "한화", "home": "키움", "away_p": "에르난데스", "home_p": "박정훈",   "venue": "고척"},
    {"away": "SSG", "home": "KT",  "away_p": "타게다",   "home_p": "보쉴리",   "venue": "수원"},
    {"away": "두산", "home": "KIA", "away_p": "최준호",   "home_p": "양현종",   "venue": "광주"},
    {"away": "NC",  "home": "롯데", "away_p": "테일러",   "home_p": "비슬리",   "venue": "사직"},
]

# 구장 팩터 (1.00 = 중립, >1.00 = 타자 친화, <1.00 = 투수 친화)
PARK = {
    "잠실": 0.93,   # 큰 구장, 투수 친화
    "고척": 0.95,   # 돔, 약간 투수 친화
    "수원": 1.05,   # 타자 친화
    "광주": 1.03,   # 약간 타자 친화
    "사직": 1.02,   # 약간 타자 친화
}

# 팀 타격 분위기 (최근 폼, -2 ~ +2)
TEAM_BAT_FORM = {
    "KT": +1, "삼성": +1, "LG": 0, "SSG": 0, "두산": 0,
    "한화": 0, "KIA": +1, "NC": -1, "롯데": -1, "키움": -1,
}


# ──────────────────────────────────────────────────────────────────
# 2. predictor 로직 시뮬레이션 (predictor.py 핵심부)
# ──────────────────────────────────────────────────────────────────
@dataclass
class Prediction:
    matchup: str
    venue: str
    pitchers: str
    home_winrate: float
    score_home: float
    score_away: float
    total: float
    pick: str
    pick_strength: str
    edge: float
    ou_pick: str
    notes: list


def pitcher_score(name: str) -> float:
    """투수 점수 (낮을수록 좋음 → 음수 점수로 환산해서 높을수록 좋음)"""
    p = PITCHERS[name]
    # ERA를 점수화: ERA 0=10점, 5=0점 (선형)
    era_score = max(0, 10 - p["era"] * 2)
    # 최근 폼: -2~+2 → -2~+2 보정
    form_bonus = p["form"]
    # 복귀 직후 / 이닝 제한 페널티
    completeness_penalty = 0 if p["complete"] else -1.5
    return era_score + form_bonus + completeness_penalty


def team_score(team: str) -> float:
    """팀 점수: 승률 + 최근 타격 폼"""
    s = STANDINGS[team]
    wr_score = s["wr"] * 10        # 0~10
    bat_form = TEAM_BAT_FORM[team]  # -2 ~ +2
    return wr_score + bat_form


def predict_game(game: dict) -> Prediction:
    home, away = game["home"], game["away"]
    home_p, away_p = game["home_p"], game["away_p"]
    venue = game["venue"]
    park = PARK[venue]

    # 가중치 (predictor.py 가중치 기조)
    # 선발 45%, 팀(승률+타격) 30%, 홈어드밴티지 8%, 매치업/잡변수 17%
    home_pitcher = pitcher_score(home_p)
    away_pitcher = pitcher_score(away_p)
    home_team = team_score(home)
    away_team = team_score(away)

    pitcher_edge = home_pitcher - away_pitcher
    team_edge = home_team - away_team
    home_field = 0.6  # 홈 어드밴티지 약 4% 승률

    edge_raw = 0.45 * pitcher_edge + 0.30 * team_edge + 0.08 * home_field * 10
    # raw edge를 승률로 변환 (시그모이드 근사)
    home_wr = 0.5 + 0.022 * edge_raw
    home_wr = max(0.20, min(0.80, home_wr))

    # 예상 득점: 리그 평균 4.7, 투수 점수와 구장 팩터로 조정
    league_avg = 4.7
    score_home = league_avg * park * (1 - (away_pitcher - 5) * 0.05) * (1 + TEAM_BAT_FORM[home] * 0.04)
    score_away = league_avg * park * (1 - (home_pitcher - 5) * 0.05) * (1 + TEAM_BAT_FORM[away] * 0.04)
    score_home = round(score_home, 2)
    score_away = round(score_away, 2)
    total = round(score_home + score_away, 2)

    diff_pct = abs(home_wr - 0.5) * 100 * 2  # 격차 %
    if home_wr > 0.5:
        pick = f"{home} 승"
        edge_pct = (home_wr - 0.5) * 200
    else:
        pick = f"{away} 승"
        edge_pct = (0.5 - home_wr) * 200

    if edge_pct >= 25:
        strength = "🟢🟢 강한 픽"
    elif edge_pct >= 15:
        strength = "🟢 픽"
    elif edge_pct >= 8:
        strength = "🟡 약한 픽"
    else:
        strength = "⚪ 관망 (50:50)"

    # O/U: KBO 라인 보통 9.5
    if total >= 10.5:
        ou_pick = f"🔼 오버 (예상 {total})"
    elif total <= 8.5:
        ou_pick = f"🔽 언더 (예상 {total})"
    else:
        ou_pick = f"⚪ 관망 (예상 {total})"

    notes = [
        f"{home_p}({home}): {PITCHERS[home_p]['notes']}",
        f"{away_p}({away}): {PITCHERS[away_p]['notes']}",
        f"구장 팩터: {park} ({venue})",
    ]

    return Prediction(
        matchup=f"{away} @ {home}",
        venue=venue,
        pitchers=f"{away_p} vs {home_p}",
        home_winrate=round(home_wr * 100, 1),
        score_home=score_home,
        score_away=score_away,
        total=total,
        pick=pick,
        pick_strength=strength,
        edge=round(edge_pct, 1),
        ou_pick=ou_pick,
        notes=notes,
    )


# ──────────────────────────────────────────────────────────────────
# 3. 출력
# ──────────────────────────────────────────────────────────────────
def main():
    print("=" * 72)
    print(f"⚾ KBO 자동 분석 — 2026-05-13 (수)")
    print("=" * 72)
    print()
    print("📊 팀 순위 (5/12 기준)")
    for team, s in sorted(STANDINGS.items(), key=lambda x: x[1]["rank"]):
        print(f"  {s['rank']:>2}. {team:<3} {s['w']:>2}승 {s['d']}무 {s['l']:>2}패 ({s['wr']:.3f})")
    print()

    results = []
    for game in GAMES:
        pred = predict_game(game)
        print("━" * 72)
        print(f"[{pred.matchup}] @ {pred.venue}")
        print(f"   선발: {pred.pitchers}")
        print("━" * 72)
        print(f"📊 홈 승률: {pred.home_winrate}% | "
              f"예측 스코어: 홈 {pred.score_home} - 원정 {pred.score_away} | "
              f"총득점: {pred.total}")
        print(f"🎯 픽: {pred.pick} — {pred.pick_strength} (격차 {pred.edge}%p)")
        print(f"   O/U: {pred.ou_pick}")
        for n in pred.notes:
            print(f"   · {n}")
        print()
        results.append(asdict(pred))

    print("=" * 72)
    print("📌 요약 픽 시트")
    print("=" * 72)
    print(f"{'경기':<22} {'픽':<14} {'강도':<14} {'O/U':<8}")
    for r in results:
        print(f"{r['matchup']:<22} {r['pick']:<14} {r['pick_strength']:<14} {r['ou_pick'].split()[0]}")

    # 저장
    out = {
        "date": "2026-05-13",
        "league": "KBO",
        "generated_at": datetime.now().isoformat(),
        "standings_asof": "2026-05-12",
        "games": results,
        "source": "WebSearch (KBO 직접 크롤링 불가, 공개 데이터 기반 수기 입력)",
    }
    with open("data/results/kbo_2026-05-13.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 저장: data/results/kbo_2026-05-13.json")


if __name__ == "__main__":
    main()
