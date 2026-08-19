# Transição para um novo PC

Roteiro para colocar este projeto rodando (dev manual + automação diária)
numa máquina nova. Feito para ser seguido do zero, sem depender do PC antigo.

**Por que gerar uma chave SSH nova em vez de copiar a antiga:** copiar a
chave privada entre máquinas espalha o mesmo segredo por vários lugares.
Gerando uma chave por máquina, cada uma pode ser revogada individualmente
no GitHub (Settings → SSH and GPG keys) sem afetar as outras — inclusive
quando o PC antigo for desativado de vez, é só remover a chave dele de lá.

---

## 1. Instalar os pré-requisitos

- **Git**: https://git-scm.com/download/win
- **Python 3.12 ou 3.13**: https://www.python.org/downloads/ (marcar "Add to PATH" no instalador)

Confirma no PowerShell:
```powershell
git --version
python --version
```

## 2. Gerar uma chave SSH nova (não copiar a do PC antigo)

> Se estiver com o Claude Code te ajudando nesta máquina, vale apontar ele
> pro [`TRANSICAO_SSH.md`](TRANSICAO_SSH.md) — é um briefing focado só
> nessa parte de autenticação, com troubleshooting dos erros mais comuns.

```powershell
ssh-keygen -t ed25519 -C "henrique.reolon.pain@gmail.com"
```
Aceita o caminho padrão (Enter). Senha é opcional — mas se puser senha, a
tarefa agendada do Windows não vai conseguir usar a chave sem interação
(prefira deixar sem senha, já que o repositório roda automação desatendida).

Copia a chave **pública**:
```powershell
Get-Content ~\.ssh\id_ed25519.pub | Set-Clipboard
```

No GitHub: **github.com/settings/keys** → "New SSH key" → cola o conteúdo
copiado → salva.

Testa a conexão:
```powershell
ssh -T git@github.com
```
Deve responder confirmando o usuário `henriquereolonpain-sys`.

## 3. Clonar o repositório

```powershell
cd ~\Documents
git clone git@github.com:henriquereolonpain-sys/acidentes-transito-passo-fundo.git Projeto_08
cd Projeto_08
```

Configura a identidade do git (necessário pro commit automático diário funcionar):
```powershell
git config user.name "Hikke"
git config user.email "henrique.reolon.pain@gmail.com"
```

## 4. Instalar as dependências Python

```powershell
pip install -r requirements.txt
```

O banco de dados (`data/acidentes.duckdb`) já vem dentro do clone — não
precisa rodar nenhum scraper pra começar a usar o app.

## 5. Testar o app localmente (opcional, mas recomendado)

```powershell
streamlit run app/streamlit_app.py
```
Abre em `http://localhost:8501`. Se carregar o mapa com os dados, está tudo certo.

## 6. Testar o pipeline diário manualmente

```powershell
python runs/run_diario.py
```
Acompanha `data/diario.log`. No fim, deve aparecer "Banco enviado pro
GitHub". Se aparecer erro de push, confere se a chave SSH foi mesmo
adicionada no GitHub (passo 2).

## 7. Registrar a tarefa agendada (roda sozinho todo dia às 19h)

```powershell
$projeto = (Get-Location).Path
$python = (Get-Command python).Source
$action = New-ScheduledTaskAction -Execute $python -Argument "runs\run_diario.py" -WorkingDirectory $projeto
$trigger = New-ScheduledTaskTrigger -Daily -At 19:00
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName "AcidentesPF-Diario" -Action $action -Trigger $trigger -Settings $settings -Description "Coleta diaria de acidentes de Passo Fundo (noticias + geocoding + dedup + push)" -Force | Out-Null
Get-ScheduledTask -TaskName "AcidentesPF-Diario"
```

Confirma que registrou (`State: Ready`). Testa disparando na hora:
```powershell
Start-ScheduledTask -TaskName "AcidentesPF-Diario"
# depois de alguns minutos:
Get-ScheduledTaskInfo -TaskName "AcidentesPF-Diario"   # LastTaskResult deve ser 0
```

## 8. Só então: desligar a automação do PC antigo

**Importante: só faça isso depois de confirmar que a tarefa rodou com
sucesso no PC novo pelo menos uma vez** (passo 7), pra não deixar o
projeto um dia sem atualizar.

No PC antigo:
```powershell
Unregister-ScheduledTask -TaskName "AcidentesPF-Diario" -Confirm:$false
```

E, opcionalmente, remove a chave SSH antiga do GitHub
(github.com/settings/keys) já que ela não vai mais ser usada.

---

## O que NÃO precisa ser transferido do PC antigo

- `data/prf_cache/` (CSVs brutos da PRF, ~200MB) — os dados já estão
  resumidos dentro do banco versionado. Se precisar reconstruir do zero
  algum dia: `python runs/run_prf.py`.
- Arquivos `.log` em `data/` — descartáveis.
- A chave SSH antiga — de propósito, cada máquina tem a sua (ver acima).

Tudo o resto (código + banco de dados) já está no `git clone` do passo 3.
