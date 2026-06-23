# INC-2024-07 — User data leak via export endpoint

**Severity:** SEV-1
**Root cause:** A new `/users/export` endpoint queried the database with a
user-supplied `user_id` but did NOT verify the caller was authorized to access
that user. Any authenticated user could export any other user's data by
changing the id.

**Contributing factor:** The query was also built with an f-string, which a
follow-up pentest found to be SQL-injectable.

**Fix:** Added an ownership/authorization check and switched to parameterized
queries.

**Lesson:** Export/admin endpoints that return user data must enforce
authorization and must never build SQL by string formatting.
