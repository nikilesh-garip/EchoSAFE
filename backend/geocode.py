"""Reverse geocoding: turns an incident's raw lat/lng into a human-readable
address for the emergency call and Telegram message.

Uses OpenStreetMap's free Nominatim API -- the same no-API-key philosophy
main.py already uses for /nearby's Overpass calls, so this needs no new key
and nothing in .env.example for the user to fill in. Best-effort only: a
failed or slow lookup must never block or break an escalation. The precise
coordinates and the Google Maps link are always sent regardless of whether
this succeeds -- this only adds a friendlier label on top of them.
"""

import time

import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "EchoSafetyApp/1.0 (emergency escalation reverse-geocoding)"

# Nominatim's usage policy caps free use at ~1 request/second; a tiny
# in-memory cache means a burst of incidents at the same location (repeated
# demo clicks, a noisy environment) does not hammer the public API.
_CACHE = {}
_CACHE_TTL_SECONDS = 600
_CACHE_MAX_ENTRIES = 256


def _cache_key(latitude, longitude):
    # Round to ~11m precision -- plenty for "which building/street", and it
    # lets nearby repeat incidents share a cache hit.
    return (round(latitude, 4), round(longitude, 4))


def reverse_geocode(latitude, longitude, timeout=6.0):
    """Returns a short human-readable address, or None if unavailable.

    Never raises: a geocoding outage must degrade the message to
    coordinates-only, not break incident dispatch.
    """
    if latitude is None or longitude is None:
        return None

    key = _cache_key(latitude, longitude)
    cached = _CACHE.get(key)
    if cached and (time.time() - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]

    try:
        response = requests.get(
            NOMINATIM_URL,
            params={
                "lat": latitude,
                "lon": longitude,
                "format": "jsonv2",
                "zoom": 18,
                "addressdetails": 1,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
        )
        if response.status_code != 200:
            return None
        payload = response.json()
    except Exception:
        return None

    label = _format_label(payload)
    if label:
        if len(_CACHE) >= _CACHE_MAX_ENTRIES:
            _CACHE.pop(next(iter(_CACHE)), None)
        _CACHE[key] = (time.time(), label)
    return label


def _format_label(payload):
    address = payload.get("address") or {}
    # Prefer a recognizable place/road, then fall back to the display_name
    # Nominatim already composed -- both are already human phrasing, never
    # raw coordinates dressed up as an address.
    parts = []
    primary = (
        address.get("amenity") or address.get("building") or address.get("road")
        or address.get("neighbourhood") or address.get("suburb")
    )
    if primary:
        parts.append(primary)
    locality = address.get("city") or address.get("town") or address.get("village")
    if locality and locality != primary:
        parts.append(locality)
    if parts:
        return ", ".join(parts)
    display_name = payload.get("display_name")
    if display_name:
        # Trim to the first three comma segments: a full Nominatim
        # display_name can run to a whole postal hierarchy, too long to read
        # aloud or fit cleanly in a Telegram alert line.
        return ", ".join(part.strip() for part in display_name.split(",")[:3])
    return None
