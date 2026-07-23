# Duplicate Groups count once toward aggregate stats and integration time

A Duplicate Group (see CONTEXT.md) can have copies on multiple Locations (e.g. the same sub on both a NAS and an external drive). Summary stats and the Integration Calculator treat each Duplicate Group as a single unit — one representative File (the earliest `first_seen_at`) contributes to totals like total exposure and target-group integration time; the other copies are excluded from the sum but still visible as their own rows in the file table and duplicates view, tagged as duplicates.

**Why**: without this, integration time would be inflated by however many redundant copies of a sub happen to exist across drives, which defeats the purpose of the Integration Calculator (real integration time on a target, per [PRD.md](../../PRD.md) user story 17-18). A future reader seeing `SUM(exposure)` scoped to "one row per Duplicate Group" rather than a flat `SUM` over `files` should understand this is deliberate, not a bug.

**Considered and rejected**: leaving aggregates as a flat sum over all rows and relying on the user to manually filter out duplicates before reading any total — rejected because it makes every existing stat/chart silently wrong by default until the user remembers to filter, for a library where duplication is expected to be common (NAS + multiple external drives).
