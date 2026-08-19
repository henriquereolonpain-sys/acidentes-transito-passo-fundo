# Checklist — ativar o projeto num PC novo

Versão resumida, só pra marcar. Detalhe de cada passo e troubleshooting
estão em [`TRANSICAO.md`](TRANSICAO.md) (roteiro completo) e
[`TRANSICAO_SSH.md`](TRANSICAO_SSH.md) (só a parte da chave).

## Instalar

- [ ] Git — https://git-scm.com/download/win
- [ ] Python 3.12 ou 3.13 — marcar "Add to PATH" no instalador

## Chave SSH (não copiar a do PC antigo — gerar uma nova)

- [ ] `ssh-keygen -t ed25519 -C "henrique.reolon.pain@gmail.com"`
- [ ] Cadastrar a chave pública em **github.com/settings/keys**
      (`Get-Content ~\.ssh\id_ed25519.pub | Set-Clipboard` pra copiar)
- [ ] Testar: `ssh -T git@github.com` → deve confirmar `henriquereolonpain-sys`

## Projeto

- [ ] Clonar:
  ```powershell
  git clone git@github.com:henriquereolonpain-sys/acidentes-transito-passo-fundo.git Projeto_08
  cd Projeto_08
  git config user.name "Hikke"
  git config user.email "henrique.reolon.pain@gmail.com"
  ```
- [ ] `pip install -r requirements.txt`
- [ ] *(opcional)* `streamlit run app/streamlit_app.py` — confirma que o app abre com os dados

## Automação diária

- [ ] Testar na mão primeiro: `python runs/run_diario.py` → conferir que termina com
      "Banco enviado pro GitHub" no `data/diario.log`
- [ ] Registrar a tarefa agendada:
  ```powershell
  $projeto = (Get-Location).Path
  $python = (Get-Command python).Source
  $action = New-ScheduledTaskAction -Execute $python -Argument "runs\run_diario.py" -WorkingDirectory $projeto
  $trigger = New-ScheduledTaskTrigger -Daily -At 19:00
  $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1)
  Register-ScheduledTask -TaskName "AcidentesPF-Diario" -Action $action -Trigger $trigger -Settings $settings -Force
  ```
- [ ] Disparar um teste: `Start-ScheduledTask -TaskName "AcidentesPF-Diario"`
- [ ] Conferir depois: `Get-ScheduledTaskInfo -TaskName "AcidentesPF-Diario"` → `LastTaskResult` deve ser `0`

## Só por último — desligar o PC antigo

- [ ] **Só depois de confirmar o teste acima com sucesso**, no PC antigo:
  ```powershell
  Unregister-ScheduledTask -TaskName "AcidentesPF-Diario" -Confirm:$false
  ```
- [ ] *(opcional)* remover a chave SSH antiga em github.com/settings/keys
