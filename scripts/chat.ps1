<#
.SYNOPSIS
    Interactive terminal chat against the firesim-ai /chat API.

.DESCRIPTION
    Issues a session token from POST /api/session, then loops reading
    messages from the terminal and posting them to POST /chat, printing
    the agent's reply. Type 'exit' or 'quit' to end the session.

.PARAMETER ApiBaseUrl
    Base URL of the running firesim-ai API. Defaults to http://localhost:8000.

.EXAMPLE
    .\scripts\chat.ps1
    .\scripts\chat.ps1 -ApiBaseUrl http://localhost:8000
#>

param(
    [string]$ApiBaseUrl = "http://localhost:8000"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

function Get-ErrorDetail($err) {
    if ($err.ErrorDetails -and $err.ErrorDetails.Message) {
        return $err.ErrorDetails.Message
    }
    return $err.Exception.Message
}

Write-Host "firesim-ai chat - connecting to $ApiBaseUrl ..." -ForegroundColor DarkGray

try {
    $health = Invoke-RestMethod -Uri "$ApiBaseUrl/health" -Method GET
    if (-not $health.browser_connected) {
        Write-Host "Warning: browser_connected is false - map navigation replies may fail, but chat will still work." -ForegroundColor Yellow
    }
} catch {
    Write-Host "Could not reach $ApiBaseUrl/health - is the container running? ($($_.Exception.Message))" -ForegroundColor Red
    exit 1
}

try {
    $session = Invoke-RestMethod -Uri "$ApiBaseUrl/api/session" -Method POST
} catch {
    Write-Host "Failed to create a session: $(Get-ErrorDetail $_)" -ForegroundColor Red
    exit 1
}

$headers = @{ "X-Session-Id" = $session.session_id }
Write-Host "Session started ($($session.session_id)). Type 'exit' to quit.`n" -ForegroundColor DarkGray

while ($true) {
    Write-Host "You: " -ForegroundColor Cyan -NoNewline
    $message = Read-Host
    if ([string]::IsNullOrWhiteSpace($message)) { continue }
    if ($message -in @("exit", "quit")) { break }

    $body = @{ message = $message } | ConvertTo-Json

    try {
        $response = Invoke-RestMethod -Uri "$ApiBaseUrl/chat" -Method POST `
            -ContentType "application/json" -Headers $headers -Body $body
        Write-Host "Agent: " -ForegroundColor Green -NoNewline
        Write-Host $response.reply
    } catch {
        Write-Host "Error: $(Get-ErrorDetail $_)" -ForegroundColor Red
    }
    Write-Host ""
}

Write-Host "Session ended." -ForegroundColor DarkGray
