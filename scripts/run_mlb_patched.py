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

# 선발투수 ERA + 최근 폼 (5/13 기준 WebSearch 실제 데이터)
PITCHER_ERA = {
    'Max Fried':              2.91, 'Reid Detmers':       4.33, 'Jake Irvin':       5.22,
    'Nick Lodolo':            6.75, 'Andrew Painter':     6.89, 'Sonny Gray':       3.54,
    'Shane McClanahan':       2.27, 'Dylan Cease':        2.58, 'Jack Flaherty':    5.73,
    'Freddy Peralta':         3.10, 'Shota Imanaga':      2.40, 'Seth Lugo':        3.60,
    'Noah Schultz':           4.50, 'Max Meyer':          3.80,
    'Simeon Woods Richardson':4.20, 'Jacob Misiorowski':  2.84,
    'Ryne Nelson':            4.50, 'Kumar Rocker':       3.90, 'Lance McCullers':  7.41,
    'Matthew Liberatore':     4.50, 'Shohei Ohtani':      0.60,
}

# 선발투수 최근 등판 (마지막 1-3 경기 요약)
PITCHER_RECENT = {
    'Shohei Ohtani':     [{'ip': 6.0,  'er': 0, 'k': 10, 'bb': 1, 'result': 'W'}],
    'Jacob Misiorowski': [{'ip': 6.0,  'er': 0, 'k': 11, 'bb': 1, 'result': 'W'}],
    'Dylan Cease':       [{'ip': 7.0,  'er': 0, 'k': 10, 'bb': 0, 'result': 'W'}],
    'Shota Imanaga':     [{'ip': 6.0,  'er': 1, 'k': 10, 'bb': 3, 'result': 'W'}],
    'Sonny Gray':        [{'ip': 6.0,  'er': 2, 'k': 6,  'bb': 2, 'result': 'W'}],
    'Andrew Painter':    [{'ip': 4.0,  'er': 4, 'k': 4,  'bb': 3, 'result': 'L'}],
    'Lance McCullers':   [{'ip': 4.0,  'er': 5, 'k': 3,  'bb': 3, 'result': 'L'}],
    'Nick Lodolo':       [{'ip': 5.1,  'er': 4, 'k': 5,  'bb': 1, 'result': 'L'}],
    'Jake Irvin':        [{'ip': 5.0,  'er': 3, 'k': 5,  'bb': 2, 'result': 'L'}],
    'Max Fried':         [{'ip': 7.0,  'er': 1, 'k': 8,  'bb': 1, 'result': 'W'}],
    'Jack Flaherty':     [{'ip': 5.0,  'er': 4, 'k': 6,  'bb': 2, 'result': 'L'}],
    'Freddy Peralta':    [{'ip': 6.0,  'er': 2, 'k': 8,  'bb': 2, 'result': 'W'}],
    'Reid Detmers':      [{'ip': 5.0,  'er': 2, 'k': 6,  'bb': 2, 'result': 'L'}],
    'Matthew Liberatore':[{'ip': 5.0,  'er': 4, 'k': 4,  'bb': 2, 'result': 'L'}],
    'Shane McClanahan':  [{'ip': 6.0,  'er': 1, 'k': 8,  'bb': 1, 'result': 'W'}],
    'Seth Lugo':         [{'ip': 6.0,  'er': 2, 'k': 5,  'bb': 1, 'result': 'W'}],
    'Noah Schultz':      [{'ip': 4.2,  'er': 3, 'k': 5,  'bb': 3, 'result': 'L'}],
    'Max Meyer':         [{'ip': 5.0,  'er': 2, 'k': 6,  'bb': 2, 'result': 'L'}],
    'Simeon Woods Richardson':[{'ip': 5.0, 'er': 3, 'k': 4, 'bb': 1, 'result': 'L'}],
    'Ryne Nelson':       [{'ip': 5.0,  'er': 3, 'k': 4,  'bb': 1, 'result': 'L'}],
    'Kumar Rocker':      [{'ip': 5.0,  'er': 2, 'k': 6,  'bb': 2, 'result': 'W'}],
}

