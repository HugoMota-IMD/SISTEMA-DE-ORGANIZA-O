param([switch]$Json)
$ErrorActionPreference = 'Stop'
$financeRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $financeRoot
$financePython = Join-Path $financeRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $financePython)) { throw 'Ambiente Python do projeto não encontrado; nenhum processo será encerrado.' }
$financeArguments = @('tools\organiza_runtime.py', 'stop')
if ($Json) { $financeArguments += '--json' }
& $financePython @financeArguments
if ($LASTEXITCODE -ne 0) { throw 'Parada não concluída. Nenhum processo de outro projeto foi encerrado.' }
