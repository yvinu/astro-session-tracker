# Nothing is deleted automatically until the library has a second copy

The app reports what could be removed -- duplicates, raw calibration frames with a verified Master, intermediates, files safe to clear from a device -- and how much space each would free. It deletes nothing. Delete rules can be enabled, one at a time, only after a second copy of the library is configured and verified; they then go through a trash folder with retention and require a Content Hash match on the surviving copy.

**Why**: once a telescope's storage is cleared, the NAS holds the only copy of the raw lights, and a trash folder on the same volume does not protect against losing that volume. Automated cleanup on a single copy trades a recoverable problem (disk filling up) for an unrecoverable one.

**Consequences**: until a backup exists the disk-space goals are met only by reports the user acts on by hand, as the duplicate reclaim view already works. This keeps the README's statement that the tool never deletes files true for now.
