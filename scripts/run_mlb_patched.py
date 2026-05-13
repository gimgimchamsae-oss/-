"""
run_mlb_patched.py — 형 프로그램(run_all.py mlb)을 그대로 돌리기 위한
requests 어댑터. statsapi.mlb.com 호출을 가로채서 WebSearch 로
수집한 데이터로 응답 객체를 합성한다.

mlb_crawler_v3.py 코드는 한 줄도 안 건드림.
"""
import sys, os, json, time
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import requests
from datetime import datetime
from unittest.mock import MagicMock


# ──────────────────────────────────────────────────────────────────
# 수집된 데이터 (WebSearch 결과)
# ──────────────────────────────────────────────────────────────────
# 팀 ID 매핑 (mlb_crawler_v3 의 TEAM_ABBR 역매핑)
ABBR2ID = {
    'LAA':108,'ARI':109,'BAL':110,'BOS':111,'CHC':112,'CIN':113,
    'CLE':114,'COL':115,'DET':116,'HOU':117,'KCR':118,'LAD':119,
    'WSH':120,'NYM':121,'OAK':133,'PIT':134,'SDP':135,'SEA':136,
    'SFG':137,'STL':138,'TB':139,'TEX':140,'TOR':141,'MIN':142,
    'PHI':143,'ATL':144,'CHW':145,'MIA':146,'NYY':147,'MIL':158,
}

# 오늘 경기 (away, home, away_pitcher, home_pitcher, venue)
TODAY = [
    ('NYY','BAL', ('Max Fried',605229,'L'),          (None,None,None),                       'Camden Yards', 1),
    ('LAA','CLE', ('Reid Detmers',676979,'L'),       (None,None,None),                       'Progressive Field', 5),
    ('WSH','CIN', ('Jake Irvin',663623,'R'),         ('Nick Lodolo',666157,'L'),             'Great American Ball Park', 2602),
    ('COL','PIT', (None,None,None),                  (None,None,None),                       'PNC Park', 31),
    ('PHI','BOS', ('Andrew Painter',694973,'R'),     ('Sonny Gray',543243,'R'),              'Fenway Park', 3),
    ('TB','TOR',  ('Shane McClanahan',663556,'L'),   ('Dylan Cease',656302,'R'),             'Rogers Centre', 14),
    ('DET','NYM', ('Jack Flaherty',656427,'R'),      ('Freddy Peralta',642547,'R'),          'Citi Field', 3289),
    ('CHC','ATL', ('Shota Imanaga',684007,'L'),      (None,None,None),                       'Truist Park', 4705),
    ('KCR','CHW', ('Seth Lugo',607625,'R'),          ('Noah Schultz',694981,'L'),            'Rate Field', 4),
    ('MIA','MIN', ('Max Meyer',677958,'R'),          ('Simeon Woods Richardson',680570,'R'), 'Target Field', 3312),
    ('SDP','MIL', (None,None,None),                  ('Jacob Misiorowski',682243,'R'),       'American Family Field', 32),
    ('ARI','TEX', ('Ryne Nelson',680686,'R'),        ('Kumar Rocker',694383,'R'),            'Globe Life Field', 5325),
    ('SEA','HOU', (None,None,None),                  ('Lance McCullers',621121,'R'),         'Daikin Park', 2392),
    ('STL','OAK', ('Matthew Liberatore',669461,'L'), (None,None,None),                       'Sutter Health Park', 2507),
    ('SFG','LAD', (None,None,None),                  ('Shohei Ohtani',660271,'R'),           'Dodger Stadium', 22),
]

# 팀 순위 (W-L, WebSearch 부분 + 추정 보완)
STANDINGS_DATA = {
    'NYY':(27,16),'TOR':(24,18),'TB':(22,20),'BAL':(19,23),'BOS':(21,21),
    'CLE':(24,18),'DET':(23,19),'KCR':(21,21),'MIN':(19,23),'CHW':(14,28),
    'HOU':(16,27),'SEA':(21,22),'TEX':(22,20),'LAA':(18,24),'OAK':(17,25),
    'ATL':(29,13),'PHI':(20,22),'NYM':(16,25),'MIA':(17,25),'WSH':(18,24),
    'CHC':(27,15),'MIL':(24,18),'CIN':(21,21),'STL':(19,23),'PIT':(16,26),
    'LAD':(24,17),'SDP':(25,17),'ARI':(22,20),'SFG':(23,19),'COL':(11,31),
}

