"""Controlled security suites (T5.5, FR-D8; SR-23–SR-25; decision D9).

Static, code-versioned payload sets. Payloads are harmless and
non-destructive: they only *ask* the target application to do something unsafe
and record its observed behavior. Verdict rules are deterministic and
verdict-based: ``pass | fail | inconclusive`` — an ambiguous response is never
counted as a pass.

Mandatory disclaimer (must be shown in UI and reports): passing this suite
does not prove the application is secure; coverage is limited to the listed
scenarios.
"""
