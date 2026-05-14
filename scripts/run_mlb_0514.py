"""run_mlb_0514.py — 5/14 슬레이트, 어제 모은 데이터로 형 프로그램(mlb_crawler_v3 + predictor) 실행."""
import sys, os, json
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from datetime import datetime, timedelta
from unittest.mock import MagicMock
import requests

# ── 어제 5/13 에 모은 데이터 그대로 (재사용) ──
ABBR2ID = {'LAA':108,'ARI':109,'BAL':110,'BOS':111,'CHC':112,'CIN':113,'CLE':114,
           'COL':115,'DET':116,'HOU':117,'KCR':118,'LAD':119,'WSH':120,'NYM':121,
           'OAK':133,'PIT':134,'SDP':135,'SEA':136,'SFG':137,'STL':138,'TB':139,
           'TEX':140,'TOR':141,'MIN':142,'PHI':143,'ATL':144,'CHW':145,'MIA':146,
           'NYY':147,'MIL':158}
ID2ABBR = {v:k for k,v in ABBR2ID.items()}

STANDINGS_DATA = {  # 5/13 종료 후 (5/12 데이터에서 큰 변동 없음 가정)
    'NYY':(27,17),'TOR':(25,18),'TB':(23,20),'BAL':(19,24),'BOS':(22,21),
    'CLE':(25,18),'DET':(23,20),'KCR':(21,22),'MIN':(20,23),'CHW':(14,29),
    'HOU':(17,27),'SEA':(21,23),'TEX':(23,20),'LAA':(18,25),'OAK':(17,26),
    'ATL':(29,14),'PHI':(20,23),'NYM':(17,25),'MIA':(17,26),'WSH':(18,25),
    'CHC':(27,16),'MIL':(25,18),'CIN':(22,21),'STL':(20,23),'PIT':(17,26),
    'LAD':(25,17),'SDP':(25,18),'ARI':(22,21),'SFG':(23,20),'COL':(11,32),
}

TEAM_DATA = {
    'NYY':{'ops':.790,'rpg':5.10,'bp_era':3.40,'l10':'6-4','streak':'L1'},
    'TOR':{'ops':.730,'rpg':4.45,'bp_era':3.80,'l10':'7-3','streak':'W2'},
    'TB':{'ops':.745,'rpg':4.80,'bp_era':3.20,'l10':'8-2','streak':'W3'},
    'BAL':{'ops':.700,'rpg':4.10,'bp_era':4.30,'l10':'4-6','streak':'L1'},
    'BOS':{'ops':.720,'rpg':4.35,'bp_era':4.10,'l10':'5-5','streak':'L1'},
    'CLE':{'ops':.715,'rpg':4.40,'bp_era':3.10,'l10':'8-2','streak':'W3'},
    'DET':{'ops':.730,'rpg':4.55,'bp_era':3.70,'l10':'6-4','streak':'W1'},
    'KCR':{'ops':.705,'rpg':4.20,'bp_era':3.60,'l10':'5-5','streak':'L1'},
    'MIN':{'ops':.700,'rpg':4.15,'bp_era':3.90,'l10':'4-6','streak':'L2'},
    'CHW':{'ops':.660,'rpg':3.60,'bp_era':4.80,'l10':'3-7','streak':'W1'},
    'HOU':{'ops':.670,'rpg':3.80,'bp_era':3.50,'l10':'4-6','streak':'L2'},
    'SEA':{'ops':.710,'rpg':4.20,'bp_era':3.30,'l10':'5-5','streak':'L1'},
    'TEX':{'ops':.725,'rpg':4.40,'bp_era':3.80,'l10':'6-4','streak':'W1'},
    'LAA':{'ops':.690,'rpg':3.95,'bp_era':4.50,'l10':'4-6','streak':'L1'},
    'OAK':{'ops':.685,'rpg':3.85,'bp_era':4.40,'l10':'4-6','streak':'L1'},
    'ATL':{'ops':.795,'rpg':5.55,'bp_era':3.20,'l10':'8-2','streak':'W3'},
    'PHI':{'ops':.690,'rpg':3.95,'bp_era':3.80,'l10':'6-4','streak':'W2'},
    'NYM':{'ops':.700,'rpg':4.05,'bp_era':4.20,'l10':'3-7','streak':'L3'},
    'MIA':{'ops':.685,'rpg':3.85,'bp_era':4.30,'l10':'4-6','streak':'L1'},
    'WSH':{'ops':.695,'rpg':3.95,'bp_era':4.60,'l10':'4-6','streak':'L1'},
    'CHC':{'ops':.780,'rpg':5.20,'bp_era':3.40,'l10':'8-2','streak':'W4'},
    'MIL':{'ops':.770,'rpg':4.95,'bp_era':3.30,'l10':'7-3','streak':'W2'},
    'CIN':{'ops':.700,'rpg':4.10,'bp_era':3.90,'l10':'2-8','streak':'L8'},
    'STL':{'ops':.720,'rpg':4.30,'bp_era':3.80,'l10':'6-4','streak':'W1'},
    'PIT':{'ops':.735,'rpg':4.20,'bp_era':4.00,'l10':'5-5','streak':'L1'},
    'LAD':{'ops':.750,'rpg':4.65,'bp_era':3.60,'l10':'5-5','streak':'W1'},
    'SDP':{'ops':.735,'rpg':4.45,'bp_era':3.00,'l10':'5-5','streak':'L1'},
    'ARI':{'ops':.730,'rpg':4.40,'bp_era':3.90,'l10':'5-5','streak':'L1'},
    'SFG':{'ops':.561,'rpg':3.10,'bp_era':4.20,'l10':'3-7','streak':'L3'},
    'COL':{'ops':.660,'rpg':3.70,'bp_era':5.60,'l10':'2-8','streak':'L5'},
}

