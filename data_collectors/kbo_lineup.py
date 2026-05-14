"""
data_collectors/kbo_lineup.py
==============================
KBO 오늘 라인업 + 결장(IL/휴식) 수집

KBO 공식 ws 에는 라인업 API 가 없음. 대안 소스:
1. 네이버 스포츠 게임센터 (https://sports.news.naver.com/kbaseball/record/index)
2. 각 구단 공식 (LG/두산 등 — 셀럽 일정 페이지)
3. 톱스타뉴스 등 일일 라인업 기사

이걸로 predictor 의 `home_lineup_data` / `away_lineup_data` 에 들어가는
{'absent': [{'name':..., 'position':...}], 'starters': [...]} 만들기.

사용:
    from data_collectors.kbo_lineup import KBOLineup
    l = KBOLineup()
    out = l.get_today_lineup('두산')
    # → {'absent': [...], 'starters': [{'order':1,'name':'정수빈',...}]}
"""
from __future__ import annotations
import os, re, time, json
from datetime import datetime
from typing import Dict, List
import requests
from bs4 import BeautifulSoup


class KBOLineup:

    NAVER_GAME = "https://m.sports.naver.com/kbaseball/schedule/index"
    NAVER_API = "https://api-gw.sports.naver.com/schedule/games"

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
                      'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0',
        'Accept': 'application/json',
        'Referer': 'https://m.sports.naver.com/',
    }

    TEAM_NAVER_CODES = {
        '두산': 'OB', 'LG': 'LG', '키움': 'WO', '한화': 'HH', '롯데': 'LT',
        'KIA': 'HT', '삼성': 'SS', 'NC': 'NC', 'SSG': 'SK', 'KT': 'KT',
    }

    def __init__(self, cache_dir: str = "data/cache/kbo_lineup", delay: float = 0.4):
        self.cache_dir = cache_dir
        self.delay = delay
        os.makedirs(cache_dir, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    # ------------------------------------------------------------
    # 1. 네이버 API 로 오늘 경기 id 얻기
    # ------------------------------------------------------------
    def get_today_game_ids(self, date: str = None) -> List[str]:
        if date is None:
            date = datetime.now().strftime('%Y%m%d')
        url = f"{self.NAVER_API}?fields=basic&upperCategoryId=kbaseball&date={date}"
        try:
            res = self.session.get(url, timeout=10)
            data = res.json()
            return [g['gameId'] for g in data.get('result', {}).get('games', [])]
        except Exception as e:
            print(f"[KBOLineup] 경기ID 조회 실패: {e}")
            return []

    # ------------------------------------------------------------
    # 2. 게임 라인업 (네이버 게임센터)
    # ------------------------------------------------------------
    def get_lineup_by_game_id(self, game_id: str) -> Dict:
        """네이버 game_id 로 양 팀 라인업 조회"""
        url = f"https://api-gw.sports.naver.com/game/{game_id}/lineup"
        try:
            res = self.session.get(url, timeout=10)
            data = res.json().get('result', {})
            home_l = self._parse_lineup_block(data.get('home', {}))
            away_l = self._parse_lineup_block(data.get('away', {}))
            time.sleep(self.delay)
            return {'home': home_l, 'away': away_l}
        except Exception as e:
            print(f"[KBOLineup] 라인업 {game_id} 실패: {e}")
            return {'home': {}, 'away': {}}

    def _parse_lineup_block(self, block: Dict) -> Dict:
        starters = []
        for p in block.get('batterList', []):
            starters.append({
                'order': p.get('battingOrder'),
                'name': p.get('playerName'),
                'position': p.get('position'),
                'hand': p.get('hitType'),  # 우타/좌타/스위치
            })
        return {
            'team': block.get('teamName'),
            'starters': starters,
            'starting_pitcher': block.get('startingPitcher', {}).get('playerName'),
        }

    # ------------------------------------------------------------
    # 3. IL/결장 (네이버 부상자 명단)
    # ------------------------------------------------------------
    def get_team_injuries(self, team: str) -> List[Dict]:
        cache = self._cache(f"il_{team}")
        if self._fresh(cache):
            return json.loads(open(cache, encoding='utf-8').read())

        code = self.TEAM_NAVER_CODES.get(team, team)
        url = f"https://api-gw.sports.naver.com/team/kbo/{code}/players?status=injured"
        try:
            res = self.session.get(url, timeout=10)
            data = res.json().get('result', {}).get('players', [])
            injuries = [
                {
                    'name': p.get('playerName'),
                    'position': p.get('position'),
                    'reason': p.get('injuryReason'),
                    'return_date': p.get('expectedReturnDate'),
                }
                for p in data if p.get('status') == 'INJURED'
            ]
            self._save(cache, injuries)
            time.sleep(self.delay)
            return injuries
        except Exception as e:
            print(f"[KBOLineup] IL {team} 실패: {e}")
            return []

    # ------------------------------------------------------------
    # 4. 통합 호출 (matchup 키 형식)
    # ------------------------------------------------------------
    def get_lineup_data(self, team: str, game_id: str = None) -> Dict:
        """
        predictor.py 가 기대하는 형식:
        {'absent': [{'name':..., 'position':...}, ...],
         'starters': [{'order':1, 'name':..., 'position':...}, ...]}
        """
        injuries = self.get_team_injuries(team)
        absent = [{'name': i['name'], 'position': i.get('position', '')}
                  for i in injuries]
        starters = []

        if game_id:
            lu = self.get_lineup_by_game_id(game_id)
            for side in ('home', 'away'):
                blk = lu.get(side, {})
                if blk.get('team') == team:
                    starters = blk.get('starters', [])
                    break

        return {'absent': absent, 'starters': starters}

    # ------------------------------------------------------------
    # 헬퍼
    # ------------------------------------------------------------
    def _cache(self, key: str) -> str:
        today = datetime.now().strftime('%Y-%m-%d')
        return os.path.join(self.cache_dir, f"{today}_{key}.json")

    def _fresh(self, path: str, hours: int = 2) -> bool:
        if not os.path.exists(path):
            return False
        return (time.time() - os.path.getmtime(path)) / 3600 < hours

    def _save(self, path: str, data) -> None:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    l = KBOLineup()
    ids = l.get_today_game_ids()
    print(f"오늘 경기 ID: {ids}")
    for team in ['두산', 'LG', 'KT']:
        print(f"\n=== {team} ===")
        print(json.dumps(l.get_lineup_data(team), ensure_ascii=False, indent=2))
