# The service runs on the NAS

The catalog, scheduler and API run as a container on the NAS, with the web UI and a small command-line tool used from the Mac. Scheduled downloads from the telescopes need something that is always on and on the home network, and the NAS is where the library already lives (ADR-0003), so reading and hashing files there costs no network transfer.

**Consequences**: nothing in the service may depend on macOS. Location comes from configured library roots, not from `/Volumes/<name>`; the native folder picker is a convenience that is absent on the NAS. Machine-specific paths are environment settings, not catalog data. The catalog file lives on local container storage, not on a network share. Processing with Siril, PixInsight and the other tools stays on the Mac, so files travel to and from it through a Checkout and a check-in.

**Considered and rejected**: running everything on the Mac with launchd, which only downloads when the laptop is awake and at home; a separate mini PC, which is one more machine to maintain for a job the NAS can do.
