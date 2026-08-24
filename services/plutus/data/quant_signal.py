"""Deterministic normalization of a validated market summary."""

import math


def classify_trend(observations):
    return_5d = observations["return_5d_pct"]
    return_20d = observations["return_20d_pct"]
    if return_20d >= 3 and return_5d >= 0:
        return "bullish"
    if return_20d <= -3 and return_5d <= 0:
        return "bearish"
    return "neutral"


def classify_momentum(observations):
    magnitude = abs(observations["return_20d_pct"])
    if magnitude >= 10:
        return "strong"
    if magnitude >= 3:
        return "moderate"
    if magnitude >= 1:
        return "weak"
    return "neutral"


def classify_volatility(value):
    if value <= 1:
        return "low"
    if value <= 3:
        return "normal"
    if value <= 6:
        return "high"
    return "extreme"


def classify_volume(value):
    if value is None:
        return "unavailable"
    if value >= 2:
        return "strong"
    if value >= 1.2:
        return "supportive"
    if value <= 0.7:
        return "weak"
    return "neutral"


def signal_strength(observations):
    """Normalize recent return magnitude; this is not a probability forecast."""
    five_day = min(abs(observations["return_5d_pct"]) / 10, 1)
    twenty_day = min(abs(observations["return_20d_pct"]) / 20, 1)
    strength = (five_day + twenty_day) / 2
    if observations["return_5d_pct"] * observations["return_20d_pct"] < 0:
        strength *= 0.5
    return round(strength, 2)


def risk_flags(summary):
    observations = summary["observations"]
    flags = list(summary["quality_reasons"])
    if observations["volatility_20d_pct"] > 6:
        flags.append("extreme_volatility")
    if observations["volume_ratio_20d"] is None:
        flags.append("volume_unavailable")
    elif observations["volume_ratio_20d"] >= 2:
        flags.append("elevated_volume")
    if observations["distance_from_20d_low_pct"] <= 3:
        flags.append("near_20d_low")
    if observations["distance_from_20d_low_pct"] >= 50:
        flags.append("extended_from_20d_low")
    available_returns = [
        observations[key]
        for key in ("return_5d_pct", "return_20d_pct", "return_60d_pct")
        if observations[key] is not None and observations[key] != 0
    ]
    if available_returns and min(available_returns) < 0 < max(available_returns):
        flags.append("conflicting_return_horizons")
    return sorted(set(flags))


def quant_signal(summary):
    if not summary["market_available"]:
        return {
            "symbol": summary["symbol"],
            "status": "ABSTAIN",
            "reason": "MARKET_DATA_UNAVAILABLE",
            "quality_reasons": list(summary["quality_reasons"]),
        }

    observations = summary["observations"]
    for key, value in observations.items():
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"invalid market observation: {key}")

    return {
        "symbol": summary["symbol"],
        "status": "ANALYZED",
        "trend": classify_trend(observations),
        "momentum": classify_momentum(observations),
        "volatility": classify_volatility(observations["volatility_20d_pct"]),
        "volume_confirmation": classify_volume(observations["volume_ratio_20d"]),
        "preferred_horizon": "20d",
        "signal_strength": signal_strength(observations),
        "risk_flags": risk_flags(summary),
        "evidence": {
            key: value for key, value in observations.items() if value is not None
        },
    }
