"""Integration time and grand integrated mean midpoint, per target group.

Pure calculation, no I/O. "Integration time" here means light-frame
exposure only -- calibration frames (dark/bias/flat) don't collect signal
from the target, so they don't count toward it, matching standard
astrophotography usage. The mean midpoint is for PixInsight/Siril-style
post-processing workflows that need a single representative timestamp for
a stack.
"""

from datetime import datetime, timezone


def _parse_datetime(date_obs):
    """Parse a DATE-OBS header value to a timezone-aware datetime, or None."""
    if not date_obs or date_obs == "Unknown":
        return None

    text = str(date_obs).strip()
    if text.endswith("Z"):
        text = text[:-1]

    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            dt = datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _light_frames(files):
    return [f for f in files if f.get("frame_type") == "Light"]


def total_integration_seconds(files):
    """Sum of exposure time (seconds) across light-frame subs in `files`."""
    return sum(float(f.get("exposure") or 0) for f in _light_frames(files))


def grand_integrated_mean_midpoint(files):
    """Exposure-weighted average midpoint timestamp across light-frame subs.

    Each sub's midpoint is its DATE-OBS (exposure start, per FITS
    convention) plus half its exposure duration. Weighting by exposure
    means longer subs pull the mean midpoint further toward their own
    timestamp. Working in absolute epoch seconds (rather than manipulating
    calendar fields) means a set of subs spanning midnight is handled
    correctly with no special-casing.

    Returns an ISO 8601 UTC string, or None if there are no light frames
    with both a parseable date and a positive exposure.
    """
    weighted_sum = 0.0
    total_weight = 0.0

    for f in _light_frames(files):
        dt = _parse_datetime(f.get("date"))
        exposure = float(f.get("exposure") or 0)
        if dt is None or exposure <= 0:
            continue
        midpoint_epoch = dt.timestamp() + exposure / 2
        weighted_sum += midpoint_epoch * exposure
        total_weight += exposure

    if total_weight == 0:
        return None

    mean_epoch = weighted_sum / total_weight
    return datetime.fromtimestamp(mean_epoch, tz=timezone.utc).isoformat()
