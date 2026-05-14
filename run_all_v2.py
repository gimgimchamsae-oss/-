"""
run_all_v2.py — 풀데이터 통합 실행기 (KBO/MLB/NPB)
====================================================
기존 run_all.py 흐름 그대로 + 신규 collector 통합:

KBO: kbo_crawler_v3 + kbo_statiz + kbo_lineup
MLB: mlb_crawler_v3 + mlb_advanced (pybaseball)
NPB: npb_collector + npb_advanced

사용:
    python run_all_v2.py kbo
    python run_all_v2.py mlb
    python run_all_v2.py npb
    python run_all_v2.py all
"""
import sys, os, json, time
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import argparse
from datetime import datetime

from data_collectors.kbo_crawler_v3 import KBOCrawlerV3
from data_collectors.kbo_statiz import KBOStatiz
from data_collectors.kbo_lineup import KBOLineup
from data_collectors.mlb_crawler_v3 import MLBCrawlerV3
from data_collectors.npb_collector import NPBCollector
from data_collectors.npb_advanced import NPBAdvanced
from data_collectors.weather_collector import WeatherCollector

# pybaseball 은 선택적 (없으면 MLB Statcast 스킵)
try:
    from data_collectors.mlb_advanced import MLBAdvanced
    HAS_MLB_ADV = True
except Exception as e:
    print(f"⚠️ mlb_advanced 로드 실패 (pybaseball 미설치?): {e}")
    HAS_MLB_ADV = False

# 심판 데이터 (umpscorecards)
try:
    from models.umpire_score import UmpireScoreAnalyzer
    HAS_UMP = True
except Exception:
    HAS_UMP = False

from models.predictor import GamePredictor


# ============================================================
# KBO 풀데이터 분석
# ============================================================
def analyze_kbo():
    print("\n" + "=" * 70)
    print("⚾ KBO 풀데이터 분석 (공식 + Statiz + 라인업)")
    print("=" * 70)

    crawler = KBOCrawlerV3()
    statiz = KBOStatiz()
    lineup = KBOLineup()
    weather_c = WeatherCollector() if os.getenv("OPENWEATHER_API_KEY") else None

    data = crawler.get_all_data_for_today()
    if not data['today_games']:
        print("❌ 오늘 KBO 경기 없음")
        return []

    print(f"\n📡 Statiz 고급지표 수집 (10팀)...")
    teams_seen = set()
    statiz_cache = {}
    for g in data['today_games']:
        for t in (g.get('home_team'), g.get('away_team')):
            if t and t not in teams_seen:
                teams_seen.add(t)
                statiz_cache[t] = statiz.get_all_for_team(t)
                print(f"  ├─ {t}: wRC+ {statiz_cache[t]['advanced_batting']['wrc_plus']}")

    print(f"\n📡 네이버 라인업/IL 수집...")
    game_ids = lineup.get_today_game_ids()
    lineup_cache = {}
    for t in teams_seen:
        lineup_cache[t] = lineup.get_lineup_data(t, game_ids[0] if game_ids else None)

    predictor = GamePredictor('KBO')
    picks = []
    print(f"\n🔍 {len(data['today_games'])}경기 분석 중...")

    for game in data['today_games']:
        home, away = game.get('home_team'), game.get('away_team')
        if not home or not away:
            continue

        matchup = _build_kbo_matchup(data, game, statiz_cache, lineup_cache, weather_c)
        try:
            pred = predictor.predict(matchup)
            picks.append(_format_pick(pred, game, 'KBO'))
            _print_pick(picks[-1])
        except Exception as e:
            print(f"   ❌ 에러: {e}")

    _save_results('kbo', picks)
    return picks


def _build_kbo_matchup(data, game, statiz_cache, lineup_cache, weather_c):
    home, away = game['home_team'], game['away_team']
    stadium = game.get('stadium', '')

    # 팀 기본 (KBO ws)
    home_bat = next((t for t in data['team_batting'] if t['team'] == home), {})
    away_bat = next((t for t in data['team_batting'] if t['team'] == away), {})
    home_pit = next((t for t in data['team_pitching'] if t['team'] == home), {})
    away_pit = next((t for t in data['team_pitching'] if t['team'] == away), {})

    # 선발 (KBO 개인 투수)
    home_p_name = game.get('home_pitcher')
    away_p_name = game.get('away_pitcher')
    pitchers = {p['name']: p for p in data.get('pitchers', [])}
    home_p = pitchers.get(home_p_name, {})
    away_p = pitchers.get(away_p_name, {})

    # Statiz 보강
    home_adv = statiz_cache.get(home, {})
    away_adv = statiz_cache.get(away, {})

    # 라인업
    home_lu = lineup_cache.get(home, {'absent': [], 'starters': []})
    away_lu = lineup_cache.get(away, {'absent': [], 'starters': []})

    # 날씨
    weather = weather_c.get_weather(stadium) if weather_c else {}

    return {
        'home_team': home,
        'away_team': away,
        'home_pitcher_stats': {'season_stats': home_p},
        'away_pitcher_stats': {'season_stats': away_p},
        'home_batting': home_bat,
        'away_batting': away_bat,
        'home_pitching': home_pit,
        'away_pitching': away_pit,
        # 보강 데이터
        'home_advanced_batting': home_adv.get('advanced_batting'),
        'away_advanced_batting': away_adv.get('advanced_batting'),
        'home_fielding': home_adv.get('fielding'),
        'away_fielding': away_adv.get('fielding'),
        'home_lineup_data': home_lu,
        'away_lineup_data': away_lu,
        'venue': stadium,
        'weather': weather,
        'date': datetime.now().strftime('%Y-%m-%d'),
    }


