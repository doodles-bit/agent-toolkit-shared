# Query Analyst Ephemeral Runner

A small Windows/PowerShell package that watches a local file queue and launches
one fresh Codex session per task. It is useful when a long-running coordinator
should stay small while query, log, or document work runs in isolated sessions.

The shared version contains no credentials, company paths, data-source settings,
task history, or production outputs.

## Requirements

- Windows 10/11 or Windows Server with PowerShell 7 (`pwsh`).
- Codex CLI installed and authenticated (`codex --version`).
- A model available to the Codex account used on the machine.
- A local workspace created from `workspace-template/`.

## Quick Start

From this package directory:

```powershell
$workspace = Join-Path $HOME "agent-workspaces/query-analyst"
New-Item -ItemType Directory -Force -Path $workspace | Out-Null
Copy-Item -Recurse -Force .\workspace-template\* $workspace

.\query-analyst-runner.ps1 -Workspace $workspace -Once -DryRun
```

Start the continuous runner in a visible terminal while testing:

```powershell
.\query-analyst-runner.ps1 `
  -Workspace "$HOME\agent-workspaces\query-analyst" `
  -ReasoningEffort medium
```

The runner inherits the model from the user's Codex configuration by default.
Pin a model only after confirming that the home account can use it:

```powershell
.\query-analyst-runner.ps1 `
  -Workspace "$HOME\agent-workspaces\query-analyst" `
  -Model "YOUR_AVAILABLE_MODEL" `
  -ReasoningEffort medium
```

## Submit And Inspect A Task

Use a file for longer task instructions to avoid shell quoting mistakes:

```powershell
$message = Get-Content -Raw .\task.md
$task = .\new-task.ps1 -Message $message
$task
```

The continuous runner claims the task automatically. Inspect status and result:

```powershell
.\task-status.ps1
.\task-status.ps1 -TaskId $task.task_id
```

Artifacts are written to:

- Agent output: `<workspace>/outputs/<task_id>/`
- Runner prompt/log/final response: `runtime/runner-logs/query-analyst/<task_id>/`
- Queue state and result: `runtime/store/<task_id>.json`

## Run In The Background

First confirm a real task succeeds in a visible terminal. Then launch a hidden
runner and redirect its host output:

```powershell
$package = (Get-Location).Path
$workspace = "$HOME\agent-workspaces\query-analyst"
$logDir = Join-Path $package "runtime/host-logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

Start-Process pwsh `
  -ArgumentList @(
    "-NoProfile", "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $package "query-analyst-runner.ps1"),
    "-Workspace", $workspace
  ) `
  -RedirectStandardOutput (Join-Path $logDir "runner.out.log") `
  -RedirectStandardError (Join-Path $logDir "runner.err.log") `
  -WindowStyle Hidden
```

For automatic startup, create a Task Scheduler entry that runs the same `pwsh`
command at user logon. Set the working directory to this package directory and
run it as the same Windows account that authenticated Codex.

## Accessing Additional Data

The default `workspace-write` sandbox can write only to the workspace and paths
explicitly supplied with `-AdditionalDir`. Add the narrowest required directory:

```powershell
.\query-analyst-runner.ps1 `
  -Workspace "$HOME\agent-workspaces\query-analyst" `
  -AdditionalDir "D:\analysis-input"
```

`-DangerouslyBypassCodexSandbox` disables both approvals and sandboxing. Do not
use it for unattended tasks unless the host is externally isolated and every
task source is trusted.

## Updating The Agent

Edit the copied workspace, not `workspace-template/`:

- `AGENTS.md`: durable role and safety rules.
- `memory/query-playbook.md`: verified reusable procedures only.
- `outputs/`: task-local evidence; keep it out of Git.

Restart the runner after changing runner startup parameters or the runner script.
Workspace instruction changes are read by each new session automatically.

## Recovery

If the machine or runner stops during a task, its JSON may remain `active`.
Inspect the task log and output directory first. If the work did not finish,
change only that task's `status` back to `pending`, clear `claimed_at`, and
restart the runner. Do not reset an active task while a Codex child process is
still running.

The current queue is designed for one runner process per agent id. Multiple
runners with the same `-Agent` value can race while claiming a task.

See [IMPLEMENTATION.md](IMPLEMENTATION.md) for the state machine, file schema,
security boundaries, and extension points.
