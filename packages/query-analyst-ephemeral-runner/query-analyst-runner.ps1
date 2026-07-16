# File-backed ephemeral Codex runner.
# Each pending task is claimed, executed in a fresh `codex exec --ephemeral`
# session, and completed with the final response and task-local logs.

[CmdletBinding()]
param(
    [string]$Agent = "query-analyst",
    [string]$StoreDir = "",
    [Parameter(Mandatory = $true)]
    [string]$Workspace,
    [string]$Codex = "",
    [string]$Model = "",
    [ValidateSet("none", "minimal", "low", "medium", "high", "xhigh")]
    [string]$ReasoningEffort = "medium",
    [string[]]$AdditionalDir = @(),
    [int]$PollSeconds = 10,
    [int]$MaxTasks = 0,
    [switch]$Once,
    [switch]$DryRun,
    [switch]$DangerouslyBypassCodexSandbox
)

$ErrorActionPreference = "Stop"

$ScriptRoot = if ($PSScriptRoot) {
    $PSScriptRoot
} else {
    Split-Path -Parent $MyInvocation.MyCommand.Path
}

if ([string]::IsNullOrWhiteSpace($StoreDir)) {
    $StoreDir = Join-Path $ScriptRoot "runtime/store"
}

if ([string]::IsNullOrWhiteSpace($Codex)) {
    $codexCommand = Get-Command codex.cmd -ErrorAction SilentlyContinue
    if (-not $codexCommand) {
        $codexCommand = Get-Command codex -ErrorAction SilentlyContinue
    }
    if (-not $codexCommand) {
        throw "Codex CLI was not found on PATH. Install it or pass -Codex <path>."
    }
    $Codex = $codexCommand.Source
}

$Workspace = [System.IO.Path]::GetFullPath($Workspace)
$StoreDir = [System.IO.Path]::GetFullPath($StoreDir)
$LogRoot = Join-Path (Split-Path -Parent $StoreDir) "runner-logs/$Agent"