# ============================================================
# MLB 풀데이터 분석
# ============================================================
def analyze_mlb():
    print("\n" + "=" * 70)
    print("⚾ MLB 풀데이터 분석 (statsapi + pybaseball Statcast + umpscorecards)")
    print("=" * 70)

    crawler = MLBCrawlerV3()
    advanced = MLBAdvanced() if HAS_MLB_ADV else None
    ump_analyzer = UmpireScoreAnalyzer() if HAS_UMP else None
    weather_c = WeatherCollector() if os.getenv("OPENWEATHER_API_KEY") else None

    data = crawler.get_all_data_for_today()
    if not data['games']:
        print("❌ 오늘 MLB 경기 없음")
        return []

    predictor = GamePredictor('MLB')
    picks = []

    for game in data['games']:
        if game['status'] != 'Preview':
            continue
        matchup = _build_mlb_matchup(game, advanced, ump_analyzer, weather_c)
        try:
            pred = predictor.predict(matchup)
            picks.append(_format_pick(pred, game, 'MLB'))
            _print_pick(picks[-1])
        except Exception as e:
            print(f"   ❌ 에러: {e}")

    _save_results('mlb', picks)
    return picks


def _build_mlb_matchup(game, advanced, ump_analyzer, weather_c):
    home_p_id = (game.get('home_pitcher') or {}).get('id')
    away_p_id = (game.get('away_pitcher') or {}).get('id')

    # Statcast (pybaseball 통해 Baseball Savant 직접)
    home_sc = advanced.get_pitcher_statcast(home_p_id) if (advanced and home_p_id) else None
    away_sc = advanced.get_pitcher_statcast(away_p_id) if (advanced and away_p_id) else None

    # 수비 (pybaseball.fielding_stats_bref)
    home_field = advanced.get_team_fielding(game['home_team']['id']) if advanced else None
    away_field = advanced.get_team_fielding(game['away_team']['id']) if advanced else None

    # 고급 타격 (FanGraphs wRC+/wOBA)
    home_adv_bat = advanced.get_team_advanced_batting(game['home_team']['id']) if advanced else None
    away_adv_bat = advanced.get_team_advanced_batting(game['away_team']['id']) if advanced else None

    # 심판 (umpscorecards)
    ump_name = (game.get('umpire') or {}).get('home_plate_name')

    # 날씨
    venue = game.get('venue', '')
    weather = weather_c.get_weather(venue) if weather_c else game.get('weather', {})

    return {
        'home_team': game['home_team']['abbr'],
        'away_team': game['away_team']['abbr'],
        'home_pitcher_stats': game.get('home_pitcher_stats', {}),
        'away_pitcher_stats': game.get('away_pitcher_stats', {}),
        'home_pitcher_statcast': home_sc,
        'away_pitcher_statcast': away_sc,
        'home_batting': game.get('home_batting', {}),
        'away_batting': game.get('away_batting', {}),
        'home_pitching': game.get('home_pitching', {}),
        'away_pitching': game.get('away_pitching', {}),
        'home_advanced_batting': home_adv_bat,
        'away_advanced_batting': away_adv_bat,
        'home_fielding': home_field,
        'away_fielding': away_field,
        'umpire_name': ump_name,
        'venue': venue,
        'weather': weather,
        'date': datetime.now().strftime('%Y-%m-%d'),
    }


# ============================================================
# NPB 풀데이터 분석
# ============================================================
def analyze_npb():
    print("\n" + "=" * 70)
    print("⚾ NPB 풀데이터 분석 (npb.jp + npbstats + baseball-freak + 1.02)")
    print("=" * 70)

    collector = NPBCollector()
    advanced = NPBAdvanced()
    weather_c = WeatherCollector() if os.getenv("OPENWEATHER_API_KEY") else None

    sched = collector.get_schedule()
    today_str = datetime.now().strftime('%Y-%m-%d')
    today_games = [g for g in sched if g.get('date') == today_str]

    if not today_games:
        print("❌ 오늘 NPB 경기 없음")
        return []

    # 보강 데이터 캐시
    teams_seen = set()
    adv_cache = {}
    for g in today_games:
        for t in (g.get('home_team'), g.get('away_team')):
            if t and t not in teams_seen:
                teams_seen.add(t)
                adv_cache[t] = advanced.get_all_for_team(t)

    predictor = GamePredictor('NPB')
    picks = []

    for game in today_games:
        matchup = _build_npb_matchup(game, adv_cache, weather_c)
        try:
            pred = predictor.predict(matchup)
            picks.append(_format_pick(pred, game, 'NPB'))
            _print_pick(picks[-1])
        except Exception as e:
            print(f"   ❌ 에러: {e}")

    _save_results('npb', picks)
    return picks


