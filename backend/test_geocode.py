"""Tests for reverse geocoding (backend/geocode.py).

No real network calls: Nominatim is mocked throughout, both because tests
must not depend on internet access or a third party's uptime, and because
hammering the free API on every test run would be a bad citizen of its
usage policy. What's under test is Echo's own logic -- label formatting,
graceful degradation, and caching -- not Nominatim itself.
"""

import geocode


def test_reverse_geocode_returns_none_without_coordinates():
    assert geocode.reverse_geocode(None, 78.4867) is None
    assert geocode.reverse_geocode(17.385, None) is None


def test_reverse_geocode_degrades_to_none_on_network_failure(monkeypatch):
    def _boom(*args, **kwargs):
        raise ConnectionError("no network in this test")

    monkeypatch.setattr(geocode.requests, "get", _boom)
    geocode._CACHE.clear()
    # Must not raise: a geocoding outage degrades the alert message, it must
    # never break incident dispatch.
    assert geocode.reverse_geocode(17.385044, 78.486671) is None


def test_reverse_geocode_degrades_to_none_on_bad_status(monkeypatch):
    class FakeResponse:
        status_code = 503

    monkeypatch.setattr(geocode.requests, "get", lambda *a, **k: FakeResponse())
    geocode._CACHE.clear()
    assert geocode.reverse_geocode(17.385044, 78.486671) is None


def test_format_label_prefers_named_place_over_display_name():
    payload = {
        "address": {"amenity": "City Central Hospital", "city": "Hyderabad"},
        "display_name": "City Central Hospital, Somajiguda, Hyderabad, Telangana, 500082, India",
    }
    assert geocode._format_label(payload) == "City Central Hospital, Hyderabad"


def test_format_label_falls_back_to_trimmed_display_name():
    payload = {"address": {}, "display_name": "Road 12, Banjara Hills, Hyderabad, Telangana, India"}
    assert geocode._format_label(payload) == "Road 12, Banjara Hills, Hyderabad"


def test_format_label_returns_none_when_nothing_usable():
    assert geocode._format_label({"address": {}}) is None


def test_reverse_geocode_success_and_cache_hit(monkeypatch):
    calls = {"count": 0}

    class FakeResponse:
        status_code = 200

        def json(self):
            calls["count"] += 1
            return {"address": {"road": "Road 12", "city": "Hyderabad"}, "display_name": "Road 12, Hyderabad"}

    monkeypatch.setattr(geocode.requests, "get", lambda *a, **k: FakeResponse())
    geocode._CACHE.clear()

    first = geocode.reverse_geocode(17.385044, 78.486671)
    assert first == "Road 12, Hyderabad"

    # A second lookup at (rounded) the same coordinates must hit the cache,
    # not issue a second HTTP request -- see geocode.py's Nominatim usage-
    # policy comment.
    def _fail_if_called(*a, **k):
        raise AssertionError("reverse_geocode should have used the cache")

    monkeypatch.setattr(geocode.requests, "get", _fail_if_called)
    second = geocode.reverse_geocode(17.385045, 78.486672)  # same ~11m cell
    assert second == "Road 12, Hyderabad"
