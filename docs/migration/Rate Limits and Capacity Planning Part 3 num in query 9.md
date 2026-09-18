# Rate Limits and Capacity Planning Part 3 num in query 9

**Stage 9 of 10** of the Google Class Help hosting migration.

- **Stage goal:** Rate limiting, Google API quotas, token-failure handling, logging, privacy, retention, and capacity planning for ~1,000 users.
- **Depends on:** stages 1-8 must be done (or their decisions recorded)
- **Source prompt sections:** §70 "Time and timezone handling"  (part 3/4)

---
## 70. Time and timezone handling

The existing project has explicit datetime semantics and stores certain values as naive datetimes.

Do not change timezone behavior accidentally during the migration.

Review:

- Google Classroom timestamps;
- due dates;
- PostgreSQL `timestamp with time zone` vs `timestamp without time zone`;
- user locale/display timezone;
- calendar calculations;
- server timezone;
- DST.

A hosted server should normally operate in UTC internally.

Convert to user-facing timezone at the UI boundary where appropriate.

Document any required migration.

---

