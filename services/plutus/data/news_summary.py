"""Deterministically reduce raw news rows for the NEWS specialist."""

import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher


def parse_timestamp(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("news timestamp must be a datetime or ISO string")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalized_headline(value):
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def reduce_news(symbol, rows, as_of, lookback_days=30, limit=8):
    if lookback_days < 1 or limit < 1:
        raise ValueError("lookback_days and limit must be positive")
    cutoff = parse_timestamp(as_of) - timedelta(days=lookback_days)
    candidates = []
    for row in rows:
        headline = (row.get("headline") or "").strip()
        if not headline:
            continue
        published = parse_timestamp(row.get("created_at") or row.get("published_at"))
        if published < cutoff or published > parse_timestamp(as_of):
            continue
        candidates.append((published, headline, row))
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)

    retained = []
    retained_titles = []
    for published, headline, row in candidates:
        normalized = normalized_headline(headline)
        if any(
            SequenceMatcher(None, normalized, existing).ratio() >= 0.92
            for existing in retained_titles
        ):
            continue
        retained_titles.append(normalized)
        retained.append(
            {
                "id": len(retained),
                "published_at": published.isoformat().replace("+00:00", "Z"),
                "headline": headline,
                "summary": (row.get("summary") or "").strip(),
                "source": (row.get("source") or "unknown").strip() or "unknown",
            }
        )
        if len(retained) == limit:
            break
    return {"symbol": symbol, "articles": retained}


def abstain_result(summary):
    if summary["articles"]:
        raise ValueError("NO_RECENT_NEWS abstention requires an empty article list")
    return {"symbol": summary["symbol"], "status": "ABSTAIN", "reason": "NO_RECENT_NEWS"}
