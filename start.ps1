param([switch]$Json)
$ErrorActionPreference = 'Stop'
$financeRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $financeRoot
$resolvedGitRoot = (& git rev-parse --show-toplevel)
if ($LASTEXITCODE -ne 0 -or [System.IO.Path]::GetFullPath($resolvedGitRoot.Trim()).TrimEnd('\') -ine $financeRoot.TrimEnd('\')) {
    throw 'Raiz Git diferente da pasta exclusiva do projeto.'
}
$financePython = Join-Path $financeRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $financePython)) {
    throw 'Ambiente Python existente não encontrado. A instalação e o banco não serão recriados automaticamente.'
}
$financeArguments = @('tools\organiza_runtime.py', 'start')
if ($Json) { $financeArguments += '--json' }
& $financePython @financeArguments
if ($LASTEXITCODE -ne 0) { throw 'Não foi possível iniciar o Organiza. Confira a mensagem acima; não remova nem reinicialize o banco.' }
