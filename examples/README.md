# changelog-forge — examples

Each scenario shows: a real git history, the command, and the output — captured verbatim from a hermetic test repo.

---

## Scenario 1 — typical pre-release run

**Setup:** A repo at tag `v0.4.2` with four commits since:

```
$ git log --oneline v0.4.2..HEAD
95b75a9 feat!: drop /v0 endpoints
1eec1a8 perf: cache token-bucket counters
75db064 feat(api): paginate search endpoint
db91534 fix(auth): handle null user in cookie middleware
```

The `feat!:` and the `BREAKING CHANGE:` trailer should drive a `major` bump.

**Command:**

```sh
python3 scripts/forge.py --format md
```

**Helper output (verbatim):**

```markdown
## [Unreleased] - 2026-05-16

### Features
- drop /v0 endpoints ⚠ BREAKING (95b75a9)
- **api**: paginate search endpoint (75db064)

### Bug Fixes
- **auth**: handle null user in cookie middleware (db91534)

### Performance
- cache token-bucket counters (1eec1a8)

_Suggested bump: **major**_
_Suggested version: **1.0.0**_
```

---

## Scenario 2 — JSON for release tooling

```sh
python3 scripts/forge.py --format json
```

The JSON output includes a dedicated `breaking_changes` array:

```json
{
  "suggested_bump": "major",
  "suggested_version": "1.0.0",
  "breaking_changes": [
    {
      "commit": "95b75a981846c54a346d677bf4b2f9253cb2f8b4",
      "note": "drop /v0 endpoints"
    }
  ]
}
```

Useful for `npm publish`, `cargo release`, or a custom release script — read `suggested_bump` and use it directly with `npm version <bump>` or equivalent.

---

## Scenario 3 — write into CHANGELOG.md (idempotent)

```sh
python3 scripts/forge.py --write
```

Behaviour:

- If `CHANGELOG.md` doesn't exist → create it with a `# Changelog` heading + the new `## [Unreleased]` block.
- If `CHANGELOG.md` exists and has a `## [Unreleased]` block → replace it.
- If `CHANGELOG.md` exists with a `# Changelog` heading but no `[Unreleased]` block → insert the new block *after* the heading (not before).

Run it twice; the second run produces byte-identical output. That's covered by `test_write_changelog_idempotent`.

---

## Scenario 4 — explicit range

Compare specific refs:

```sh
python3 scripts/forge.py --from v0.4.0 --to v0.4.2 --format md
```

Useful for back-filling CHANGELOG entries for old releases.

---

## Semver heuristic reference

| Trigger | Bump |
|---|---|
| any breaking (`!` or `BREAKING CHANGE:`) | `major` |
| any `feat` | `minor` |
| any `fix` / `perf` | `patch` |
| only `chore` / `docs` / `style` / `refactor` / `test` / `ci` / `build` | `patch` (effectively no-op) |

The highest-precedence rule that matches wins.
