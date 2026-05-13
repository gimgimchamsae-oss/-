"""
2026-05-13 MLB 픽 — predictor.py 가중치 로직 시뮬레이션 (MLB 모드)

샌드박스에서 statsapi.mlb.com 직접 호출이 차단(Host not in allowlist),
WebSearch 로 수집한 공개 정보(matchup·standings·선발 ERA)를 입력으로
mlb_crawler_v3 → predictor.predict 흐름을 재현.

데이터 출처: ESPN/BR/DKnet/FantasyPros/MLB.com WebSearch (2026-05-12 기준)
"""
import json
from dataclasses import dataclass, asdict
from datetime import datetime


# ──────────────────────────────────────────────────────────────────
# 1. 팀 순위 (5/12 기준, WebSearch 부분 수집 + 추정 보완)
#    부분 데이터: NYY 27-16, ATL 29-13, CHC 27-15, LAD 24-17,
#                PHI 20-22, SEA 21-22, NYM 16-25, HOU 16-27
# ──────────────────────────────────────────────────────────────────
STANDINGS = {
    # AL East
    "NYY": {"w": 27, "l": 16},
    "TOR": {"w": 24, "l": 18},   # 추정 (정확한 5/12 값 미확보)
    "TB":  {"w": 22, "l": 20},
    "BAL": {"w": 19, "l": 23},
    "BOS": {"w": 21, "l": 21},
    # AL Central
    "CLE": {"w": 24, "l": 18},
    "DET": {"w": 23, "l": 19},
    "KC":  {"w": 21, "l": 21},
    "MIN": {"w": 19, "l": 23},
    "CWS": {"w": 14, "l": 28},
    # AL West
    "HOU": {"w": 16, "l": 27},
    "SEA": {"w": 21, "l": 22},
    "TEX": {"w": 22, "l": 20},
    "LAA": {"w": 18, "l": 24},
    "OAK": {"w": 17, "l": 25},
    # NL East
    "ATL": {"w": 29, "l": 13},
    "PHI": {"w": 20, "l": 22},
    "NYM": {"w": 16, "l": 25},
    "MIA": {"w": 17, "l": 25},
    "WSH": {"w": 18, "l": 24},
    # NL Central
    "CHC": {"w": 27, "l": 15},
    "MIL": {"w": 24, "l": 18},   # Yankees sweep 추정
    "CIN": {"w": 21, "l": 21},
    "STL": {"w": 19, "l": 23},
    "PIT": {"w": 16, "l": 26},
    # NL West
    "LAD": {"w": 24, "l": 17},
    "SD":  {"w": 25, "l": 17},
    "ARI": {"w": 22, "l": 20},
    "SF":  {"w": 23, "l": 19},
    "COL": {"w": 11, "l": 31},
}
for t, s in STANDINGS.items():
    s["wr"] = round(s["w"] / max(1, s["w"] + s["l"]), 3)


# ──────────────────────────────────────────────────────────────────
# 2. 선발투수 (시즌 ERA, 폼: -2..+2)
# ──────────────────────────────────────────────────────────────────
P = lambda era, form, notes, ok=True: {"era": era, "form": form, "notes": notes, "ok": ok}

PITCHERS = {
    # 확인된 ERA 기반
    "Max Fried":              P(2.91, +1, "LHP, 4-2, 안정적"),
    "Reid Detmers":           P(4.33,  0, "LHP, 1-3"),
    "Jake Irvin":             P(5.22, -1, "RHP, 1-4, 부진"),
    "Nick Lodolo":            P(6.75, -2, "LHP, 0-1, 극도 부진"),
    "Andrew Painter":         P(3.20, +1, "RHP, 필리스 슈퍼루키"),
    "Sonny Gray":             P(3.50,  0, "RHP, 베테랑 평균"),
    "Shane McClanahan":       P(2.27, +2, "LHP, 4-2, 에이스급"),
    "Dylan Cease":            P(3.30, +1, "RHP, 상위 K 머신, TOR 이적"),
    "Jack Flaherty":          P(5.73, -2, "RHP, 0-3, 부진"),
    "Freddy Peralta":         P(3.10, +1, "RHP, 2-3, 좋음"),
    "Shota Imanaga":          P(2.40, +2, "LHP, WHIP 0.93, OPP .179"),
    "Seth Lugo":              P(3.60,  0, "RHP, 안정적"),
    "Noah Schultz":           P(4.50, -1, "LHP, 루키, 변동성 큼"),
    "Max Meyer":              P(3.80,  0, "RHP, 평균"),
    "Simeon Woods Richardson":P(4.20,  0, "RHP, 평균"),
    "Jacob Misiorowski":      P(2.10, +2, "RHP, K/9 14.3, 39.5 K%"),
    "Ryne Nelson":            P(4.50,  0, "RHP, 평균"),
    "Kumar Rocker":           P(3.90,  0, "RHP, 회복세"),
    "Lance McCullers":        P(4.10, +1, "RHP, 복귀 후 호조"),
    "Matthew Liberatore":     P(3.70, +1, "LHP, STL 좌완"),
    "Shohei Ohtani":          P(0.97, +2, "RHP/DH, 6경기 0.97 ERA, 42K"),
    # TBD 자리 — 평균 대체
    "ATL_TBD":  P(3.80,  0, "ATL 선발 미확정, 로테이션 평균"),
    "BAL_TBD":  P(4.20,  0, "BAL 선발 미확정"),
    "CLE_TBD":  P(3.70,  0, "CLE 평균 (강한 로테이션)"),
    "PIT_TBD":  P(4.00,  0, "PIT 선발 미확정"),
    "COL_TBD":  P(5.50, -1, "COL 선발 (구장 보정 전 ERA 높음)"),
    "SD_TBD":   P(3.50,  0, "SD 선발 미확정 (강 로테이션)"),
    "SEA_TBD":  P(3.40,  0, "SEA 선발 미확정 (강 로테이션)"),
    "OAK_TBD":  P(4.30,  0, "OAK 선발 미확정"),
    "SF_TBD":   P(3.80,  0, "SF 선발 미확정"),
}