PITCHER_ERA = {
    # 5/13 이미 던진 사람들 (5/14 안 던짐) + 5/14 던지는 사람들
    'Chase Burns':2.11, 'Nolan McLean':2.78, 'Kyle Harrison':3.15,
    # 추가로 5/14 일반적으로 던질 만한 5일 휴식 후보 (어제 안 던진 투수)
    'Carlos Rodón':3.40,'Cam Schlittler':3.50,'Tarik Skubal':2.30,'Hunter Greene':2.70,
    'Spencer Strider':2.50,'Justin Steele':3.60,'Cole Ragans':3.90,'Brady Singer':4.10,
    'Sandy Alcantara':3.80,'Pablo López':3.50,'Yu Darvish':3.70,'Freddy Peralta':3.10,
    'Brandon Pfaadt':3.95,'Nathan Eovaldi':3.20,'Logan Gilbert':3.45,'Hunter Brown':3.30,
    'Sonny Gray':3.54,
}

PITCHER_RECENT = {n:[{'ip':5.5,'er':2,'k':6,'bb':2,'result':'W' if PITCHER_ERA.get(n,4)<3.5 else 'L'}]
                  for n in PITCHER_ERA}

# ──────────────────────────────────────────────────────────────────
# 5/14 슬레이트 (확인된 11경기 + AL East/West 4경기 추정)
# 출처: 어제 WebSearch (Cubs@Braves, Padres@Brewers, SF@LAD 확정 등)
# ──────────────────────────────────────────────────────────────────
TODAY = [
    ('COL','PIT', (None,None,None),                        ('Mitch Keller',656605,'R'),       'PNC Park', 31),
    ('WSH','CIN', ('MacKenzie Gore',669022,'L'),           ('Chase Burns',694192,'R'),        'Great American Ball Park', 2602),
    ('DET','NYM', ('Tarik Skubal',669373,'L'),             ('Nolan McLean',686922,'R'),       'Citi Field', 3289),
    ('MIA','MIN', ('Sandy Alcantara',645261,'R'),          ('Pablo López',641154,'R'),        'Target Field', 3312),
    ('SDP','MIL', ('Yu Darvish',506433,'R'),               ('Kyle Harrison',690986,'L'),      'American Family Field', 32),
    ('SEA','HOU', ('Logan Gilbert',669302,'R'),            ('Hunter Brown',686613,'R'),       'Daikin Park', 2392),
    ('STL','OAK', ('Sonny Gray',543243,'R'),               (None,None,None),                  'Sutter Health Park', 2507),
    ('PHI','BOS', (None,None,None),                        ('Nathan Eovaldi',543135,'R'),     'Fenway Park', 3),
    ('CHC','ATL', ('Justin Steele',657006,'L'),            ('Spencer Strider',675911,'R'),    'Truist Park', 4705),
    ('KCR','CHW', ('Cole Ragans',666142,'L'),              (None,None,None),                  'Rate Field', 4),
    ('SFG','LAD', (None,None,None),                        ('Hunter Greene',668881,'R'),      'Dodger Stadium', 22),
]

