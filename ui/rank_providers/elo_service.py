"""Thunderdome elo-service adapter.

Verified against the bundled ranked.py plugin:
  - bulk:   GET /players?ids=a,b,c&mode=<mode>
  - single: GET /player/{steam_id}?mode=<mode>, 404 = unranked  (:666)
  - RATING: sort_score or mu                                    (:466, :672)
  - auth:   X-API-Key

:597 is a different endpoint's 404 (the GET /player/{steam_id} name lookup,
no ?mode=) and is not what this adapter models.

There is no 'rating' key on either endpoint. An adapter that reads one returns
None for every player against a perfectly healthy service.
"""
import requests

from ui.rank_providers.base import PROVIDER_TIMEOUT, RankProvider, RankResult


class ThunderdomeEloProvider(RankProvider):
    def map_game_type(self, qlsm_gametype):
        """Always None: 'mode' here is a service-specific pool name such as
        'ffa_auto', which corresponds to no QL gametype. This provider is
        configured through the game_type override column instead."""
        return None

    def _headers(self):
        return {'X-API-Key': self.api_key} if self.api_key else {}

    def fetch_ratings(self, steam_ids, game_type, instance_id=None):
        if not steam_ids or not game_type:
            return {}
        params = {'ids': ','.join(str(s) for s in steam_ids), 'mode': game_type}
        try:
            response = requests.get(
                f'{self.base_url}/players',
                params=params, headers=self._headers(), timeout=PROVIDER_TIMEOUT,
            )
        except requests.RequestException as exc:
            self._log_failure(instance_id, exc=exc)
            return {}
        if response.status_code == 404:
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

        out = {}
        for steam_id, entry in body.items():
            # A null entry means the service knows nothing about that player.
            if not isinstance(entry, dict):
                continue
            # `or`, not `is None`. ranked.py:466 and :672 both read
            # int(d.get("sort_score") or d["mu"]), so a sort_score of 0 is
            # treated as absent and mu wins. An `is None` check would show 0
            # in QLSM for a player whose in-game !rating shows a real number.
            value = entry.get('sort_score') or entry.get('mu')
            if value is None:
                continue
            try:
                rating = float(value)
            except (TypeError, ValueError):
                continue
            out[str(steam_id)] = RankResult(
                rating=rating,
                display=f'{rating:g}',
                provisional=False,
            )
        return out