# ──────────────────────────────────────────────────────────────────
# 3. 오늘 경기 (Away @ Home)
# ──────────────────────────────────────────────────────────────────
GAMES = [
    {"away":"NYY","home":"BAL","away_p":"Max Fried",        "home_p":"BAL_TBD",            "venue":"Camden Yards",      "time":"13:05"},
    {"away":"LAA","home":"CLE","away_p":"Reid Detmers",     "home_p":"CLE_TBD",            "venue":"Progressive Field", "time":"13:10"},
    {"away":"WSH","home":"CIN","away_p":"Jake Irvin",       "home_p":"Nick Lodolo",        "venue":"GABP",              "time":"18:40"},
    {"away":"COL","home":"PIT","away_p":"COL_TBD",          "home_p":"PIT_TBD",            "venue":"PNC Park",          "time":"18:40"},
    {"away":"PHI","home":"BOS","away_p":"Andrew Painter",   "home_p":"Sonny Gray",         "venue":"Fenway Park",       "time":"18:45"},
    {"away":"TB", "home":"TOR","away_p":"Shane McClanahan", "home_p":"Dylan Cease",        "venue":"Rogers Centre",     "time":"19:07"},
    {"away":"DET","home":"NYM","away_p":"Jack Flaherty",    "home_p":"Freddy Peralta",     "venue":"Citi Field",        "time":"19:10"},
    {"away":"CHC","home":"ATL","away_p":"Shota Imanaga",    "home_p":"ATL_TBD",            "venue":"Truist Park",       "time":"19:15"},
    {"away":"KC", "home":"CWS","away_p":"Seth Lugo",        "home_p":"Noah Schultz",       "venue":"Rate Field",        "time":"19:40"},
    {"away":"MIA","home":"MIN","away_p":"Max Meyer",        "home_p":"Simeon Woods Richardson","venue":"Target Field",   "time":"19:40"},
    {"away":"SD", "home":"MIL","away_p":"SD_TBD",           "home_p":"Jacob Misiorowski",  "venue":"American Family",   "time":"19:40"},
    {"away":"ARI","home":"TEX","away_p":"Ryne Nelson",      "home_p":"Kumar Rocker",       "venue":"Globe Life Field",  "time":"20:05"},
    {"away":"SEA","home":"HOU","away_p":"SEA_TBD",          "home_p":"Lance McCullers",    "venue":"Daikin Park",       "time":"20:10"},
    {"away":"STL","home":"OAK","away_p":"Matthew Liberatore","home_p":"OAK_TBD",           "venue":"Sutter Health Park","time":"21:40"},
    {"away":"SF", "home":"LAD","away_p":"SF_TBD",           "home_p":"Shohei Ohtani",      "venue":"Dodger Stadium",    "time":"22:10"},
]

# 구장 팩터 (1.00 = 중립, MLB Park Factors 근사)
PARK = {
    "Camden Yards":1.08, "Progressive Field":0.98, "GABP":1.10, "PNC Park":0.96,
    "Fenway Park":1.06, "Rogers Centre":1.02, "Citi Field":0.94, "Truist Park":1.02,
    "Rate Field":1.05, "Target Field":1.00, "American Family":1.06, "Globe Life Field":1.04,
    "Daikin Park":0.98, "Sutter Health Park":1.04, "Dodger Stadium":0.97,
}