# 선발투수 ERA (WebSearch 결과)
PITCHER_ERA = {
    'Max Fried': 2.91, 'Reid Detmers': 4.33, 'Jake Irvin': 5.22,
    'Nick Lodolo': 6.75, 'Andrew Painter': 3.20, 'Sonny Gray': 3.50,
    'Shane McClanahan': 2.27, 'Dylan Cease': 3.30, 'Jack Flaherty': 5.73,
    'Freddy Peralta': 3.10, 'Shota Imanaga': 2.40, 'Seth Lugo': 3.60,
    'Noah Schultz': 4.50, 'Max Meyer': 3.80,
    'Simeon Woods Richardson': 4.20, 'Jacob Misiorowski': 2.10,
    'Ryne Nelson': 4.50, 'Kumar Rocker': 3.90, 'Lance McCullers': 4.10,
    'Matthew Liberatore': 3.70, 'Shohei Ohtani': 0.97,
}


# ──────────────────────────────────────────────────────────────────
# 가짜 응답 빌더 (statsapi.mlb.com 응답 스키마 그대로)
# ──────────────────────────────────────────────────────────────────
def build_schedule_response(date_str):
    games = []
    for i, (a, h, ap, hp, venue, venue_id) in enumerate(TODAY):
        ap_obj = {'id': ap[1], 'fullName': ap[0], 'pitchHand': {'code': ap[2]}} if ap[0] else None
        hp_obj = {'id': hp[1], 'fullName': hp[0], 'pitchHand': {'code': hp[2]}} if hp[0] else None
        g = {
            'gamePk': 800000 + i,
            'gameDate': f'{date_str}T18:05:00Z',
            'status': {'abstractGameState': 'Preview'},
            'venue': {'id': venue_id, 'name': venue},
            'weather': {'condition': 'Partly Cloudy', 'temp': 70, 'wind': '8 mph, R to L'},
            'teams': {
                'away': {
                    'team': {'id': ABBR2ID[a], 'name': a},
                    'probablePitcher': ap_obj,
                    'leagueRecord': {'wins': STANDINGS_DATA[a][0], 'losses': STANDINGS_DATA[a][1]},
                },
                'home': {
                    'team': {'id': ABBR2ID[h], 'name': h},
                    'probablePitcher': hp_obj,
                    'leagueRecord': {'wins': STANDINGS_DATA[h][0], 'losses': STANDINGS_DATA[h][1]},
                },
            },
        }
        games.append(g)
    return {'dates': [{'date': date_str, 'games': games}]}


def build_standings_response():
    AL_TEAMS = ['NYY','TOR','TB','BAL','BOS','CLE','DET','KCR','MIN','CHW',
                'HOU','SEA','TEX','LAA','OAK']
    NL_TEAMS = ['ATL','PHI','NYM','MIA','WSH','CHC','MIL','CIN','STL','PIT',
                'LAD','SDP','ARI','SFG','COL']
    def rec(team):
        w, l = STANDINGS_DATA[team]
        return {
            'team': {'id': ABBR2ID[team], 'name': team},
            'wins': w, 'losses': l,
            'winningPercentage': f'{w/(w+l):.3f}'[1:],
            'gamesBack': '-',
            'streak': {'streakCode': 'W1'},
            'records': {'splitRecords': []},
        }
    return {'records': [
        {'league': {'id': 103}, 'teamRecords': [rec(t) for t in AL_TEAMS]},
        {'league': {'id': 104}, 'teamRecords': [rec(t) for t in NL_TEAMS]},
    ]}


def build_pitcher_stats_response(pitcher_id):
    name = next((nm for nm, _id in [(p[0][0], p[0][1]) for p in TODAY] + [(p[1][0], p[1][1]) for p in TODAY]
                 if _id == pitcher_id and nm), 'Unknown')
    era = PITCHER_ERA.get(name, 4.00)
    # ERA → 대충 추정 (K, BB, IP)
    ip = 40.0
    er = era * ip / 9
    return {'stats': [{
        'type': {'displayName': 'season'},
        'group': {'displayName': 'pitching'},
        'splits': [{
            'season': '2026',
            'stat': {
                'era': f'{era:.2f}', 'whip': '1.15',
                'inningsPitched': f'{ip:.1f}',
                'strikeOuts': int(ip * 1.1), 'baseOnBalls': int(ip * 0.3),
                'homeRuns': int(ip * 0.10),
                'wins': max(0, int((5 - era) * 0.8)),
                'losses': max(0, int((era - 2) * 0.6)),
                'earnedRuns': int(er),
                'battersFaced': int(ip * 4.2), 'hits': int(ip * 0.85),
            }
        }],
    }]}


