"""qlstats adapter.

Verified against the bundled balance.py plugin:
  - URL shape:  f"http://{host}/{api}/" + "+".join(ids)   (:127-131, :277)
  - value:      players[i][<game_type>]["elo"]            (:411)
  - modes:      SUPPORTED_GAMETYPES + duel/ffa            (:48-56)
No auth.
"""
import requests

from ui.rank_providers.base import PROVIDER_TIMEOUT, RankProvider, RankResult

# balance.py's SUPPORTED_GAMETYPES plus the two it supports externally only.
# qlstats uses the same short codes QLSM does, so this is an identity map
# restricted to what qlstats actually rates.
_SUPPORTED = {'ad', 'ca', 'ctf', 'dom', 'ft', 'tdm', 'duel', 'ffa'}

DEFAULT_RATING_SYSTEM = 'elo'


class QlstatsProvider(RankProvider):
    def map_game_type(self, qlsm_gametype):
        code = (qlsm_gametype or '').strip().lower()
        return code if code in _SUPPORTED else None

    def fetch_ratings(self, steam_ids, game_type, instance_id=None):
        if not steam_ids or not game_type:
            return {}
        system = self.extra.get('rating_system') or DEFAULT_RATING_SYSTEM
        url = f"{self.base_url}/{system}/" + '+'.join(str(s) for s in steam_ids)
        try:
            response = requests.get(url, timeout=PROVIDER_TIMEOUT)
        except requests.RequestException as exc:
            self._log_failure(instance_id, exc=exc)
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

        untracked_raw = body.get('untracked')
        untracked = ({str(sid) for sid in untracked_raw}
                     if isinstance(untracked_raw, list) else set())
        players = body.get('players')
        out = {}
        for entry in players if isinstance(players, list) else []:
            if not isinstance(entry, dict):
                continue
            # str(), never int() — balance.py:308 does int() and that key type
            # would miss every lookup on the frontend.
            steam_id = str(entry.get('steamid') or '').strip()
            if not steam_id or steam_id in untracked:
                continue
            bucket = entry.get(game_type)
            if not isinstance(bucket, dict):
                continue
            elo = bucket.get('elo')
            if elo is None:
                continue
            # balance.py:326-327 treats elo==0 AND games==0 as "the API has
            # nothing for this player" and substitutes DEFAULT_RATING (1500).
            # A read-only display does not invent a number: omit the player so
            # the cell shows a dash. Without this the cell renders a literal 0.
            if elo == 0 and bucket.get('games') == 0:
                continue
            try:
                rating = float(elo)
            except (TypeError, ValueError):
                continue
            out[steam_id] = RankResult(
                rating=rating, display=str(elo), provisional=False,
            )
        return out
