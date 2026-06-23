# Security Engineering Standards

## SQL & data access
- NEVER build SQL by string concatenation or f-strings. Use parameterized
  queries / an ORM. String-formatted SQL is treated as a CRITICAL finding.
- All data-export and admin endpoints MUST enforce authorization (verify the
  caller owns or may access the requested resource). Missing authZ on an
  endpoint that returns user data is a CRITICAL finding.

## Secrets
- No secrets, tokens, or private keys in source. Use the secrets manager.

## Input handling
- Validate and bound all external input. Reject unbounded `limit`/`size`
  parameters that could be used for resource exhaustion.

## Dependencies
- New dependencies must be pinned and from the approved registry.