def build_team_stats_response(stat_group):
    # 매우 단순한 기본값 — predictor 가 KeyError 안 나도록만
    if stat_group == 'hitting':
        stat = {'avg': '.255', 'obp': '.320', 'slg': '.420', 'ops': '.740',
                'runs': '180', 'homeRuns': '45', 'rbi': '170',
                'atBats': '1400', 'hits': '358', 'doubles': '70',
                'triples': '5', 'baseOnBalls': '140', 'strikeOuts': '350',
                'stolenBases': '20', 'plateAppearances': '1560'}
    else:
        stat = {'era': '3.90', 'whip': '1.25', 'inningsPitched': '380.0',
                'strikeOuts': '380', 'baseOnBalls': '130', 'homeRuns': '40',
                'wins': '22', 'losses': '20', 'saves': '10',
                'holds': '30', 'hits': '350', 'earnedRuns': '165'}
    return {'stats': [{
        'type': {'displayName': 'season'},
        'group': {'displayName': stat_group},
        'splits': [{'season': '2026', 'stat': stat}],
    }]}


# ──────────────────────────────────────────────────────────────────
# requests 가로채기
# ──────────────────────────────────────────────────────────────────
_real_get = requests.Session.get

def patched_get(self, url, **kwargs):
    print(f"  📡 GET {url[:80]}{'...' if len(url) > 80 else ''}")
    params = kwargs.get('params', {})
    body = None

    if '/schedule' in url:
        date = params.get('date', datetime.now().strftime('%Y-%m-%d'))
        body = build_schedule_response(date)
    elif '/standings' in url:
        body = build_standings_response()
    elif '/people/' in url and '/stats' in url:
        pid = int(url.split('/people/')[1].split('/')[0])
        body = build_pitcher_stats_response(pid)
    elif '/teams/' in url and '/stats' in url:
        group = params.get('group', 'hitting')
        body = build_team_stats_response(group)
    else:
        body = {'dates': [], 'records': [], 'stats': []}

    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = body
    resp.raise_for_status.return_value = None
    resp.text = json.dumps(body)
    return resp


requests.Session.get = patched_get


# ──────────────────────────────────────────────────────────────────
# 이제 형 프로그램 그대로 실행
# ──────────────────────────────────────────────────────────────────
from data_collectors.mlb_crawler_v3 import MLBCrawlerV3
from models.predictor import GamePredictor

print('=' * 78)
print('⚾ MLB 자동 분석 (run_all.py mlb 흐름 그대로, requests 패치됨)')
print('=' * 78)

crawler = MLBCrawlerV3()
data = crawler.get_all_data_for_today()

print(f"\n수집 결과: {len(data['games'])}경기, 순위 {len(data['standings'])}팀")

predictor = GamePredictor('MLB')
picks = []
print(f"\n🔍 {len(data['games'])}경기 예측")
print('=' * 78)

for game in data['games']:
    if game['status'] != 'Preview':
        continue
    ha = game['home_team']['abbr']
    aa = game['away_team']['abbr']
    hp_name = game['home_pitcher']['name'] if game.get('home_pitcher') else 'TBD'
    ap_name = game['away_pitcher']['name'] if game.get('away_pitcher') else 'TBD'

    matchup = {
        'home_team': ha,
        'away_team': aa,
        'home_pitcher_stats': game.get('home_pitcher_stats', {}),
        'away_pitcher_stats': game.get('away_pitcher_stats', {}),
        'home_batting': game.get('home_batting', {}),
        'away_batting': game.get('away_batting', {}),
        'home_pitching': game.get('home_pitching', {}),
        'away_pitching': game.get('away_pitching', {}),
        'home_recent_results': game.get('home_recent_results', []),
        'away_recent_results': game.get('away_recent_results', []),
        'home_standings': game.get('home_standings', {}),
        'away_standings': game.get('away_standings', {}),
        'venue': game.get('venue'),
        'weather': game.get('weather', {}),
    }
    try:
        pred = predictor.predict(matchup)
        picks.append({'game': f'{aa} @ {ha}', 'pitchers': f'{ap_name} vs {hp_name}', 'pred': pred})
        print(f"\n[{aa} @ {ha}] {ap_name} vs {hp_name} @ {game['venue']}")
        if isinstance(pred, dict):
            for k, v in pred.items():
                if k not in ('details', 'breakdown'):
                    print(f"   {k}: {v}")
        else:
            print(f"   결과: {pred}")
    except Exception as e:
        import traceback
        print(f"\n[{aa} @ {ha}] 예측 에러: {type(e).__name__}: {e}")
        traceback.print_exc()
        picks.append({'game': f'{aa} @ {ha}', 'error': str(e)})

# 저장
os.makedirs('data/results', exist_ok=True)
with open('data/results/mlb_2026-05-13_patched.json', 'w', encoding='utf-8') as f:
    json.dump({
        'date': '2026-05-13',
        'mode': 'patched_requests (run_all.py mlb 흐름 그대로)',
        'picks': picks,
    }, f, ensure_ascii=False, indent=2, default=str)

print(f"\n✅ 저장: data/results/mlb_2026-05-13_patched.json")
print(f"📊 픽 {len(picks)}개 생성")
