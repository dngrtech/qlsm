"""Provider type string -> adapter class.

Adding a provider is a new module plus one line here. It is never a schema
change or a route change.
"""
from ui.rank_providers.elo_service import ThunderdomeEloProvider
from ui.rank_providers.qlstats import QlstatsProvider
from ui.rank_providers.slipgate import SlipgateProvider

PROVIDER_TYPES = {
    'qlstats': QlstatsProvider,
    'slipgate': SlipgateProvider,
    'elo_service': ThunderdomeEloProvider,
}


def build_provider(provider_type, base_url, api_key, extra):
    """An adapter instance, or None when provider_type is not registered."""
    cls = PROVIDER_TYPES.get(provider_type)
    if cls is None:
        return None
    return cls(base_url, api_key, extra)
