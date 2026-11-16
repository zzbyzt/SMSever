$ErrorActionPreference = 'Stop'
$appRoot = Split-Path -Parent $PSScriptRoot
$runtimeDir = Join-Path (Split-Path -Parent $appRoot) 'runtime'
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
$pythonCandidates = @((Join-Path $appRoot '.venv\Scripts\python.exe'), 'D:\anaconda\python.exe')
$pythonExe = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $pythonExe) { $pythonExe = (Get-Command python -ErrorAction Stop).Source }
$chosenPort = $null
foreach ($candidatePort in 8766..8776) {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$candidatePort/api/health" -TimeoutSec 1
        if ($health.app -eq 'cellmem-ui') { Start-Process "http://127.0.0.1:$candidatePort"; exit 0 }
    } catch {}
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $candidatePort)
        $listener.Start(); $listener.Stop(); $chosenPort = $candidatePort; break
    } catch {}
}
if (-not $chosenPort) { throw 'No free local port between 8766 and 8776.' }
$serverScript = Join-Path $PSScriptRoot 'server.py'
$arguments = @('-X', 'utf8', ('"' + $serverScript + '"'), '--port', "$chosenPort")
$process = Start-Process -FilePath $pythonExe -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDir 'server.stdout.log') -RedirectStandardError (Join-Path $runtimeDir 'server.stderr.log')
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Milliseconds 300
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$chosenPort/api/health" -TimeoutSec 1
        if ($health.app -eq 'cellmem-ui') {
            @{pid=$process.Id; port=$chosenPort; url="http://127.0.0.1:$chosenPort"} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeDir 'server.json') -Encoding UTF8
            Start-Process "http://127.0.0.1:$chosenPort"
            exit 0
        }
    } catch {}
}
throw "CellMem failed to start; inspect $runtimeDir\server.stderr.log"
