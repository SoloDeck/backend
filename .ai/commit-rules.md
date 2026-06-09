# Commit Rules

The canonical commit and branch convention for this repository. Read before every commit.

## Commit Scope

One logical change per commit. Never bundle unrelated changes.

## Branch Per Purpose (REQUIRED)

Before committing, check the current branch. If on `main`/default, you **MUST** create a new
branch named `<type>/<scope-or-purpose>` and commit there. Never commit directly to `main`.

```
feat/deals-intake-form
migration/invoices-tax
fix/auth-token-refresh
```

## Message Format

`<type>(<scope>): <short summary>`

```
feat(deals): add intake form endpoint
fix(models): correct deal_stage enum value
migration(invoices): add tax_amount column
```

- **Allowed types:** `feat` · `fix` · `docs` · `refactor` · `test` · `chore` · `migration`
- **Scope:** the module name (`auth`, `deals`, `contracts`, …) or `models`, `schema`, `config`,
  `deps`, `ci`.

## Never Commit

- Secrets, `.env` files, local IDE config.
- Compiled bytecode (`__pycache__`, `*.pyc`).

## Hygiene

- **Never amend a pushed commit.** Create a new commit instead.
- **Never skip hooks** (`--no-verify`) unless explicitly instructed.
- **Migration commits** must be tagged `migration(<domain>):` and must not be bundled with feature
  code.

## Version Bump (REQUIRED before a deployable change is done)

Once tests pass and the change is deployable, you **MUST** bump the application version in
`pyproject.toml` (`version = "X.Y.Z"`, semver) as part of the same change:

- `fix` → patch (`0.1.0` → `0.1.1`)
- `feat` → minor (`0.1.0` → `0.2.0`)
- breaking change → major (`0.1.0` → `1.0.0`)

Pure `docs`/`test`/`chore`/`refactor` changes that are not independently deployable do not require a
bump. Commit the bump as `chore(version): bump to X.Y.Z` (or fold it into the deployable commit).
