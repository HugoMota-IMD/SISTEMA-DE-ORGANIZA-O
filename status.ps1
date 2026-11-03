param([switch]$Json)
$ErrorActionPreference = 'Stop'
$financeRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $financeRoot
$financePython = Join-Path $financeRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $financePython)) { throw 'Ambiente Python do projeto não encontrado.' }
$financeArguments = @('tools\organiza_runtime.py', 'status')
if ($Json) { $financeArguments += '--json' }
& $financePython @financeArguments
if ($LASTEXITCODE -ne 0) { throw 'Não foi possível consultar o estado do Organiza.' }
