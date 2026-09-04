"""JARVIS Orbit — standalone daily-driver browser runtime.

Orbit is a NEW browser product (unbranded Chromium via CDP) with JARVIS as its
native intelligence layer. The package owns the Orbit control surface:

    orbit.registry   -> stable tab ids <-> CDP target ids + ownership
    orbit.cdp        -> CDP transport + CDPBackend (BrowserBackend contract)
    orbit.controller -> BrowserController bound to the Orbit CDP backend
    orbit.tools      -> browser tool handlers (single ToolExecutionService path)
    orbit.runtime    -> vertical slice seam (DSH request -> tool -> page read)
"""

__version__ = "0.1.0"