"""
data_collectors/kbo_statiz.py
=============================
Statiz (statiz.sporki.com) 크롤러

KBO 공식 ws API 에 없는 고급 지표 보강:
- wRC+ / wOBA / ISO / BABIP (팀 + 개인)
- DRS / UZR-유사 수비 지표
- 득점권 타율 (RISP)
- vs 좌투/우투 OPS
- 투수 FIP / xFIP / SIERA / K-BB%
- BABIP 운빨

kbo_crawler_v3 와 함께 호출해서 matchup_data 의 advanced_batting 키 채움.

설계:
- Statiz 가 SSR 페이지라 BeautifulSoup 파싱
- 캐시: 같은 날 같은 팀 재요청 안 함
- robots.txt 준수: 0.5초 슬립

사용법:
    from data_collectors.kbo_statiz import KBOStatiz
    s = KBOStatiz()
    bat = s.get_team_advanced_batting('두산', 2026)
    # → {'wrc_plus': 108, 'woba': 0.332, 'iso': 0.158, ...}
"""
from __future__ import annotations
import os
import re
import time
import json
from datetime import datetime
from typing import Dict, List, Optional
import requests
from bs4 import BeautifulSoup


class KBOStatiz:
    """Statiz 고급 지표 크롤러"""

    BASE = "https://statiz.sporki.com"
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'ko-KR,ko;q=0.9',
        'Referer': 'https://statiz.sporki.com/',
    }

    # Statiz 팀 코드 (URL ?t= 파라미터)
    TEAM_CODES = {
        '두산': 1, 'LG': 2, '롯데': 3, '삼성': 4, 'KIA': 5,
        '한화': 6, 'SSG': 7, 'NC': 8, '키움': 9, 'KT': 10,
    }

    def __init__(self, cache_dir: str = "data/cache/kbo_statiz", delay: float = 0.5):
        self.cache_dir = cache_dir
        self.delay = delay
        os.makedirs(cache_dir, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    # ------------------------------------------------------------
    # 1. 팀 고급 타격 (wRC+, wOBA, ISO, BABIP)
    # ------------------------------------------------------------
    def get_team_advanced_batting(self, team: str, year: int = None) -> Dict:
        if year is None:
            year = datetime.now().year
        cache = self._cache_path(f"team_bat_{team}_{year}")
        if self._is_fresh(cache):
            return json.loads(open(cache, encoding='utf-8').read())

        tc = self.TEAM_CODES.get(team)
        if tc is None:
            return {}
        url = f"{self.BASE}/team/?year={year}&t={tc}"
        try:
            res = self.session.get(url, timeout=15)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, 'lxml')

            stats = self._parse_team_batting_table(soup)
            self._save_cache(cache, stats)
            time.sleep(self.delay)
            return stats
        except Exception as e:
            print(f"[Statiz] team batting {team} 실패: {e}")
            return {}

    def _parse_team_batting_table(self, soup: BeautifulSoup) -> Dict:
        """Statiz 팀 페이지의 타격 테이블에서 wRC+/wOBA/ISO/BABIP 추출"""
        result = {}
        # Statiz 는 .stats_box 또는 #team_batting 류 테이블
        for table in soup.select('table'):
            headers = [th.get_text(strip=True) for th in table.select('thead th')]
            if not any(h in headers for h in ('wRC+', 'wOBA', 'OPS+', 'ISO')):
                continue
            # 첫 데이터 행이 시즌 합계
            tr = table.select_one('tbody tr')
            if not tr:
                continue
            cells = [td.get_text(strip=True) for td in tr.find_all('td')]
            for h, v in zip(headers, cells):
                key = self._norm_key(h)
                if key in ('wrc_plus', 'woba', 'iso', 'babip', 'ops_plus',
                           'avg', 'obp', 'slg', 'ops', 'risp_avg', 'wpa'):
                    result[key] = self._to_float(v)
            break
        return result

    # ------------------------------------------------------------
    # 2. 팀 vs 좌/우투 OPS
    # ------------------------------------------------------------
    def get_team_split_vs_handedness(self, team: str, year: int = None) -> Dict:
        if year is None:
            year = datetime.now().year
        cache = self._cache_path(f"team_split_{team}_{year}")
        if self._is_fresh(cache):
            return json.loads(open(cache, encoding='utf-8').read())

        tc = self.TEAM_CODES.get(team)
        url = f"{self.BASE}/team/?year={year}&t={tc}&m=split"
        try:
            res = self.session.get(url, timeout=15)
            soup = BeautifulSoup(res.text, 'lxml')

            split = {'vs_lhp': {}, 'vs_rhp': {}}
            for table in soup.select('table'):
                caption = (table.find('caption') or table.find_previous('h3') or
                           table.find_previous('h4'))
                cap_text = caption.get_text(strip=True) if caption else ''
                if '좌투' in cap_text or 'LHP' in cap_text:
                    target = split['vs_lhp']
                elif '우투' in cap_text or 'RHP' in cap_text:
                    target = split['vs_rhp']
                else:
                    continue
                tr = table.select_one('tbody tr')
                if not tr:
                    continue
                headers = [th.get_text(strip=True) for th in table.select('thead th')]
                cells = [td.get_text(strip=True) for td in tr.find_all('td')]
                for h, v in zip(headers, cells):
                    k = self._norm_key(h)
                    if k in ('avg', 'obp', 'slg', 'ops', 'wrc_plus'):
                        target[k] = self._to_float(v)
            self._save_cache(cache, split)
            time.sleep(self.delay)
            return split
        except Exception as e:
            print(f"[Statiz] split {team} 실패: {e}")
            return {}

    # ------------------------------------------------------------
    # 3. 팀 수비 (DRS-유사)
    # ------------------------------------------------------------
    def get_team_defense(self, team: str, year: int = None) -> Dict:
        if year is None:
            year = datetime.now().year
        cache = self._cache_path(f"team_def_{team}_{year}")
        if self._is_fresh(cache):
            return json.loads(open(cache, encoding='utf-8').read())

        tc = self.TEAM_CODES.get(team)
        url = f"{self.BASE}/team/?year={year}&t={tc}&m=fielding"
        try:
            res = self.session.get(url, timeout=15)
            soup = BeautifulSoup(res.text, 'lxml')
            result = {}
            for table in soup.select('table'):
                headers = [th.get_text(strip=True) for th in table.select('thead th')]
                if not any(h in headers for h in ('수비효율', 'DER', 'DRS', '실책')):
                    continue
                tr = table.select_one('tbody tr')
                if not tr:
                    continue
                cells = [td.get_text(strip=True) for td in tr.find_all('td')]
                for h, v in zip(headers, cells):
                    k = self._norm_key(h)
                    if k in ('der', 'drs', 'errors', 'dp_rate', 'framing', 'cs_rate'):
                        result[k] = self._to_float(v)
                break
            self._save_cache(cache, result)
            time.sleep(self.delay)
            return result
        except Exception as e:
            print(f"[Statiz] defense {team} 실패: {e}")
            return {}

    # ------------------------------------------------------------
    # 4. 개인 투수 고급 지표 (FIP/xFIP/SIERA/K-BB%)
    # ------------------------------------------------------------
    def get_pitcher_advanced(self, pitcher_name: str, year: int = None) -> Dict:
        if year is None:
            year = datetime.now().year
        cache = self._cache_path(f"pitcher_{pitcher_name}_{year}")
        if self._is_fresh(cache):
            return json.loads(open(cache, encoding='utf-8').read())

        # 이름으로 검색 → playerid 추출
        sr_url = f"{self.BASE}/search?q={pitcher_name}"
        try:
            res = self.session.get(sr_url, timeout=15)
            soup = BeautifulSoup(res.text, 'lxml')
            link = soup.select_one('a[href*="/player/?p_no="]')
            if not link:
                return {}
            pid = re.search(r'p_no=(\d+)', link['href']).group(1)
            time.sleep(self.delay)

            # 투수 상세
            url = f"{self.BASE}/player/?m=playerinfo&p_no={pid}&t=2&y={year}"
            res = self.session.get(url, timeout=15)
            soup = BeautifulSoup(res.text, 'lxml')

            stats = {}
            for table in soup.select('table'):
                headers = [th.get_text(strip=True) for th in table.select('thead th')]
                if not any(h in headers for h in ('FIP', 'xFIP', 'SIERA', 'K-BB%', 'CSW%')):
                    continue
                tr = table.select_one('tbody tr')
                if not tr:
                    continue
                cells = [td.get_text(strip=True) for td in tr.find_all('td')]
                for h, v in zip(headers, cells):
                    k = self._norm_key(h)
                    if k in ('fip', 'xfip', 'siera', 'k_bb_pct', 'whip',
                             'k_per_9', 'bb_per_9', 'hr_per_9', 'era', 'csw_pct',
                             'babip', 'lob_pct'):
                        stats[k] = self._to_float(v)
                break

            self._save_cache(cache, stats)
            time.sleep(self.delay)
            return stats
        except Exception as e:
            print(f"[Statiz] pitcher {pitcher_name} 실패: {e}")
            return {}

    # ------------------------------------------------------------
    # 5. 통합 호출
    # ------------------------------------------------------------
    def get_all_for_team(self, team: str, year: int = None) -> Dict:
        """matchup_data 에 그대로 넣을 수 있는 dict 반환"""
        adv_bat = self.get_team_advanced_batting(team, year)
        splits = self.get_team_split_vs_handedness(team, year)
        defense = self.get_team_defense(team, year)
        return {
            'advanced_batting': {
                'wrc_plus': adv_bat.get('wrc_plus', 100),
                'woba': adv_bat.get('woba', 0.320),
                'iso': adv_bat.get('iso', 0.140),
                'babip': adv_bat.get('babip', 0.300),
                'risp_avg': adv_bat.get('risp_avg', 0.255),
                'vs_power_pitcher': {'ops': splits.get('vs_rhp', {}).get('ops', 0.720)},
                'vs_control_pitcher': {'ops': splits.get('vs_lhp', {}).get('ops', 0.720)},
            },
            'fielding': {
                'drs': defense.get('drs', 0),
                'der': defense.get('der', 0.690),
                'errors': defense.get('errors', 0),
                'framing_runs': defense.get('framing', 0),
                'cs_pct': defense.get('cs_rate', 0.30),
            },
        }

    # ------------------------------------------------------------
    # 헬퍼
    # ------------------------------------------------------------
    @staticmethod
    def _norm_key(h: str) -> str:
        return {
            'wRC+': 'wrc_plus', 'wOBA': 'woba', 'ISO': 'iso', 'BABIP': 'babip',
            'AVG': 'avg', '타율': 'avg', 'OBP': 'obp', '출루': 'obp',
            'SLG': 'slg', '장타': 'slg', 'OPS': 'ops', 'OPS+': 'ops_plus',
            '득점권': 'risp_avg', 'WPA': 'wpa',
            'DER': 'der', '수비효율': 'der', 'DRS': 'drs',
            '실책': 'errors', 'E': 'errors',
            'DP': 'dp_rate', '병살': 'dp_rate',
            '프레이밍': 'framing', 'CS%': 'cs_rate', '도루저지': 'cs_rate',
            'FIP': 'fip', 'xFIP': 'xfip', 'SIERA': 'siera',
            'K-BB%': 'k_bb_pct', 'WHIP': 'whip',
            'K/9': 'k_per_9', 'BB/9': 'bb_per_9', 'HR/9': 'hr_per_9',
            'ERA': 'era', 'CSW%': 'csw_pct', 'LOB%': 'lob_pct',
        }.get(h, h.lower())

    @staticmethod
    def _to_float(v: str) -> float:
        try:
            return float(v.replace(',', '').replace('%', '').strip())
        except Exception:
            return 0.0

    def _cache_path(self, key: str) -> str:
        today = datetime.now().strftime('%Y-%m-%d')
        return os.path.join(self.cache_dir, f"{today}_{key}.json")

    def _is_fresh(self, path: str, max_age_hours: int = 6) -> bool:
        if not os.path.exists(path):
            return False
        age = (time.time() - os.path.getmtime(path)) / 3600
        return age < max_age_hours

    def _save_cache(self, path: str, data) -> None:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


# ============================================================
# 빠른 테스트
# ============================================================
if __name__ == "__main__":
    s = KBOStatiz()
    for team in ['두산', 'KT', '한화']:
        print(f"\n=== {team} ===")
        all_data = s.get_all_for_team(team)
        print(json.dumps(all_data, ensure_ascii=False, indent=2))
