# ops-program

Programme tracking for the platform build: epics, the backlog manifest,
standards, decisions and runbooks.

## Documentation

Start with **[docs/](docs/)**. In reading order:

| Document | What it covers |
|---|---|
| [Engineering Handbook](docs/engineering-handbook.md) | How we work: ownership, definition of done, review, interfaces, incidents |
| [CONVENTIONS.md](CONVENTIONS.md) | Every naming rule: repos, branches, commits, issues, labels, AWS, Terraform, Kubernetes |
| [Terraform Standards](docs/terraform-standards.md) | File layout, pinning, variables, safety, secrets, review criteria |
| [Terraform State Strategy](docs/terraform-state-strategy.md) | Layer model, state keys, cross-layer contracts |
| [ADRs](docs/adr/) | Why things are the way they are |
| [Runbooks](runbooks/) | Procedures for when something is on fire |

## Programme data

- `program/roster.yaml` — person → GitHub account → workstreams
- `program/backlog.yaml` — the 19 epics and their tasks, source of truth for the board

## Scripts

All idempotent and safe to re-run.

| Script | Does |
|---|---|
| `scripts/bootstrap-labels.sh` | Applies the 35-label taxonomy to every repo |
| `scripts/bootstrap-codeowners.sh` | Commits path-scoped CODEOWNERS to every repo |
| `scripts/seed-backlog.sh` | Creates epics and sub-issues, links them, adds to the board |
| `scripts/render_board.py` | Renders the live board as a self-contained HTML page |

`seed-backlog.sh` also backfills assignees: GitHub cannot assign issues to people
who have not accepted their organisation invitation, so re-run it as people join.

## The board

[Platform Build](https://github.com/orgs/Ubuntu-25c-market-prep/projects/1) —
19 epics, 119 tasks, sequenced into 8 waves.
