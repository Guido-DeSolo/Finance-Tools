"""Deterministically reduce quality-approved market statistics for QUANT."""


OBSERVATION_FIELDS = (
    "return_1d_pct",
    "return_5d_pct",
    "return_20d_pct",
    "return_60d_pct",
    "volatility_20d_pct",
    "volume_ratio_20d",
    "distance_from_20d_high_pct",
    "distance_from_20d_low_pct",
)


def pct(value):
    return round(float(value) * 100, 2) if value is not None else None


def reduce_market(packet):
    market = packet["market"]
    reasons = list(market.get("reasons") or [])
    stats = market.get("stats") if market.get("quality_pass") else None
    if not stats:
        return {
            "symbol": packet["symbol"],
            "market_available": False,
            "quality_reasons": reasons or ["market_data_unavailable"],
            "observations": None,
        }

    observations = {
        "return_1d_pct": pct(stats.get("return_1d")),
        "return_5d_pct": pct(stats.get("return_5d")),
        "return_20d_pct": pct(stats.get("return_20d")),
        "return_60d_pct": pct(stats.get("return_60d")),
        "volatility_20d_pct": pct(stats.get("volatility_20d")),
        "volume_ratio_20d": (
            round(float(stats["volume_ratio_20d"]), 2)
            if stats.get("volume_ratio_20d") is not None else None
        ),
        "distance_from_20d_high_pct": pct(stats.get("distance_from_20d_high")),
        "distance_from_20d_low_pct": pct(stats.get("distance_from_20d_low")),
    }
    missing = [key for key, value in observations.items() if value is None]
    core_fields = {
        "return_5d_pct", "return_20d_pct", "volatility_20d_pct",
        "distance_from_20d_high_pct", "distance_from_20d_low_pct",
    }
    missing_core = sorted(core_fields.intersection(missing))
    reasons = sorted(
        set(reasons + [f"missing_quant_observation:{key}" for key in missing])
    )
    if missing_core:
        return {
            "symbol": packet["symbol"],
            "market_available": False,
            "quality_reasons": reasons,
            "observations": None,
        }
    return {
        "symbol": packet["symbol"],
        "market_available": True,
        "quality_reasons": reasons,
        "observations": observations,
    }


def abstain_result(summary):
    if summary["market_available"]:
        raise ValueError("deterministic abstention requires unavailable market data")
    return {
        "symbol": summary["symbol"],
        "status": "ABSTAIN",
        "trend": "neutral",
        "momentum": "neutral",
        "volatility": "normal",
        "volume_confirmation": "unavailable",
        "time_horizon": "20d",
        "confidence": 0.0,
        "interpretation": (
            "Market evidence is unavailable because it failed deterministic quality checks."
        ),
        "risk_flags": ["market_data_unavailable"],
        "evidence_refs": [],
    }
