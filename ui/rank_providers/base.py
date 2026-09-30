"""The shared rank-provider interface.

Every adapter converts its own provider's shape into RankResult and swallows
its own failures. Callers never see a provider exception and never see a
provider's own key type — see the string-key note on fetch_ratings.
"""
import logging
from abc import ABC, abstractmethod
from typing import TypedDict

logger = logging.getLogger(__name__)

# Connect and read timeouts for every outbound provider call. Short on purpose:
# this rides a synchronous request the UI polls.
PROVIDER_TIMEOUT = (3, 3)


class RankResult(TypedDict):
    rating: float | None   # numeric when the provider gives one; carried, not rendered
    display: str           # what the table actually shows
    provisional: bool      # carried, not rendered in this slice


class RankProvider(ABC):
    def __init__(self, base_url: str, api_key: str | None, extra: dict):
        self.base_url = (base_url or '').rstrip('/')
        self.api_key = api_key or None
        self.extra = extra or {}

    @abstractmethod
    def fetch_ratings(self, steam_ids: list[str], game_type: str | None,
                      instance_id: int | None = None) -> dict[str, RankResult]:
        """Returns {steam_id: RankResult}, keyed by the steam id as a **string**.

        Missing or unranked players are omitted, not raised. Network and HTTP
        errors are caught internally and yield an empty dict.

        The string key is load-bearing. balance.py:308 does
        `sid = int(p["steamid"])`; an adapter that mirrors that produces int
        keys, every frontend lookup misses, and the whole feature renders a
        silent column of dashes.
        """

    @abstractmethod
    def map_game_type(self, qlsm_gametype: str) -> str | None:
        """This provider's own code for a QLSM gametype, or None when the mode
        is not rated here. None is a correct, quiet outcome: no request is made
        and the column is empty."""

    def _log_failure(self, instance_id, status_code=None, exc=None):
        """Provider type, instance id and status code ONLY.

        Never headers, never bodies, never the config object: these logs ship to
        Loki, so a token in a 'let's log the failed request' line does not stay
        local. Rank failures never reach append_log() either — that field is
        rendered verbatim in the UI.
        """
        logger.warning(
            'rank provider %s failed for instance %s (status=%s, error=%s)',
            type(self).__name__, instance_id, status_code,
            type(exc).__name__ if exc else None,
        )
