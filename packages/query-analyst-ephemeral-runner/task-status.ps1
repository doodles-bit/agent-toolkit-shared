[CmdletBinding()]
param(
    [string]$TaskId = "",
    [string]$StoreDir = ""
)

$ErrorActionPreference = "Stop"
$ScriptRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
if ([string]::IsNullOrWhiteSpace($StoreDir)) {
    $StoreDir = Join-Path $ScriptRoot "runtime/store"
}

if (-not (Test-Path -LiteralPath $StoreDir)) {
    throw "StoreDir not found: $StoreDir"
}

if ($TaskId) {
    $path = Join-Path $StoreDir "$TaskId.json"
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Task not found: $TaskId"
    }
    Get-Content -Raw -LiteralPath $path | ConvertFrom-Json
    exit 0
}

Get-ChildItem -LiteralPath $StoreDir -Filter "*.json" -File |
    ForEach-Object {
        try { Get-Content -Raw -LiteralPath $_.FullName | ConvertFrom-Json } catch { $null }
    } |
    Where-Object { $_ } |
    Sort-Object created_at -Descending |
    Select-Object id, from, to, status, created_at, claimed_at, completed_at, is_error
