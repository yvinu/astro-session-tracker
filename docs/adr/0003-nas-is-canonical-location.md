# NAS is the canonical Location for duplicate consolidation

The user's target repository lives on a NAS; external drives connected to the MacBook are transient/working copies. When a Duplicate Group has a copy on the NAS Location and copies elsewhere, the duplicates view suggests keeping the NAS copy and flags the others as reclaim candidates (with per-Location reclaimable-space totals and an exportable candidate-path list) — the tool never deletes files itself, it only recommends.

**Consequences**: if a Duplicate Group has no NAS copy at all (only spread across external drives), there's no canonical copy to suggest keeping — those groups are shown but need a different resolution (flagged as "no NAS copy" rather than given a keep suggestion, since defaulting to "keep the first-seen copy" would silently contradict the NAS-canonical rule). This edge case should be handled explicitly, not left to fall through to an arbitrary default.
