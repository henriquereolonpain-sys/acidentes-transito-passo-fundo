# Registra a rotina diária no Agendador de Tarefas do Windows.
# Execute UMA VEZ (clique direito > Executar com PowerShell, ou no terminal):
#   powershell -ExecutionPolicy Bypass -File agendar_diario.ps1
#
# A tarefa roda todo dia às 19:00. Se a máquina estiver desligada nesse horário,
# ela executa assim que a máquina ligar (StartWhenAvailable).
# Para remover:  Unregister-ScheduledTask -TaskName "AcidentesPF-Diario" -Confirm:$false

$ErrorActionPreference = "Stop"

# Caminhos absolutos
$projeto = Split-Path -Parent $MyInvocation.MyCommand.Definition
$python  = (Get-Command python).Source
$script  = Join-Path $projeto "run_diario.py"

Write-Host "Projeto: $projeto"
Write-Host "Python:  $python"

# Ação: rodar run_diario.py no diretório do projeto
$action = New-ScheduledTaskAction -Execute $python -Argument "run_diario.py" -WorkingDirectory $projeto

# Gatilho: diário às 19:00
$trigger = New-ScheduledTaskTrigger -Daily -At 19:00

# Configurações: roda se perdeu o horário (máquina estava desligada), sem exigir AC
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)

# Registra (sobrescreve se já existir)
Register-ScheduledTask `
    -TaskName "AcidentesPF-Diario" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Coleta diária de acidentes de Passo Fundo (notícias + geocoding + dedup)" `
    -Force | Out-Null

Write-Host ""
Write-Host "Tarefa 'AcidentesPF-Diario' registrada. Roda todo dia as 19:00." -ForegroundColor Green
Write-Host "Para rodar agora e testar:  Start-ScheduledTask -TaskName 'AcidentesPF-Diario'"
Write-Host "Para ver o status:          Get-ScheduledTask -TaskName 'AcidentesPF-Diario'"
Write-Host "Para remover:               Unregister-ScheduledTask -TaskName 'AcidentesPF-Diario' -Confirm:`$false"
