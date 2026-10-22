# Development version

# Version 0.3.0 - 2026-10-22

* Use *Pillow* plugin methods directly. This avoids a `KeyError` if the JPEG plugin is not loaded yet. (Ported from upstream.)
* Avoid unused object IDs. (Ported from upstream.)
* Drop support for Python <= 3.9.
* Drop support for *Pillow* < 10.2.0.
* Make tests compatible with *Pillow* >= 12.1.0.
* Use lazy imports for Python 3.15. (Ported from upstream.)
* Enforce strict typing.

# Version 0.2.0 - 2025-03-15

* Drop support for Python 3.8.
* Synchronize with *Pillow* license changes.

# Version 0.1.0 - 2024-06-10

* First public release.
