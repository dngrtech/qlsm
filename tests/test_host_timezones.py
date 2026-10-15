"""The standalone host form must accept the zones of the hosts QLSM manages."""
from ui.routes.host_routes import VALID_TIMEZONES


def test_finland_and_estonia_are_valid_host_timezones():
    assert {"Europe/Helsinki", "Europe/Tallinn"} <= VALID_TIMEZONES
