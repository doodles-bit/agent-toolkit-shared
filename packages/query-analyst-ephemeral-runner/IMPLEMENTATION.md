# Implementation Details

## Purpose

The runner isolates expensive source work from a coordinator's conversation.
Instead of retaining schemas, logs, and long documents in one session, it starts
a clean Codex process for each task and returns only a compact result. Durable
evidence stays on disk under a task id.

## Components

```text
new-task.ps1
    |
    v
runtime/store/<task_id>.json
    |
    v
query-analyst-runner.ps1
    |
    +-- codex exec --ephemeral --cd <workspace>
    |       |
    |       +-- <workspace>/outputs/<task_id>/...
    |
    +-- runtime/runner-logs/<agent>/<task_id>/...
    |
    v
runtime/store/<task_id>.json  (done or failed, with final response)
```

- `new-task.ps1` creates a UUID task with `pending` state.
- `query-analyst-runner.ps1` polls the store, claims matching tasks, composes a
  bounded prompt, executes Codex, saves logs, and completes the task.
- `task-status.ps1` lists queue state or prints one complete task object.
- `workspace-template/` defines the agent role and evidence contract without
  embedding a data source or credential.

## Task Schema

```json
{
  "id": "uuid",
  "from": "local-user",
  "to": "query-analyst",
  "message": "task instructions",
  "status": "pending | active | done | failed",
  "created_at": "ISO-8601 UTC",
  "claimed_at": "ISO-8601 UTC or null",
  "completed_at": "ISO-8601 UTC or null",
  "result": "final response or null",
  "is_error": false,
  "runner_pid": 1234
}
```

`runner_pid` is added when a task is claimed. JSON writes use a temporary file
and same-directory move so readers do not observe partially written JSON.

## State Machine

```text
pending --claim--> active --exit 0--> done
                         `--error--> failed
```

The runner claims only tasks whose `to` value equals its `-Agent` value. Tasks
are processed in ascending `created_at` order. `-Once` exits after one task or
after finding an empty queue. `-MaxTasks` bounds a batch runner.

## Codex Process Contract

Every task uses:

```text
codex exec --ephemeral \
  --config model_reasoning_effort="<effort>" \
  [--model <model>] \
  --cd <workspace> \
  [--add-dir <path> ...] \
  --output-last-message <final.md> \
  --sandbox workspace-write \
  -
```

The prompt is sent through standard input, not interpolated into a shell command.
Arguments use `ProcessStartInfo.ArgumentList`, which avoids command-string quoting
and injection problems. Standard streams use UTF-8 for non-English tasks.

`--ephemeral` prevents task sessions from being persisted as resumable Codex
sessions. Task artifacts and runner logs remain available for audit and recovery.

## Prompt And Memory Boundary

The fresh session receives only:

- Workspace `AGENTS.md`.
- Optional `memory/query-playbook.md`.
- Task metadata and task message.
- Artifact and response-size rules.

It does not receive prior task conversations. Task-specific results belong in
`outputs/<task_id>/`; the playbook should contain only verified reusable rules.
This separation is the main context-saving mechanism.

## Security Boundary

The repository intentionally excludes:

- API keys, OAuth tokens, cookies, and connection strings.
- Production task JSON, logs, prompts, outputs, schemas, and query history.
- Company usernames, absolute paths, window titles, and internal agent names.
- Data-platform clients or environment-specific authentication helpers.

Security still depends on deployment:

- A task message is executable agent input. Accept tasks only from trusted local
  users or add authentication before exposing a task-creation API.
- `-AdditionalDir` expands writable scope. Grant only required directories.
- `-DangerouslyBypassCodexSandbox` removes the main local containment boundary.
- Logs and results can contain source data. Protect and rotate `runtime/` and
  workspace `outputs/` according to the sensitivity of the local data.
- Store credentials outside task text, agent memory, Git, and output artifacts.

## Concurrency And Durability

The implementation assumes one runner per agent id. File replacement prevents
partial JSON writes, but claim is not a distributed compare-and-swap operation.
Two runners with the same agent id can both read the same pending task before one
writes `active`. For multi-host or multi-runner operation, replace the file store
with SQLite transactions, a database queue, or a broker supporting leases.

There is no automatic active-task lease. This avoids incorrectly rerunning a slow
task, but a machine crash leaves manual recovery work. A future lease design
should include `heartbeat_at`, an expiry interval, child PID validation, and an
explicit retry count.

## Extending The Package

### Add a coordinator or MCP server

Keep the JSON schema and store directory stable. A coordinator can create tasks
and read results through an MCP tool or local HTTP API without changing the
runner. Authenticate any non-local endpoint and validate `from`, `to`, message
size, and allowed task types.

### Add multiple agent roles

Create separate workspaces and run one process per role:

```powershell
.\query-analyst-runner.ps1 -Agent docs-agent -Workspace D:\agents\docs
.\query-analyst-runner.ps1 -Agent code-agent -Workspace D:\agents\code
```

Submit with the matching destination:

```powershell
.\new-task.ps1 -To docs-agent -Message "Find evidence for ..."
```

### Add notifications

Observe task JSON transitions or add a post-completion command after
`Complete-Task`. Keep notification failures separate from task success so a
desktop or chat integration cannot corrupt completed work.

## Validation Strategy

Before unattended operation:

1. Parse all PowerShell files with the PowerShell language parser.
2. Run `-Once -DryRun` against an empty store.
3. Submit a file-only smoke task that writes `summary.md` without network access.
4. Confirm state becomes `done`, logs exist, and the final response references the artifact.
5. Restart the runner and confirm no completed task runs again.
6. Test one intentional failure and confirm state becomes `failed` with diagnostics.
