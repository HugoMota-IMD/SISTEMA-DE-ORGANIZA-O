<#
.SYNOPSIS
Opção reversível de inicialização do Organiza no logon deste usuário, sem administrador.
.EXAMPLE
powershell -File .\tools\configure_autostart.ps1 -Enable
.EXAMPLE
powershell -File .\tools\configure_autostart.ps1 -Disable
#>
[CmdletBinding(DefaultParameterSetName='Status')]
param(
    [Parameter(ParameterSetName='Enable', Mandatory=$true)][switch]$Enable,
    [Parameter(ParameterSetName='Disable', Mandatory=$true)][switch]$Disable
)
$ErrorActionPreference = 'Stop'
$financeRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $financeRoot
$financeSha = [System.Security.Cryptography.SHA256]::Create()
try {
    $financeDigest = $financeSha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($financeRoot.ToLowerInvariant()))
    $financeId = ([System.BitConverter]::ToString($financeDigest) -replace '-', '').ToLowerInvariant().Substring(0,16)
} finally { $financeSha.Dispose() }
$financeRegistry = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$financeName = 'Organiza-' + $financeId
$financePowerShell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$financeCommand = '"' + $financePowerShell + '" -NoProfile -NonInteractive -WindowStyle Hidden -File "' + (Join-Path $financeRoot 'start.ps1') + '"'
if ($Enable) {
    $financePython = Join-Path $financeRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $financePython)) { throw 'Ambiente Python existente não encontrado; opção automática não ativada.' }
    & $financePython tools\organiza_runtime.py check --json
    if ($LASTEXITCODE -ne 0) { throw 'Confira o banco e a instalação antes de ativar.' }
    if ((Get-ExecutionPolicy) -eq 'Restricted') { throw 'A política do Windows bloqueia scripts PowerShell. A opção não foi ativada. Peça ao responsável para autorizar somente os scripts locais do Organiza; não altere a política global automaticamente.' }
    if (-not (Test-Path -LiteralPath $financeRegistry)) { New-Item -Path $financeRegistry -Force | Out-Null }
    New-ItemProperty -LiteralPath $financeRegistry -Name $financeName -Value $financeCommand -PropertyType String -Force | Out-Null
    Write-Host 'Inicialização no logon deste usuário ativada. Não foi criado serviço administrativo nem alterada energia/suspensão.'
} elseif ($Disable) {
    if (Test-Path -LiteralPath $financeRegistry) {
        $financeExisting = Get-ItemProperty -LiteralPath $financeRegistry -Name $financeName -ErrorAction SilentlyContinue
        if ($financeExisting) { Remove-ItemProperty -LiteralPath $financeRegistry -Name $financeName }
    }
    Write-Host 'Somente a entrada de inicialização deste Organiza foi desativada. O processo atual não foi parado.'
} else {
    $financeExisting = if (Test-Path -LiteralPath $financeRegistry) { Get-ItemProperty -LiteralPath $financeRegistry -Name $financeName -ErrorAction SilentlyContinue }
    if ($financeExisting) { Write-Host 'Inicialização no logon: ativada para esta instalação.' } else { Write-Host 'Inicialização no logon: desativada para esta instalação.' }
}
