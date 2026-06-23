# Code Review Checklist

## Correctness
- Errors from I/O and external calls are handled, not swallowed.
- Public API changes are backward compatible or version-gated.
- New logic has tests; new endpoints have at least one happy-path + one error test.

## Style & docs
- Public functions/endpoints have a docstring describing inputs and behavior.
- Names are descriptive; no single-letter names for non-trivial values.

## General
- The PR does one thing; unrelated changes are split out.
- CI is green before merge.