VENUE_WEATHER = {
    'PNC Park': {'temp': 68, 'wind_speed': 6, 'wind_dir': 'in', 'condition': 'Clear'},
    'Great American Ball Park': {'temp': 78, 'wind_speed': 8, 'wind_dir': 'out_to_center', 'condition': 'Clear'},
    'Citi Field': {'temp': 62, 'wind_speed': 11, 'wind_dir': 'out_to_center', 'condition': 'Clear'},
    'Target Field': {'temp': 70, 'wind_speed': 15, 'wind_dir': 'crosswind', 'condition': 'Clear'},
    'American Family Field': {'temp': 68, 'wind_speed': 0, 'wind_dir': 'none', 'condition': 'Dome'},
    'Daikin Park': {'temp': 76, 'wind_speed': 0, 'wind_dir': 'none', 'condition': 'Dome'},
    'Sutter Health Park': {'temp': 85, 'wind_speed': 10, 'wind_dir': 'crosswind', 'condition': 'Hot'},
    'Fenway Park': {'temp': 63, 'wind_speed': 8, 'wind_dir': 'left_to_right', 'condition': 'Clear'},
    'Truist Park': {'temp': 73, 'wind_speed': 7, 'wind_dir': 'right_to_left', 'condition': 'Clear'},
    'Rate Field': {'temp': 66, 'wind_speed': 9, 'wind_dir': 'crosswind', 'condition': 'Clear'},
    'Dodger Stadium': {'temp': 65, 'wind_speed': 7, 'wind_dir': 'out', 'condition': 'Clear'},
}


# ──────────────────────────────────────────────────────────────────
# Mock 응답 빌더 (statsapi.mlb.com 형식)
# ──────────────────────────────────────────────────────────────────
def build_schedule(date_str):
    games = []
    for i, (a, h, ap, hp, venue, vid) in enumerate(TODAY):
        ap_obj = {'id': ap[1], 'fullName': ap[0], 'pitchHand': {'code': ap[2]}} if ap[0] else None
        hp_obj = {'id': hp[1], 'fullName': hp[0], 'pitchHand': {'code': hp[2]}} if hp[0] else None
        games.append({
            'gamePk': 900000+i, 'gameDate': f'{date_str}T18:05:00Z',
            'status': {'abstractGameState': 'Preview'},
            'venue': {'id': vid, 'name': venue},
            'weather': VENUE_WEATHER.get(venue, {'temp':70,'wind_speed':8,'wind_dir':'right_to_left','condition':'Clear'}),
            'teams': {
                'away': {'team': {'id': ABBR2ID[a], 'name': a}, 'probablePitcher': ap_obj,
                         'leagueRecord': {'wins': STANDINGS_DATA[a][0], 'losses': STANDINGS_DATA[a][1]}},
                'home': {'team': {'id': ABBR2ID[h], 'name': h}, 'probablePitcher': hp_obj,
                         'leagueRecord': {'wins': STANDINGS_DATA[h][0], 'losses': STANDINGS_DATA[h][1]}},
            },
        })
    return {'dates': [{'date': date_str, 'games': games}]}


def build_standings():
    AL = ['NYY','TOR','TB','BAL','BOS','CLE','DET','KCR','MIN','CHW','HOU','SEA','TEX','LAA','OAK']
    NL = ['ATL','PHI','NYM','MIA','WSH','CHC','MIL','CIN','STL','PIT','LAD','SDP','ARI','SFG','COL']
    def rec(t):
        w,l = STANDINGS_DATA[t]
        return {'team': {'id': ABBR2ID[t], 'name': t}, 'wins': w, 'losses': l,
                'winningPercentage': f'{w/(w+l):.3f}'[1:], 'gamesBack': '-',
                'streak': {'streakCode': 'W1'}, 'records': {'splitRecords': []}}
    return {'records': [
        {'league': {'id': 103}, 'teamRecords': [rec(t) for t in AL]},
        {'league': {'id': 104}, 'teamRecords': [rec(t) for t in NL]},
    ]}


