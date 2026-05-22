# REFLECTIONS — Group 10 costctl

## 1. Multi-account: scaling costctl to 100 AWS accounts

Today `costctl` reads credentials from the default boto3 chain (env vars / `~/.aws/credentials`), which means one invocation talks to one account. To run it across ~100 accounts we'd change three things:

- **Cross-account roles instead of long-lived keys.** Create one IAM role per child account (e.g. `costctl-readonly`) trusting a central "ops" account, then the CLI takes `--profile ops` and `--account <id>` flags and calls `sts:AssumeRole` for each target account at the start of the run. This keeps credentials in one place and lets Security rotate / revoke per child account independently.
- **A simple account loop with concurrency.** Wrap `main()` so it iterates over a list of account IDs (from a config file or AWS Organizations `list_accounts`), assumes the role for each, and runs the existing command. For `list` / `cost` this is embarrassingly parallel — a `ThreadPoolExecutor(max_workers=10)` is enough. For `terminate` / `clean` we'd keep it serial and add an explicit `--account` filter to avoid blast-radius mistakes.
- **Aggregated CSV per account.** Each command would gain a `--csv` / `--out <dir>` switch and write one row per resource, prefixed with the account id. Then a tiny `costctl roll-up` post-step reads all CSVs and prints a sorted total. Useful as a FinOps weekly report.

The key insight: the per-account *logic* doesn't change, only the *credential boundary* and the *output shape*.

## 2. `clean --apply` blast radius

If someone accidentally ran `clean --tag Environment=dev --apply` in an account shared with another team, the current safeguards (dry-run default, summary print) are **not enough** — a slip of the keyboard appends `--apply` and resources are gone in seconds.

What I'd want in place before allowing `--apply` against a shared account:

- **A second confirmation step gated on count.** Even with `--apply`, if `len(targets) > 5` or `len(targets["volume"]) > 0`, the CLI should print the full target list and require typing `yes-delete-N-resources` (with `N` matching the actual count). Force-flag bypass is fine for CI, but for interactive use a typed-count gate prevents fat-finger mistakes.
- **Tag ownership convention enforced at the CLI level.** Refuse to operate on tags that aren't namespaced (e.g. reject `Environment=*` but allow `team=g10:purpose=practice`). Pair this with an org-level SCP that says "you cannot terminate a resource unless its `team` tag matches your IAM principal's `team` tag." That way even if the CLI is bypassed, IAM stops you.
- **Per-account daily quota for `clean`.** Refuse if this account has already had more than (say) 20 resources cleaned in the last 24h, surfaced via a tiny DynamoDB counter or an SSM Parameter. A single bad invocation can only do so much damage.
- **Soft-delete first.** For EC2: `stop` instead of `terminate` on the first pass, mark with `pending-clean=<timestamp>`, then a separate `costctl reap` job does the actual `terminate_instances` 72 hours later. This gives the other team a window to notice and shout.

The pattern is the same as production change management: small steps, reversible defaults, explicit consent on scope, and a way for an outsider to catch you before the bad thing is permanent.

## 3. AI assistance

Roughly 70-80% of the code in `commands/*_cmd.py` came from Claude scaffolding the implementations off the spec docstrings + provided helpers. Parts I actively reviewed/modified:

- **Output format alignment.** The docstrings show very specific output (column widths, "(no tags)" placeholder, "Refusing — bucket X has N object(s)"). I cross-checked each `print(...)` against the docstring and the test assertions — the tests only check substrings, but matching the docstring exactly makes the sample_output diff against AWS Console cleaner.
- **S3 tag merging.** `put_bucket_tagging` replaces the entire TagSet, so the AI's first cut would have silently destroyed unrelated tags. I made sure `_tag_s3` reads existing tags first, merges, then puts — and falls back to empty dict on `ClientError` (no tagging config) rather than crashing.
- **`_list_ec2` skipping terminated instances.** AWS keeps terminated instances visible in `describe_instances` for ~1 hour. Without the filter, `list ec2` would show ghosts. Added explicitly.

What I would not let AI write unattended: anything destructive (`terminate_instances`, `delete_bucket`, `clean --apply`). I read those line-by-line and confirmed the confirm/force gating against `tests/test_terminate.py` and `tests/test_clean.py` assertions.
