# baro-1day-trial

Two independent parts. They share no data and no keys.

| Part | What it is | Start here |
|---|---|---|
| Part 1: Market Radar | Give it brands; it looks at ten sources (ads, shelf, search, social) and keeps what it finds in a local Postgres | `part1/README.md` |
| Part 2: Brand Data Backbone | A Go service that ingests vendor webhooks for many tenants, keeps recent events in an encrypted Postgres hot tier and older ones in a MinIO cold tier, serves state and range reads, and erases customers and tenants. Deep dive: crash safety | `part2/DESIGN.md` (design, 3 pages), then `part2/README.md` (commands), `part2/RUNBOOK.md` and `part2/docs/measurements.md` |

Elsewhere in the repository:

- `.env.example`: the template for Part 1's `.env` (keys are explained in `part1/README.md`, "Prerequisites").
- `docs/superpowers/specs/` and `docs/superpowers/plans/`: the design and plan documents the code was built from.
- `CLAUDE.md`: the working agreement for the coding agent that built this, in Korean.