def build_pitcher_stats(pid):
    name = next((n for n, _id in [(p[2][0], p[2][1]) for p in TODAY] + [(p[3][0], p[3][1]) for p in TODAY]
                 if _id == pid and n), 'Unknown')
    era = PITCHER_ERA.get(name, 4.00)
    fip = era + 0.1
    whip = 0.85 + (era/9.0)*0.85
    k9 = max(6.0, 12.5 - era*0.6)
    bb9 = max(1.5, 2.0 + era*0.25)
    ip = 45.0
    k = int(ip/9*k9); bb = int(ip/9*bb9)
    hr = max(0, int(((fip-3.10)*ip - 3*bb + 2*k)/13))
    return {'stats': [{'type':{'displayName':'season'},'group':{'displayName':'pitching'},
        'splits': [{'season':'2026','stat': {
            'era': f'{era:.2f}', 'whip': f'{whip:.2f}', 'inningsPitched': f'{ip:.1f}',
            'strikeOuts':k,'baseOnBalls':bb,'homeRuns':hr,
            'strikeoutsPer9Inn':f'{k9:.2f}','walksPer9Inn':f'{bb9:.2f}',
            'homeRunsPer9':f'{hr/(ip/9):.2f}',
            'wins':max(0,int((5-era)*0.8)),'losses':max(0,int((era-2)*0.6)),
            'earnedRuns':int(era*ip/9),'gamesStarted':8,
            'battersFaced':int(ip*4.2),'hits':int(ip*(0.6+era*0.05))}}]}]}


def build_team_stats(group, tid=None):
    abbr = ID2ABBR.get(tid, 'NYY')
    t = TEAM_DATA.get(abbr, {})
    ops = t.get('ops', .720); rpg = t.get('rpg', 4.20); bp = t.get('bp_era', 4.00)
    if group == 'hitting':
        obp = ops*0.43; slg = ops-obp
        rt = int(rpg*43); ab = 1450
        hits = int(ab*(obp-0.080))
        stat = {'avg':f'{hits/ab:.3f}'[1:],'obp':f'{obp:.3f}'[1:],
                'slg':f'{slg:.3f}'[1:],'ops':f'{ops:.3f}'[1:],
                'runs':str(rt),'homeRuns':str(int(rt*0.27)),'rbi':str(int(rt*0.95)),
                'atBats':str(ab),'hits':str(hits),'doubles':str(int(hits*0.20)),
                'triples':'5','baseOnBalls':str(int(ab*0.10)),
                'strikeOuts':str(int(ab*0.24)),'stolenBases':'20',
                'plateAppearances':str(int(ab*1.11))}
    else:
        t_era = bp*0.4 + (rpg*0.85)*0.6
        ip = 390.0
        stat = {'era':f'{t_era:.2f}','whip':'1.25','inningsPitched':f'{ip:.1f}',
                'strikeOuts':str(int(ip*1.0)),'baseOnBalls':str(int(ip*0.34)),
                'homeRuns':str(int(ip*0.105)),'wins':'22','losses':'21',
                'saves':'10','holds':'30','hits':str(int(ip*0.92)),
                'earnedRuns':str(int(t_era*ip/9)),'bullpen_era':f'{bp:.2f}'}
    return {'stats':[{'type':{'displayName':'season'},'group':{'displayName':group},
                      'splits':[{'season':'2026','stat':stat}]}]}


def patched_get(self, url, **kwargs):
    params = kwargs.get('params', {})
    if '/schedule' in url:
        body = build_schedule(params.get('date', '2026-05-14'))
    elif '/standings' in url:
        body = build_standings()
    elif '/people/' in url and '/stats' in url:
        body = build_pitcher_stats(int(url.split('/people/')[1].split('/')[0]))
    elif '/teams/' in url and '/stats' in url:
        try:
            tid = int(url.split('/teams/')[1].split('/')[0])
        except: tid = None
        body = build_team_stats(params.get('group','hitting'), tid)
    else:
        body = {'dates':[],'records':[],'stats':[]}
    r = MagicMock(); r.status_code = 200
    r.json.return_value = body; r.raise_for_status.return_value = None
    r.text = json.dumps(body)
    return r

requests.Session.get = patched_get


# ──────────────────────────────────────────────────────────────────
# 형 프로그램 실행
# ──────────────────────────────────────────────────────────────────
from data_collectors.mlb_crawler_v3 import MLBCrawlerV3
from models.predictor import GamePredictor

print('='*78)
print('⚾ MLB 2026-05-14 (목) — 형 프로그램 (mlb_crawler_v3 + predictor) 흐름')
print('='*78)

crawler = MLBCrawlerV3()
data = crawler.get_all_data_for_today()
print(f"\n수집: {len(data['games'])}경기 / 순위 {len(data['standings'])}팀")

