# 0001. GitHub over GitLab for source and planning

**Status:** Accepted
**Date:** 2026-08-01
**Deciders:** @cto, @pm

## Context

The programme needs source control plus epic/task planning for 16 people. GitLab
was the initial choice.

GitLab.com Free caps **private top-level namespaces at 5 users** — a 16-person
private group goes read-only. Epics, epic boards, swimlanes, iterations, saved
board scopes and WIP limits are all Premium. Self-hosted CE removes the user cap
but keeps every Free-tier feature limit, and adds an instance to operate.

## Decision

GitHub organisation `Ubuntu-25c-market-prep`, public repositories, GitHub
Projects for planning.

## Alternatives considered

**GitLab.com Premium** — buys exactly the needed features at roughly $29/user/mo
for 16 people. Rejected on cost for a training programme.

**Self-hosted GitLab CE** — no user cap, no licence cost, but no epics either,
so the hierarchy would be faked with label conventions. Plus an instance to
patch, back up and keep available for 16 people.

**GitLab.com Free, public group** — sidesteps the user cap, but still no epics.

## Consequences

- Sub-issues nest 8 levels and work **across repositories**, which GitLab Free
  could not do. Epics live in `ops-program` and own tasks in the working repos.
- Iteration fields, roadmap view and saved views are free.
- Repositories are **public**, which was required for branch protection and
  CODEOWNERS enforcement on the Free plan. This is a permanent constraint on
  what may ever be committed: no account ids, no tfvars, no state.
- Board **grouping** cannot be set through the API. Three views need manual
  configuration after any board rebuild.
