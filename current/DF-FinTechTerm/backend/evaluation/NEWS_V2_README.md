# Frozen NEWS benchmark v2

NEWS v2 preserves the v1 synthetic corpus but narrows the model contract to exact
per-article sentiment and materiality assessments. Python derives overall
sentiment, confidence, conflict state, counts, balance, maximum materiality, and
no-news abstention. Catalyst classification and model-generated risk flags do not
exist in v2.

Readiness requires 100% structural validity, no invalid article references, no
unsupported sentiment or materiality classifications, deterministic abstention,
and no article-level contradictions. Latency is not scored.