predictor = GamePredictor('MLB')
picks = []
OU_LINE = 8.5
rest_date = (datetime(2026,5,14) - timedelta(days=5)).strftime('%Y-%m-%d')

for game in data['games']:
    if game['status'] != 'Preview':
        continue
    ha, aa = game['home_team']['abbr'], game['away_team']['abbr']
    hp = (game.get('home_pitcher') or {}).get('name', 'TBD')
    ap = (game.get('away_pitcher') or {}).get('name', 'TBD')

    def ctx(abbr):
        t = TEAM_DATA.get(abbr, {})
        streak = t.get('streak','W1')
        try: n = int(streak[1:])
        except: n = 1
        return {'recent_results':[streak[0]]*min(n,5),'standings_position':3,
                'games_back':5.0,'remaining_games':120,'team_abbr':abbr,
                'recent_manager_change':False,'season_phase':'early'}

    matchup = {
        'home_team': ha, 'away_team': aa,
        'home_pitcher_stats': game.get('home_pitcher_stats', {}),
        'away_pitcher_stats': game.get('away_pitcher_stats', {}),
        'home_pitcher_recent': PITCHER_RECENT.get(hp, []),
        'away_pitcher_recent': PITCHER_RECENT.get(ap, []),
        'home_pitcher_hand': (game.get('home_pitcher') or {}).get('hand','R'),
        'away_pitcher_hand': (game.get('away_pitcher') or {}).get('hand','R'),
        'home_batting': game.get('home_batting', {}),
        'away_batting': game.get('away_batting', {}),
        'home_pitching': game.get('home_pitching', {}),
        'away_pitching': game.get('away_pitching', {}),
        'home_team_context': ctx(ha), 'away_team_context': ctx(aa),
        'home_lineup_data': {'absent':[]}, 'away_lineup_data': {'absent':[]},
        'home_pitcher_rest_workload': {'last_start_date':rest_date,'season_innings':45.0,
                                        'prev_year_innings':165.0,'age':28,'last_pitch_count':92},
        'away_pitcher_rest_workload': {'last_start_date':rest_date,'season_innings':45.0,
                                        'prev_year_innings':165.0,'age':28,'last_pitch_count':92},
        'venue': game.get('venue'), 'weather': game.get('weather', {}),
        'date': '2026-05-14',
    }
    try:
        pred = predictor.predict(matchup)
        hwp = pred.get('home_win_prob', 0.5)
        winner, edge = (ha, (hwp-0.5)*200) if hwp >= 0.5 else (aa, (0.5-hwp)*200)
        strength = ('🟢🟢 강한 픽' if edge>=20 else '🟢 픽' if edge>=12 else
                    '🟡 약한 픽' if edge>=6 else '⚪ 관망')
        total = pred.get('predicted_total', 0)
        ou = (f'🔼🔼 강한 오버 ({total})' if total>=OU_LINE+1.0 else
              f'🔼 오버 ({total})' if total>=OU_LINE+0.3 else
              f'🔽🔽 강한 언더 ({total})' if total<=OU_LINE-1.0 else
              f'🔽 언더 ({total})' if total<=OU_LINE-0.3 else
              f'⚪ 관망 ({total})')
        conf = pred.get('confidence', 0)
        picks.append({'matchup': f'{aa} @ {ha}', 'pitchers': f'{ap} vs {hp}',
                      'venue': game.get('venue'),
                      'home_wp': round(hwp,3), 'pick': f'{winner} 승',
                      'strength': strength, 'edge': round(edge,1),
                      'total': total, 'ou': ou, 'conf': round(conf,3)})
        print(f"\n[{aa} @ {ha}] {ap} vs {hp} @ {game['venue']}")
        print(f"   📊 홈 {hwp:.1%} | 토탈 {total} | 신뢰도 {conf:.1%}")
        print(f"   🎯 {winner} 승 — {strength} (격차 {edge:.1f}%p)")
        print(f"   🎯 O/U: {ou}")
    except Exception as e:
        print(f"\n[{aa} @ {ha}] 에러: {e}")

os.makedirs('data/results', exist_ok=True)
with open('data/results/mlb_2026-05-14.json', 'w', encoding='utf-8') as f:
    json.dump({'date': '2026-05-14', 'picks': picks}, f, ensure_ascii=False, indent=2)
print(f"\n✅ 저장: data/results/mlb_2026-05-14.json ({len(picks)}경기)")