function Write-RunnerLog {
    param([string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$stamp] $Message"
}

function Get-TaskPath {
    param([string]$TaskId)
    Join-Path $StoreDir "$TaskId.json"
}

function Read-TaskFile {
    param([string]$Path)
    [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8) |
        ConvertFrom-Json
}

function Write-TaskFile {
    param([object]$Task)

    $path = Get-TaskPath -TaskId $Task.id
    $tmp = "$path.$PID.tmp"
    $json = $Task | ConvertTo-Json -Depth 10
    $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText($tmp, $json, $utf8NoBom)
    Move-Item -LiteralPath $tmp -Destination $path -Force
}

function Set-TaskProperty {
    param(
        [object]$Task,
        [string]$Name,
        [object]$Value
    )

    if ($Task.PSObject.Properties[$Name]) {
        $Task.$Name = $Value
    } else {
        $Task | Add-Member -MemberType NoteProperty -Name $Name -Value $Value
    }
}

function Get-NextPendingTask {
    $tasks = Get-ChildItem -LiteralPath $StoreDir -Filter "*.json" -File |
        ForEach-Object {
            try {
                Read-TaskFile -Path $_.FullName
            } catch {
                Write-RunnerLog "ignored unreadable task file: $($_.FullName)"
                $null
            }
        } |
        Where-Object { $_ -and $_.to -eq $Agent -and $_.status -eq "pending" } |
        Sort-Object created_at

    if (@($tasks).Count -eq 0) {
        return $null
    }
    return @($tasks)[0]
}

function Claim-Task {
    param([object]$Task)

    $path = Get-TaskPath -TaskId $Task.id
    $current = Read-TaskFile -Path $path
    if ($current.status -ne "pending") {
        Write-RunnerLog "skip task $($Task.id): status is $($current.status)"
        return $null
    }

    $current.status = "active"
    Set-TaskProperty -Task $current -Name "claimed_at" -Value ((Get-Date).ToUniversalTime().ToString("o"))
    Set-TaskProperty -Task $current -Name "runner_pid" -Value $PID
    Write-TaskFile -Task $current
    return $current
}

function Complete-Task {
    param(
        [string]$TaskId,
        [string]$Result,
        [bool]$IsError
    )

    $task = Read-TaskFile -Path (Get-TaskPath -TaskId $TaskId)
    $task.status = if ($IsError) { "failed" } else { "done" }
    Set-TaskProperty -Task $task -Name "completed_at" -Value ((Get-Date).ToUniversalTime().ToString("o"))
    Set-TaskProperty -Task $task -Name "result" -Value $Result
    Set-TaskProperty -Task $task -Name "is_error" -Value $IsError
    Write-TaskFile -Task $task
    return $task
}

function New-CodexPrompt {
    param([object]$Task)

    $playbook = Join-Path $Workspace "memory/query-playbook.md"
    $playbookInstruction = if (Test-Path -LiteralPath $playbook) {
        "- $playbook"
    } else {
        "- No playbook file is present; follow AGENTS.md and the task message."
    }

    @"
You are $Agent.

This is an ephemeral file-queue run. The runner already claimed the task and
will persist your final response. Do not modify task JSON files directly.

Read and follow:
- $Workspace/AGENTS.md
$playbookInstruction

Task metadata:
- task_id: $($Task.id)
- from: $($Task.from)
- to: $($Task.to)
- created_at: $($Task.created_at)

Required operating rules:
- Write task artifacts under outputs/$($Task.id)/.
- Keep large logs, source extracts, and result sets out of the final response.
- Include artifact paths, verified findings, and blockers in the final response.
- If execution fails, preserve useful diagnostics in outputs/$($Task.id)/run.log.

Task message:
$($Task.message)
"@
}

function Invoke-CodexTask {
    param([object]$Task)

    $taskLogDir = Join-Path $LogRoot $Task.id
    New-Item -ItemType Directory -Force -Path $taskLogDir | Out-Null

    $promptFile = Join-Path $taskLogDir "prompt.md"
    $stdoutFile = Join-Path $taskLogDir "codex.log"
    $finalFile = Join-Path $taskLogDir "final.md"
    $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    $prompt = New-CodexPrompt -Task $Task
    [System.IO.File]::WriteAllText($promptFile, $prompt, $utf8NoBom)

    $arguments = [System.Collections.Generic.List[string]]::new()
    @("exec", "--ephemeral", "--config", ('model_reasoning_effort="{0}"' -f $ReasoningEffort)) |
        ForEach-Object { $arguments.Add($_) }

    if (-not [string]::IsNullOrWhiteSpace($Model)) {
        $arguments.Add("--model")
        $arguments.Add($Model)
    }

    $arguments.Add("--cd")
    $arguments.Add($Workspace)
    foreach ($dir in $AdditionalDir) {
        if (-not (Test-Path -LiteralPath $dir)) {
            throw "AdditionalDir not found: $dir"
        }
        $arguments.Add("--add-dir")
        $arguments.Add([System.IO.Path]::GetFullPath($dir))
    }
    $arguments.Add("--output-last-message")
    $arguments.Add($finalFile)

    if ($DangerouslyBypassCodexSandbox) {
        $arguments.Add("--dangerously-bypass-approvals-and-sandbox")
    } else {
        $arguments.Add("--sandbox")
        $arguments.Add("workspace-write")
    }
    $arguments.Add("-")

    $modelLabel = if ($Model) { $Model } else { "user-config default" }
    Write-RunnerLog "running task $($Task.id) (model=$modelLabel, reasoning=$ReasoningEffort)"

    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $Codex
    $psi.WorkingDirectory = $Workspace
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.StandardInputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    foreach ($argument in $arguments) {
        $psi.ArgumentList.Add($argument)
    }

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $psi
    [void]$process.Start()
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $process.StandardInput.Write($prompt)
    $process.StandardInput.Close()
    $process.WaitForExit()

    $combinedLog = $stdoutTask.Result + $stderrTask.Result
    [System.IO.File]::WriteAllText($stdoutFile, $combinedLog, $utf8NoBom)
    $final = if (Test-Path -LiteralPath $finalFile) {
        [System.IO.File]::ReadAllText($finalFile, [System.Text.Encoding]::UTF8)
    } else {
        $combinedLog
    }
    if ([string]::IsNullOrWhiteSpace($final)) {
        $final = "(empty final response)"
    }

    [pscustomobject]@{
        ExitCode = $process.ExitCode
        Result = $final.Trim() + "`n`nrunner:`n- exit_code: $($process.ExitCode)`n- runner_log: $stdoutFile"
    }
}

if (-not (Test-Path -LiteralPath $Workspace)) {
    throw "Workspace not found: $Workspace"
}
if (-not (Test-Path -LiteralPath (Join-Path $Workspace "AGENTS.md"))) {
    throw "AGENTS.md not found in workspace: $Workspace"
}
New-Item -ItemType Directory -Force -Path $StoreDir, $LogRoot | Out-Null

$modelLabel = if ($Model) { $Model } else { "user-config default" }
Write-RunnerLog "runner started (agent=$Agent, model=$modelLabel, reasoning=$ReasoningEffort, dry_run=$DryRun)"

$processed = 0
while ($true) {
    $task = Get-NextPendingTask
    if (-not $task) {
        if ($Once) { break }
        Start-Sleep -Seconds $PollSeconds
        continue
    }

    Write-RunnerLog "pending task found: $($task.id) from=$($task.from)"
    if ($DryRun) {
        Write-RunnerLog "dry run: would process task $($task.id)"
        if ($Once) { break }
        Start-Sleep -Seconds $PollSeconds
        continue
    }

    $claimed = Claim-Task -Task $task
    if (-not $claimed) { continue }

    try {
        $run = Invoke-CodexTask -Task $claimed
        $completed = Complete-Task -TaskId $claimed.id -Result $run.Result -IsError ($run.ExitCode -ne 0)
    } catch {
        $failure = "Runner failed before Codex completed.`n`nerror:`n$($_.Exception.Message)"
        $completed = Complete-Task -TaskId $claimed.id -Result $failure -IsError $true
    }

    Write-RunnerLog "task $($completed.id) completed with status=$($completed.status)"
    $processed += 1
    if ($Once -or ($MaxTasks -gt 0 -and $processed -ge $MaxTasks)) { break }
}

Write-RunnerLog "runner stopped (processed=$processed)"
