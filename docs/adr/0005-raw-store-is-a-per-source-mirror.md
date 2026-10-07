# The raw store is a per-Source mirror; organization lives in the catalog

Each Source (a telescope or the ASIAIR) has a permanent folder on the NAS that mirrors the device: its folder structure, its file names, its file dates. Mirror files are never moved, renamed or edited. Everything that organizes them -- Rig, Target, Filter, Night, session, Project -- is a catalog value, and raw files are found through the catalog, not through folder names.

An earlier design moved each new file from a landing folder into a managed tree (`lights/<rig>/<night>/`). It was dropped before being built, for three reasons found in the user's existing sync scripts and notes:

- A pull that copies "whatever is missing at the destination" is simple and safe, and it only works if the destination is permanent. Emptying a landing folder after each pull would have re-downloaded the whole device every run unless a second record of what had been pulled was kept.
- A path built from Rig and Night is only as right as the metadata at the moment of filing. The Dwarf writes local end-of-exposure time into `DATE-OBS`; files would have been filed under the wrong night and moved later.
- The device's file dates are the only evidence of a session's time zone, and its folder names carry information the files do not. A mirror keeps both for free.

**Consequences**: the library on disk is not browsable by target; the app is how you find things. Outputs are different: stacks and finals live in Project folders under Canonical Names, because those are what a person looks for by name. Files arriving from external drives still pass through a landing zone, where they are checked against the catalog before being added.
