"""Slipgate adapter.

Verified against Slipgate's own minqlxtended plugin v1.10.1:
  - auth:   Authorization: Bearer <sgs_...>                (:456)
  - bulk:   POST /ratings/bulk {steam_ids, game_type}      (:2496-2507)
  - 404 on the single-player path means unranked           (:2427)
  - TWO unranked shapes: found=False, and display=None     (:2542-2547)
  - codes:  the 11 long forms in GAMETYPE_CODES            (:124-134)

Only the bulk POST is ever called. The single-player path above is documented
for reference and unused.

'display' is rendered whole and never parsed: the field is named display, not
rating, and may well be a label like "1650 (Gold)".
"""
import requests

from ui.rank_providers.base import PROVIDER_TIMEOUT, RankProvider, RankResult

# QLSM's short codes -> Slipgate's own vocabulary. All 11 of GAMETYPE_CODES:
# four differ, seven pass through. Sending 'har' or '1f' unmapped returns
# nothing at all, with no error — exactly the undiagnosable empty column this
# mapping exists to prevent.
#
# '1fctf' and 'ictf' from LiveServerStatusModal.jsx:26 are NOT mapped: they are
# speculative aliases in a set whose own comment says "and common aliases", and
# neither runtime emits them. '1f' is the real short code
# (minqlx/_core.py:54-55, minqlxtended/_enums.py:357).
_GAME_TYPE_MAP = {
    'ca': 'ca', 'ctf': 'ctf', 'tdm': 'tdm', 'ft': 'ft',
    'ffa': 'ffa', 'duel': 'duel', 'ad': 'ad',
    'har': 'harvester', 'dom': 'domination', 'rr': 'redrover',
    '1f': '1flag',
}


class SlipgateProvider(RankProvider):
    def map_game_type(self, qlsm_gametype):
        return _GAME_TYPE_MAP.get((qlsm_gametype or '').strip().lower())

    def _headers(self):
        headers = {}
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        return headers

    def fetch_ratings(self, steam_ids, game_type, instance_id=None):
        if not steam_ids or not game_type:
            return {}
        payload = {'steam_ids': [str(s) for s in steam_ids], 'game_type': game_type}
        try:
            response = requests.post(
                f'{self.base_url}/ratings/bulk',
                json=payload, headers=self._headers(), timeout=PROVIDER_TIMEOUT,
            )
        except requests.RequestException as exc:
            self._log_failure(instance_id, exc=exc)
            return {}
        if response.status_code == 404:
            # Belt-and-braces. The plugin documents a 404 only on the
            # single-player path (:2427), which QLSM never calls; nothing
            # documents one on the bulk POST. Kept because if it ever happens it
            # means unranked, not an error, and must not be logged as a failure.
            return {}
        if response.status_code != 200:
            self._log_failure(instance_id, status_code=response.status_code)
            return {}
        try:
            body = response.json()
        except ValueError:
            self._log_failure(instance_id, status_code=response.status_code)
            return {}
        if not isinstance(body, dict):
            return {}

        players = body.get('players')
        out = {}
        for entry in players if isinstance(players, list) else []:
            if not isinstance(entry, dict):
                continue
            steam_id = str(entry.get('steam_id') or '').strip()
            if not steam_id:
                continue
            # Shape one: explicitly not found.
            if not entry.get('found'):
                continue
            display = entry.get('display')
            # Shape two: found, but no rating to show. Same meaning, and an
            # adapter that checks only the first renders a wrong cell here.
            if display is None:
                continue
            out[steam_id] = RankResult(
                rating=None,                    # display is not necessarily numeric
                display=str(display),           # verbatim, never parsed
                provisional=bool(entry.get('provisional')),
            )
        return out
