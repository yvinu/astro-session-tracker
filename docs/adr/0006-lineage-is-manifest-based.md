# Lineage rests on the Checkout manifest; log parsers only add detail

What went into an image is recorded by the app's own bookkeeping, not recovered from tool logs. A Checkout fixes the set of subs handed out, each with its Content Hash. Everything checked in from that working folder is recorded as a run against that Checkout. So for any stack or final the catalog can always say which subs were available to it, and for any sub which outputs it could have contributed to, without reading a single log.

Parsers for Siril, StackingWizard, AstroWizard and PixInsight logs are enrichment on top: they can narrow "available" to "actually stacked", record rejected frames, and list processing steps. Logs are always stored at check-in whether or not anything can parse them.

**Why**: the tools' logs are not a stable interface. Two of the four are betas that ship new builds weekly, Photoshop writes no log at all, and Siril's log names frames only by sequence number -- the link back to file names lives in a conversion file that the most-used script deletes by default. A lineage that depended on parsing would be wrong or missing whenever a format moved.

**Consequences**: the guaranteed answer is an upper bound -- the subs handed out, not the subset a tool kept. To make later narrowing possible the manifest records each sub's position in the order Siril numbers files. A run checked in without a Checkout (e.g. retouching an old final) has no subs behind it, and says so.
