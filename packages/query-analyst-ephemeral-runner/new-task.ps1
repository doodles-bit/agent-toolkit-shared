[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Message,
    [string]$From = "local-user",
    [string]$To = "query-analyst",
    [string]$StoreDir = ""
)

$ErrorActionPreference = "Stop"
$ScriptRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
if ([string]::IsNullOrWhiteSpace($StoreDir)) {
    $StoreDir = Join-Path $ScriptRoot "runtime/store"
}
New-Item -ItemType Directory -Force -Path $StoreDir | Out-Null

$task = [ordered]@{
    id = [guid]::NewGuid().ToString()
    from = $From
    to = $To
    message = $Message
    status = "pending"
    created_at = (Get-Date).ToUniversalTime().ToString("o")
    claimed_at = $null
    completed_at = $null
    result = $null
    is_error = $false
}

$path = Join-Path ([System.IO.Path]::GetFullPath($StoreDir)) "$($task.id).json"
$json = $task | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($path, $json, [System.Text.UTF8Encoding]::new($false))

[pscustomobject]@{
    task_id = $task.id
    status = $task.status
    path = $path
}
