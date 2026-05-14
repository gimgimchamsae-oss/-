"""
data_collectors/npb_advanced.py
================================
NPB 보조 데이터 수집 (npb_collector 보강)

NPB는 미국처럼 Statcast/wRC+ 공개 안 함. 대신 무료로 긁을 수 있는 곳:
- 1.02 Essence (https://1point02.jp/op/) — wOBA/BABIP 일부 무료
- 야구 데이터 Freak (baseball-freak.com) — 팀별 vs L/R, 득점권
- Yahoo Japan Sports — 라인업, 부상자
- Sponichi — 예고선발 + 휴식일

기존 npb_collector.py 가 npb.jp/npbstats 만 보니까 이걸로 wOBA/RISP/vs L-R 추가.

사용:
    from data_collectors.npb_advanced import NPBAdvanced
    a = NPBAdvanced()
    bat = a.get_team_split('阪神', 2026)
    # → {'vs_lhp': {'ops': .760}, 'vs_rhp': {'ops': .740}, 'risp_avg': .265}
"""
from __future__ import annotations
import os, re, time, json
from datetime import datetime
from typing import Dict, List, Optional
import requests
from bs4 import BeautifulSoup


class NPBAdvanced:

    DATA_FREAK = "https://baseball-freak.com"
    ONE02 = "https://1point02.jp/op"
    YAHOO_JP = "https://baseball.yahoo.co.jp/npb"

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'ja-JP,ja;q=0.9,en;q=0.8',
    }

    # NPB 팀명 → 영문 약자 매핑 (baseball-freak url 슬러그)
    TEAM_SLUG = {
        '巨人': 'giants', '阪神': 'tigers', '広島': 'carp', '中日': 'dragons',
        'DeNA': 'baystars', 'ヤクルト': 'swallows',
        'ソフトバンク': 'hawks', '西武': 'lions', '楽天': 'eagles',
        'ロッテ': 'marines', '日本ハム': 'fighters', 'オリックス': 'buffaloes',
    }

    def __init__(self, cache_dir: str = "data/cache/npb_adv", delay: float = 0.5):
        self.cache_dir = cache_dir
        self.delay = delay
        os.makedirs(cache_dir, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    # ------------------------------------------------------------
    # 1. 팀 vs 좌/우투 + 득점권 (baseball-freak)
    # ------------------------------------------------------------
    def get_team_split(self, team_jp: str, year: int = None) -> Dict:
        if year is None:
            year = datetime.now().year
        cache = self._cache(f"split_{team_jp}_{year}")
        if self._fresh(cache):
            return json.loads(open(cache, encoding='utf-8').read())

        slug = self.TEAM_SLUG.get(team_jp)
        if not slug:
            return {}
        url = f"{self.DATA_FREAK}/team/{slug}/batting/split"

        try:
            res = self.session.get(url, timeout=15)
            soup = BeautifulSoup(res.text, 'lxml')
            result = {'vs_lhp': {}, 'vs_rhp': {}, 'risp_avg': 0.0}

            for tbl in soup.select('table'):
                cap = tbl.find('caption')
                ctext = cap.get_text(strip=True) if cap else ''
                target_key = None
                if '対左' in ctext or '左投手' in ctext:
                    target_key = 'vs_lhp'
                elif '対右' in ctext or '右投手' in ctext:
                    target_key = 'vs_rhp'
                elif '得点圏' in ctext or '走者' in ctext:
                    target_key = 'risp'
                if not target_key:
                    continue
                tr = tbl.select_one('tbody tr')
                if not tr:
                    continue
                hd = [th.get_text(strip=True) for th in tbl.select('thead th')]
                cells = [td.get_text(strip=True) for td in tr.find_all('td')]
                row = dict(zip(hd, cells))
                if target_key in ('vs_lhp', 'vs_rhp'):
                    result[target_key] = {
                        'avg': self._f(row.get('打率')),
                        'obp': self._f(row.get('出塁率')),
                        'slg': self._f(row.get('長打率')),
                        'ops': self._f(row.get('OPS')),
                    }
                elif target_key == 'risp':
                    result['risp_avg'] = self._f(row.get('打率'))

            self._save(cache, result)
            time.sleep(self.delay)
            return result
        except Exception as e:
            print(f"[NPBAdv] split {team_jp} 실패: {e}")
            return {}

    # ------------------------------------------------------------
    # 2. 팀 고급 지표 (1.02 무료 부분)
    # ------------------------------------------------------------
    def get_team_advanced(self, team_jp: str, year: int = None) -> Dict:
        """1.02 의 wOBA / BABIP / 수비 (제한적 무료)"""
        if year is None:
            year = datetime.now().year
        cache = self._cache(f"adv_{team_jp}_{year}")
        if self._fresh(cache):
            return json.loads(open(cache, encoding='utf-8').read())

        url = f"{self.ONE02}/team/{year}/index.html"
        try:
            res = self.session.get(url, timeout=15)
            soup = BeautifulSoup(res.text, 'lxml')
            result = {}
            for tr in soup.select('table tbody tr'):
                if team_jp not in tr.get_text():
                    continue
                cells = [td.get_text(strip=True) for td in tr.find_all('td')]
                # 1.02 컬럼: 順位, 球団, 試合, ..., wOBA, wRAA, BABIP, ...
                hd = [th.get_text(strip=True) for th in tr.find_parent('table').select('thead th')]
                row = dict(zip(hd, cells))
                result = {
                    'woba': self._f(row.get('wOBA')),
                    'wraa': self._f(row.get('wRAA')),
                    'babip': self._f(row.get('BABIP')),
                    'iso': self._f(row.get('ISO')),
                }
                break
            self._save(cache, result)
            time.sleep(self.delay)
            return result
        except Exception as e:
            print(f"[NPBAdv] adv {team_jp} 실패: {e}")
            return {}

    # ------------------------------------------------------------
    # 3. 라인업 + IL (Yahoo Japan)
    # ------------------------------------------------------------
    def get_today_lineup(self, team_jp: str) -> Dict:
        """오늘 라인업 + IL (Yahoo Japan Sports)"""
        slug = self.TEAM_SLUG.get(team_jp, team_jp)
        url = f"{self.YAHOO_JP}/teams/{slug}/lineup/"
        try:
            res = self.session.get(url, timeout=15)
            soup = BeautifulSoup(res.text, 'lxml')

            absent = []
            for el in soup.select('.injury, .il-player, [class*="DNP"]'):
                name = el.get_text(strip=True)
                pos = el.get('data-position') or ''
                if name:
                    absent.append({'name': name, 'position': pos})

            starters = []
            for row in soup.select('table.lineup tbody tr'):
                tds = row.find_all('td')
                if len(tds) >= 2:
                    starters.append({
                        'order': self._i(tds[0].get_text()),
                        'name': tds[1].get_text(strip=True),
                    })
            time.sleep(self.delay)
            return {'absent': absent, 'starters': starters}
        except Exception as e:
            print(f"[NPBAdv] lineup {team_jp} 실패: {e}")
            return {'absent': [], 'starters': []}

    # ------------------------------------------------------------
    # 4. 통합
    # ------------------------------------------------------------
    def get_all_for_team(self, team_jp: str, year: int = None) -> Dict:
        split = self.get_team_split(team_jp, year)
        adv = self.get_team_advanced(team_jp, year)
        lineup = self.get_today_lineup(team_jp)
        return {
            'advanced_batting': {
                'wrc_plus': 100,  # NPB 공개 없음
                'woba': adv.get('woba', 0.320),
                'iso': adv.get('iso', 0.130),
                'babip': adv.get('babip', 0.290),
                'risp_avg': split.get('risp_avg', 0.260),
                'vs_power_pitcher': {'ops': split.get('vs_rhp', {}).get('ops', 0.720)},
                'vs_control_pitcher': {'ops': split.get('vs_lhp', {}).get('ops', 0.720)},
            },
            'fielding': {},
            'lineup_data': lineup,
        }

    @staticmethod
    def _f(v):
        try:
            return float(str(v).replace(',', '').replace('%', '').strip())
        except Exception:
            return 0.0

    @staticmethod
    def _i(v):
        try:
            return int(str(v).strip())
        except Exception:
            return 0

    def _cache(self, key: str) -> str:
        today = datetime.now().strftime('%Y-%m-%d')
        return os.path.join(self.cache_dir, f"{today}_{key}.json")

    def _fresh(self, path: str, hours: int = 6) -> bool:
        if not os.path.exists(path):
            return False
        return (time.time() - os.path.getmtime(path)) / 3600 < hours

    def _save(self, path: str, data) -> None:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    a = NPBAdvanced()
    for t in ['阪神', '巨人', 'ソフトバンク']:
        print(f"\n=== {t} ===")
        print(json.dumps(a.get_all_for_team(t), ensure_ascii=False, indent=2))
