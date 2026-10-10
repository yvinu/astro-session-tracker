# The app manages Masters and matching but does not calibrate lights

Calibrating lights is left to the stacking tool. The app's part is to catalog calibration frames and Masters, match them to lights, and hand the right ones out with a Checkout.

An earlier design had the app calibrate lights itself (headless Siril on the NAS for the ASIAIR rigs, a Python calibrator for the Dwarf) and manage calibrated subs as a regenerable intermediate. It was dropped because every stacking tool in use -- the Naztronomy script for Siril, PixInsight's WBPP, StackingWizard -- calibrates for itself, so app-side calibration would have been a second and third implementation of something the tools already do, each needing validation, plus a class of large intermediate files to track and purge.

**Consequences**: no Siril in the container; the NAS only copies, hashes and catalogs. There are no calibrated subs in the library. Building Masters in the app is not ruled out, and can be added if matching shows that the Masters the tools and devices produce are not enough.