def _build_npb_matchup(game, adv_cache, weather_c):
    home, away = game['home_team'], game['away_team']
    home_adv = adv_cache.get(home, {})
    away_adv = adv_cache.get(away, {})
    venue = game.get('stadium', '')
    weather = weather_c.get_weather(venue) if weather_c else {}

    return {
        'home_team': home,
        'away_team': away,
        'home_pitcher_stats': {'season_stats': game.get('home_pitcher_stats', {})},
        'away_pitcher_stats': {'season_stats': game.get('away_pitcher_stats', {})},
        'home_batting': game.get('home_batting', {}),
        'away_batting': game.get('away_batting', {}),
        'home_pitching': game.get('home_pitching', {}),
        'away_pitching': game.get('away_pitching', {}),
        'home_advanced_batting': home_adv.get('advanced_batting'),
        'away_advanced_batting': away_adv.get('advanced_batting'),
        'home_lineup_data': home_adv.get('lineup_data'),
        'away_lineup_data': away_adv.get('lineup_data'),
        'venue': venue,
        'weather': weather,
        'date': datetime.now().strftime('%Y-%m-%d'),
    }


# ============================================================
# 출력/저장 헬퍼
# ============================================================
def _format_pick(pred, game, league):
    if league == 'KBO':
        home_lbl = game.get('home_team')
        away_lbl = game.get('away_team')
        venue = game.get('stadium', '')
    elif league == 'NPB':
        home_lbl = game.get('home_team')
        away_lbl = game.get('away_team')
        venue = game.get('stadium', '')
    else:  # MLB
        home_lbl = game['home_team']['abbr']
        away_lbl = game['away_team']['abbr']
        venue = game.get('venue', '')

    hwp = pred.get('home_win_prob', 0.5)
    if hwp >= 0.5:
        winner, edge = home_lbl, (hwp - 0.5) * 200
    else:
        winner, edge = away_lbl, (0.5 - hwp) * 200

    strength = (
        '🟢🟢 강한 픽' if edge >= 20 else
        '🟢 픽'      if edge >= 12 else
        '🟡 약한 픽'   if edge >= 6  else
        '⚪ 관망'
    )

    total = pred.get('predicted_total', 0)
    LINE = {'KBO': 9.5, 'NPB': 8.5, 'MLB': 8.5}[league]
    ou = (
        f'🔼🔼 강한 오버 ({total} vs {LINE})' if total >= LINE + 1.0 else
        f'🔼 오버 ({total})'                 if total >= LINE + 0.3 else
        f'🔽🔽 강한 언더 ({total} vs {LINE})' if total <= LINE - 1.0 else
        f'🔽 언더 ({total})'                 if total <= LINE - 0.3 else
        f'⚪ 관망 ({total})'
    )

    return {
        'league': league,
        'matchup': f"{away_lbl} @ {home_lbl}",
        'venue': venue,
        'home_win_prob': round(hwp, 3),
        'pick': f"{winner} 승",
        'strength': strength,
        'edge_pct': round(edge, 1),
        'total': total,
        'ou_pick': ou,
        'confidence': round(pred.get('confidence', 0), 3),
    }


def _print_pick(p):
    print(f"\n[{p['matchup']}] @ {p['venue']}")
    print(f"   📊 홈 승률 {p['home_win_prob']:.1%} | 토탈 {p['total']} | 신뢰도 {p['confidence']:.1%}")
    print(f"   🎯 픽: {p['pick']} — {p['strength']} (격차 {p['edge_pct']}%p)")
    print(f"   🎯 O/U: {p['ou_pick']}")


def _save_results(league, picks):
    os.makedirs('data/results', exist_ok=True)
    fn = f"data/results/{league}_{datetime.now().strftime('%Y-%m-%d')}_full.json"
    with open(fn, 'w', encoding='utf-8') as f:
        json.dump({'date': datetime.now().strftime('%Y-%m-%d'),
                   'league': league.upper(),
                   'mode': 'full_data (collectors + advanced)',
                   'picks': picks}, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 저장: {fn}")


# ============================================================
# 메인
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('league', nargs='?', default='all',
                       choices=['kbo', 'mlb', 'npb', 'all'])
    args = parser.parse_args()

    if args.league in ('kbo', 'all'):
        analyze_kbo()
    if args.league in ('mlb', 'all'):
        analyze_mlb()
    if args.league in ('npb', 'all'):
        analyze_npb()
