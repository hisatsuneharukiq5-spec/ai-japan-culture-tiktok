# Vendored copy of quiet-pipelines

This folder is an unmodified copy of quiet-pipelines (MIT, see `LICENSE`),
taken from commit `517ec75c526300201aeac102abe066d58c69c827` (v0.1.0).
It is here only because quiet-pipelines is not published yet.

Do not edit files in this folder. Make changes in the quiet-pipelines
repository and copy them over again.

## Switching to the published action

1. In `.github/workflows/watchdog.yml`, change

   ```yaml
   - uses: ./.github/actions/quiet-pipelines
   ```

   to the published action, pinned to a tag or commit SHA, e.g.

   ```yaml
   - uses: OWNER/quiet-pipelines@v0.1.0
   ```

2. Delete this folder (`.github/actions/quiet-pipelines/`).

Nothing else changes: the inputs (`config`, `github-token`,
`anthropic-api-key`, `dry-run`) and the settings file
`config/quiet-pipelines.yml` stay the same.