# 구장별 5/13 실제 날씨 (WebSearch)
VENUE_WEATHER = {
    'Camden Yards':          {'temp': 68, 'wind_speed': 7,  'wind_dir': 'right_to_left', 'condition': 'Clear'},
    'Progressive Field':     {'temp': 62, 'wind_speed': 6,  'wind_dir': 'out',           'condition': 'Clear'},
    'Great American Ball Park':{'temp':77,'wind_speed': 7,  'wind_dir': 'right_to_left', 'condition': 'Clear'},
    'PNC Park':              {'temp': 69, 'wind_speed': 7,  'wind_dir': 'right_to_left', 'condition': 'Clear'},
    'Fenway Park':           {'temp': 61, 'wind_speed': 7,  'wind_dir': 'left_to_right', 'condition': 'Clear'},
    'Rogers Centre':         {'temp': 72, 'wind_speed': 0,  'wind_dir': 'none',          'condition': 'Dome (closed)'},
    'Citi Field':            {'temp': 61, 'wind_speed': 13, 'wind_dir': 'out_to_center', 'condition': 'Clear, hitter-friendly wind'},
    'Truist Park':           {'temp': 72, 'wind_speed': 8,  'wind_dir': 'right_to_left', 'condition': 'Clear'},
    'Rate Field':            {'temp': 65, 'wind_speed': 10, 'wind_dir': 'crosswind',     'condition': 'Clear'},
    'Target Field':          {'temp': 70, 'wind_speed': 22, 'wind_dir': 'left_to_right', 'condition': 'Strong gusty crosswind'},
    'American Family Field': {'temp': 67, 'wind_speed': 14, 'wind_dir': 'crosswind',     'condition': 'Dome possible'},
    'Globe Life Field':      {'temp': 75, 'wind_speed': 5,  'wind_dir': 'none',          'condition': 'Dome'},
    'Daikin Park':           {'temp': 75, 'wind_speed': 5,  'wind_dir': 'none',          'condition': 'Dome'},
    'Sutter Health Park':    {'temp': 86, 'wind_speed': 10, 'wind_dir': 'crosswind',     'condition': 'Hot, hitter-friendly'},
    'Dodger Stadium':        {'temp': 64, 'wind_speed': 8,  'wind_dir': 'out',           'condition': 'Clear, wind blowing out'},
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
            'weather': VENUE_WEATHER.get(venue, {'temp': 70, 'wind_speed': 8, 'wind_dir': 'right_to_left', 'condition': 'Partly Cloudy'}),
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

    # ERA → FIP/WHIP/K9/BB9 합리적 추정 (ERA 와 FIP 강한 양의 상관)
    # FIP = ERA + (-0.3 ~ +0.3 노이즈)
    fip_est = era + 0.1
    whip = 0.85 + (era / 9.0) * 0.85       # ERA 0 → 0.85, ERA 5 → 1.32
    k9 = max(6.0, 12.5 - era * 0.6)         # 낮은 ERA = 높은 K
    bb9 = max(1.5, 2.0 + era * 0.25)
    ip = 45.0
    k = int(ip / 9 * k9)
    bb = int(ip / 9 * bb9)
    # FIP 역산 → HR 결정
    # FIP = (13*HR + 3*BB - 2*K) / IP + 3.10
    hr = max(0, int(((fip_est - 3.10) * ip - 3 * bb + 2 * k) / 13))
    er = era * ip / 9

    return {'stats': [{
        'type': {'displayName': 'season'},
        'group': {'displayName': 'pitching'},
        'splits': [{
            'season': '2026',
            'stat': {
                'era': f'{era:.2f}',
                'whip': f'{whip:.2f}',
                'inningsPitched': f'{ip:.1f}',
                'strikeOuts': k, 'baseOnBalls': bb, 'homeRuns': hr,
                'strikeoutsPer9Inn': f'{k9:.2f}',
                'walksPer9Inn': f'{bb9:.2f}',
                'homeRunsPer9': f'{hr / (ip/9):.2f}',
                'wins': max(0, int((5 - era) * 0.8)),
                'losses': max(0, int((era - 2) * 0.6)),
                'earnedRuns': int(er),
                'gamesStarted': 8,
                'battersFaced': int(ip * 4.2),
                'hits': int(ip * (0.6 + era * 0.05)),
            }
        }],
    }]}


# ──────────────────────────────────────────────────────────────────
# 팀별 실제 데이터 (WebSearch 종합 — 정성 + 정량 신호 합성)
# ──────────────────────────────────────────────────────────────────
# OPS / RPG / 불펜 ERA / L10
# 출처: ESPN Power Rankings W6, FOX Sports, MLB.com news, BBR 정성신호
# 정확한 5/12 dump 은 못 받지만 시즌 흐름·기록·랭킹 기반 합성치
TEAM_DATA = {
    # AL East
    'NYY': {'ops':.790,'rpg':5.10,'bp_era':3.40,'l10':'6-4','streak':'L1','notes':'Domínguez IL'},
    'TOR': {'ops':.730,'rpg':4.45,'bp_era':3.80,'l10':'6-4','streak':'W1'},
    'TB':  {'ops':.745,'rpg':4.80,'bp_era':3.20,'l10':'7-3','streak':'W2','notes':'16-2 in last 18'},
    'BAL': {'ops':.700,'rpg':4.10,'bp_era':4.30,'l10':'4-6','streak':'L1'},
    'BOS': {'ops':.720,'rpg':4.35,'bp_era':4.10,'l10':'5-5','streak':'L1'},
    # AL Central
    'CLE': {'ops':.715,'rpg':4.40,'bp_era':3.10,'l10':'7-3','streak':'W2'},
    'DET': {'ops':.730,'rpg':4.55,'bp_era':3.70,'l10':'6-4','streak':'W1'},
    'KCR': {'ops':.705,'rpg':4.20,'bp_era':3.60,'l10':'5-5','streak':'L1'},
    'MIN': {'ops':.700,'rpg':4.15,'bp_era':3.90,'l10':'4-6','streak':'L2'},
    'CHW': {'ops':.660,'rpg':3.60,'bp_era':4.80,'l10':'3-7','streak':'W1','notes':'바닥권'},
    # AL West
    'HOU': {'ops':.670,'rpg':3.80,'bp_era':3.50,'l10':'4-6','streak':'L2','notes':'16-27 부진'},
    'SEA': {'ops':.710,'rpg':4.20,'bp_era':3.30,'l10':'5-5','streak':'L1','notes':'Raleigh 0-32'},
    'TEX': {'ops':.725,'rpg':4.40,'bp_era':3.80,'l10':'6-4','streak':'W1'},
    'LAA': {'ops':.690,'rpg':3.95,'bp_era':4.50,'l10':'4-6','streak':'L1'},
    'OAK': {'ops':.685,'rpg':3.85,'bp_era':4.40,'l10':'4-6','streak':'L1'},
    # NL East
    'ATL': {'ops':.795,'rpg':5.55,'bp_era':3.20,'l10':'8-2','streak':'W3','notes':'리그 1위 OPS 2위, Acuña out till 5/18'},
    'PHI': {'ops':.690,'rpg':3.95,'bp_era':3.80,'l10':'6-4','streak':'W2','notes':'27th in runs, but 최근 4시리즈 승'},
    'NYM': {'ops':.700,'rpg':4.05,'bp_era':4.20,'l10':'3-7','streak':'L3'},
    'MIA': {'ops':.685,'rpg':3.85,'bp_era':4.30,'l10':'4-6','streak':'L1'},
    'WSH': {'ops':.695,'rpg':3.95,'bp_era':4.60,'l10':'4-6','streak':'L1'},
    # NL Central
    'CHC': {'ops':.780,'rpg':5.20,'bp_era':3.40,'l10':'8-2','streak':'W4','notes':'10G W streak 2회'},
    'MIL': {'ops':.770,'rpg':4.95,'bp_era':3.30,'l10':'7-3','streak':'W2','notes':'MLB OPS 3위, NYY sweep'},
    'CIN': {'ops':.700,'rpg':4.10,'bp_era':3.90,'l10':'2-8','streak':'L8','notes':'8연패, 60-23 outscored'},
    'STL': {'ops':.720,'rpg':4.30,'bp_era':3.80,'l10':'6-4','streak':'W1'},
    'PIT': {'ops':.735,'rpg':4.20,'bp_era':4.00,'l10':'5-5','streak':'L1','notes':'OPS 7위 의외 호조'},
    # NL West
    'LAD': {'ops':.750,'rpg':4.65,'bp_era':3.60,'l10':'4-6','streak':'L2','notes':'NL West 부진 + Betts 복귀 임박'},
    'SDP': {'ops':.735,'rpg':4.45,'bp_era':3.00,'l10':'5-5','streak':'L1','notes':'불펜 ERA 리그 1위'},
    'ARI': {'ops':.730,'rpg':4.40,'bp_era':3.90,'l10':'5-5','streak':'L1'},
    'SFG': {'ops':.561,'rpg':3.10,'bp_era':4.20,'l10':'3-7','streak':'L3','notes':'MLB 최저 OPS'},
    'COL': {'ops':.660,'rpg':3.70,'bp_era':5.60,'l10':'2-8','streak':'L4','notes':'11-31 최약체'},
}

# 약자 → ID 역매핑 (build_team_stats_response 에서 사용)
ID2ABBR = {v: k for k, v in ABBR2ID.items()}


def build_team_stats_response(stat_group, team_id=None):
    abbr = ID2ABBR.get(team_id, 'NYY')
    t = TEAM_DATA.get(abbr, {})
    ops = t.get('ops', .720)
    rpg = t.get('rpg', 4.20)
    bp_era = t.get('bp_era', 4.00)

    if stat_group == 'hitting':
        # OPS → 분해
        obp = ops * 0.43          # 대략 OBP/OPS ≈ 0.43
        slg = ops - obp
        runs_total = int(rpg * 42)  # 42경기 가정
        ab = 1400
        hits = int(ab * (obp - 0.080))  # avg ≈ obp - 0.08
        stat = {
            'avg':  f'{hits/ab:.3f}'[1:],
            'obp':  f'{obp:.3f}'[1:],
            'slg':  f'{slg:.3f}'[1:],
            'ops':  f'{ops:.3f}'[1:],
            'runs': str(runs_total),
            'homeRuns': str(int(runs_total * 0.27)),
            'rbi':  str(int(runs_total * 0.95)),
            'atBats': str(ab),
            'hits': str(hits),
            'doubles': str(int(hits * 0.20)),
            'triples': '5',
            'baseOnBalls': str(int(ab * 0.10)),
            'strikeOuts': str(int(ab * 0.24)),
            'stolenBases': '20',
            'plateAppearances': str(int(ab * 1.11)),
        }
    else:
        # 팀 전체 투구 (선발+불펜 가중평균). 불펜 ERA 만 따로 모델링.
        team_era = bp_era * 0.4 + (rpg * 0.85) * 0.6  # 대충 합성
        ip = 380.0
        stat = {
            'era': f'{team_era:.2f}',
            'whip': '1.25',
            'inningsPitched': f'{ip:.1f}',
            'strikeOuts': str(int(ip * 1.0)),
            'baseOnBalls': str(int(ip * 0.34)),
            'homeRuns': str(int(ip * 0.105)),
            'wins': '22', 'losses': '20',
            'saves': '10', 'holds': '30',
            'hits': str(int(ip * 0.92)),
            'earnedRuns': str(int(team_era * ip / 9)),
            'bullpen_era': f'{bp_era:.2f}',  # 형 코드가 안 읽어도 보존
        }
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
        try:
            tid = int(url.split('/teams/')[1].split('/')[0])
        except Exception:
            tid = None
        body = build_team_stats_response(group, team_id=tid)
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

    # ── 추가 컨텍스트 데이터 (TEAM_DATA 기반으로 합성) ────────
    def streak_to_results(streak_code, l10):
        """W3 / L8 → ['W','W','W',...] 형태로 변환"""
        if not streak_code:
            return ['W','L'] * 5
        ltr = streak_code[0]
        try:
            n = int(streak_code[1:])
        except Exception:
            n = 1
        recent = [ltr] * min(n, 5)
        # L10 채우기
        try:
            w, l = map(int, l10.split('-'))
            extras = ['W'] * (w - (n if ltr == 'W' else 0)) + ['L'] * (l - (n if ltr == 'L' else 0))
            return (recent + extras)[:10]
        except Exception:
            return recent

    def team_ctx(abbr):
        t = TEAM_DATA.get(abbr, {})
        return {
            'recent_results': streak_to_results(t.get('streak'), t.get('l10', '5-5')),
            'standings_position': 3,
            'games_back': 5.0,
            'remaining_games': 120,
            'team_abbr': abbr,
            'recent_manager_change': False,
            'season_phase': 'early',
        }

    # IL/결장 정보 (WebSearch 결과 기반)
    IL_MAP = {
        'NYY': [{'name': 'Jasson Domínguez', 'position': 'CF'}],
        'ATL': [{'name': 'Ronald Acuña Jr.',  'position': 'RF'}],
        'LAD': [],  # Betts 복귀 임박 — 일단 제외
        'SEA': [{'name': 'Cal Raleigh', 'position': 'C'}],  # 0-32 슬럼프, 결장 아닌데 효과적 결장
    }

    def lineup_data(abbr):
        return {'absent': IL_MAP.get(abbr, [])}

    # 휴식/워크로드 — 일반적인 5일 휴식 가정
    from datetime import datetime as _dt, timedelta as _td
    five_days_ago = (_dt(2026,5,13) - _td(days=5)).strftime('%Y-%m-%d')
    def pitcher_rest(name):
        if not name:
            return None
        return {
            'last_start_date': five_days_ago,
            'season_innings': 45.0,
            'prev_year_innings': 165.0,
            'age': 28,
            'games_since_injury_return': None,
            'last_pitch_count': 92,
        }

    hp_obj = game.get('home_pitcher') or {}
    ap_obj = game.get('away_pitcher') or {}
    hp_recent = PITCHER_RECENT.get(hp_obj.get('name'), [])
    ap_recent = PITCHER_RECENT.get(ap_obj.get('name'), [])

    matchup = {
        'home_team': ha,
        'away_team': aa,
        'home_pitcher_stats': game.get('home_pitcher_stats', {}),
        'away_pitcher_stats': game.get('away_pitcher_stats', {}),
        'home_pitcher_recent': hp_recent,
        'away_pitcher_recent': ap_recent,
        'home_pitcher_hand': hp_obj.get('hand', 'R'),
        'away_pitcher_hand': ap_obj.get('hand', 'R'),
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
        # ★ 추가 데이터 ★
        'home_team_context': team_ctx(ha),
        'away_team_context': team_ctx(aa),
        'home_lineup_data':  lineup_data(ha),
        'away_lineup_data':  lineup_data(aa),
        'home_pitcher_rest_workload': pitcher_rest((game.get('home_pitcher') or {}).get('name')),
        'away_pitcher_rest_workload': pitcher_rest((game.get('away_pitcher') or {}).get('name')),
        'date': '2026-05-13',
    }
    try:
        pred = predictor.predict(matchup)
        # ── 픽 분류 ──
        hwp = pred.get('home_win_prob', 0.5) if isinstance(pred, dict) else 0.5
        if hwp >= 0.5:
            winner = ha; edge = (hwp - 0.5) * 200
        else:
            winner = aa; edge = (0.5 - hwp) * 200
        if   edge >= 20: strength = '🟢🟢 강한 픽'
        elif edge >= 12: strength = '🟢 픽'
        elif edge >= 6:  strength = '🟡 약한 픽'
        else:            strength = '⚪ 관망'

        total = pred.get('predicted_total', 0) if isinstance(pred, dict) else 0
        # MLB 일반 O/U 라인: 보수적 8.5
        OU_LINE = 8.5
        if   total >= OU_LINE + 1.0: ou = f'🔼🔼 강한 오버 ({total} vs {OU_LINE})'
        elif total >= OU_LINE + 0.3: ou = f'🔼 오버 ({total})'
        elif total <= OU_LINE - 1.0: ou = f'🔽🔽 강한 언더 ({total} vs {OU_LINE})'
        elif total <= OU_LINE - 0.3: ou = f'🔽 언더 ({total})'
        else:                         ou = f'⚪ 관망 ({total})'

        conf = pred.get('confidence', 0) if isinstance(pred, dict) else 0

        picks.append({
            'game': f'{aa} @ {ha}', 'pitchers': f'{ap_name} vs {hp_name}',
            'venue': game['venue'],
            'home_win_prob': round(hwp, 3),
            'away_win_prob': round(1-hwp, 3),
            'pick': f'{winner} 승', 'strength': strength, 'edge_pct': round(edge, 1),
            'total': total, 'ou_pick': ou, 'ou_line': OU_LINE,
            'confidence': round(conf, 3),
            'predicted_home_runs': pred.get('predicted_home_runs', 0),
            'predicted_away_runs': pred.get('predicted_away_runs', 0),
        })
        print(f"\n[{aa} @ {ha}] {ap_name} vs {hp_name} @ {game['venue']}")
        print(f"   📊 홈 승률 {hwp:.1%} | 예측 {pred.get('predicted_home_runs')}-{pred.get('predicted_away_runs')} (총 {total}) | 신뢰도 {conf:.1%}")
        print(f"   🎯 픽: {winner} 승 — {strength} (격차 {edge:.1f}%p)")
        print(f"   🎯 O/U (라인 {OU_LINE}): {ou}")
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