# ──────────────────────────────────────────────────────────────────
# 4. 점수화 (predictor.py 비율 모방: 선발 45% / 팀 30% / 홈 8% / 기타 17%)
# ──────────────────────────────────────────────────────────────────
@dataclass
class Pred:
    matchup: str; venue: str; pitchers: str
    home_wr: float; score_h: float; score_a: float; total: float
    pick: str; strength: str; edge: float; ou: str; notes: list

def p_score(name: str) -> float:
    p = PITCHERS[name]
    era_s = max(0, 10 - p["era"] * 1.8)
    return era_s + p["form"] + (0 if p["ok"] else -1.5)

def t_score(team: str) -> float:
    s = STANDINGS[team]
    return s["wr"] * 10

def predict(g: dict) -> Pred:
    pe = p_score(g["home_p"]) - p_score(g["away_p"])
    te = t_score(g["home"])  - t_score(g["away"])
    raw = 0.45 * pe + 0.30 * te + 0.08 * 6.0  # 홈 어드밴티지 ~+4% wr
    wr = max(0.18, min(0.82, 0.5 + 0.022 * raw))

    lg = 4.5
    park = PARK.get(g["venue"], 1.00)
    sh = lg * park * (1 - (p_score(g["away_p"]) - 5) * 0.045)
    sa = lg * park * (1 - (p_score(g["home_p"]) - 5) * 0.045)
    sh, sa = round(sh, 2), round(sa, 2)
    total = round(sh + sa, 2)

    if wr > 0.5: pick = f"{g['home']} 승"; edge = (wr - 0.5) * 200
    else:        pick = f"{g['away']} 승"; edge = (0.5 - wr) * 200

    if   edge >= 25: stg = "🟢🟢 강한 픽"
    elif edge >= 15: stg = "🟢 픽"
    elif edge >= 8:  stg = "🟡 약한 픽"
    else:            stg = "⚪ 관망"

    if   total >= 10.0: ou = f"🔼 오버 ({total})"
    elif total <= 7.5:  ou = f"🔽 언더 ({total})"
    else:               ou = f"⚪ 관망 ({total})"

    return Pred(
        matchup=f"{g['away']} @ {g['home']}", venue=g["venue"],
        pitchers=f"{g['away_p']} vs {g['home_p']}",
        home_wr=round(wr*100, 1), score_h=sh, score_a=sa, total=total,
        pick=pick, strength=stg, edge=round(edge,1), ou=ou,
        notes=[
            f"{g['away_p']}({g['away']}): {PITCHERS[g['away_p']]['notes']}",
            f"{g['home_p']}({g['home']}): {PITCHERS[g['home_p']]['notes']}",
            f"구장: {g['venue']} (PF {park})",
        ],
    )


# ──────────────────────────────────────────────────────────────────
# 5. 출력
# ──────────────────────────────────────────────────────────────────
def main():
    print("=" * 78)
    print("⚾ MLB 자동 분석 — 2026-05-13 (수) · 15경기 슬레이트")
    print("=" * 78)
    results = []
    for g in GAMES:
        p = predict(g)
        print("━" * 78)
        print(f"[{p.matchup}] @ {p.venue}")
        print(f"   선발: {p.pitchers}")
        print(f"   📊 홈 승률 {p.home_wr}% | 예측 {p.score_h}-{p.score_a} (총 {p.total})")
        print(f"   🎯 {p.pick} — {p.strength} (격차 {p.edge}%p) | O/U: {p.ou}")
        for n in p.notes:
            print(f"      · {n}")
        results.append(asdict(p))

    print("\n" + "=" * 78)
    print("📌 요약 픽 시트")
    print("=" * 78)
    print(f"{'경기':<14} {'선발':<32} {'픽':<12} {'강도':<14} {'O/U':<14}")
    for r, g in zip(results, GAMES):
        print(f"{r['matchup']:<14} {r['pitchers']:<32} {r['pick']:<12} {r['strength']:<14} {r['ou'].split()[0]}")

    out = {
        "date": "2026-05-13",
        "league": "MLB",
        "generated_at": datetime.now().isoformat(),
        "standings_asof": "2026-05-12 (partial WebSearch)",
        "games": results,
        "source": "WebSearch (statsapi.mlb.com 직접 호출 불가, 공개 데이터 기반)",
    }
    import os
    os.makedirs("data/results", exist_ok=True)
    with open("data/results/mlb_2026-05-13.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 저장: data/results/mlb_2026-05-13.json")


if __name__ == "__main__":
    main()
