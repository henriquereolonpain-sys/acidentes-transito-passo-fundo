# Transição de chave SSH — briefing para o Claude te ajudar numa máquina nova

> Se você é uma instância do Claude Code lendo isto numa máquina nova, sem
> memória da conversa onde isto foi escrito: este arquivo te dá o contexto
> pra ajudar o usuário a configurar a autenticação Git deste projeto do
> zero. Leia esta seção antes de agir.

## Situação

Este repositório (`acidentes-transito-passo-fundo`) tem uma **rotina diária
automatizada** (`runs/run_diario.py`, disparada por uma tarefa agendada do
Windows) que faz `git commit` + `git push` sozinha todo dia. Isso exige que
a máquina que roda a tarefa tenha uma **chave SSH cadastrada no GitHub** do
usuário (`henriquereolonpain-sys`), sem senha na chave (a tarefa roda sem
interação humana).

O projeto estava rodando num PC que foi desativado. O usuário está
configurando isso numa máquina nova. **Não existe cópia da chave privada
antiga disponível** — de propósito: cada máquina deve ter sua própria
chave, cadastrada e revogável independentemente no GitHub
(`github.com/settings/keys`).

Remote do repositório: `git@github.com:henriquereolonpain-sys/acidentes-transito-passo-fundo.git`
(SSH — não HTTPS; os scripts do projeto assumem esse remote já autenticado).

## O que fazer, em ordem

1. **Verificar se já existe uma chave SSH utilizável** nesta máquina:
   ```powershell
   Test-Path ~\.ssh\id_ed25519
   ```
   Se `True`, pule para o passo 3 (só falta testar/cadastrar).

2. **Gerar uma chave nova** (ed25519, sem passphrase — a automação roda desatendida):
   ```powershell
   ssh-keygen -t ed25519 -C "henrique.reolon.pain@gmail.com" -N '""'
   ```
   (Se preferir interativo, rode sem `-N '""'` e aperte Enter duas vezes
   quando pedir senha, deixando em branco.)

3. **Copiar a chave pública e cadastrar no GitHub:**
   ```powershell
   Get-Content ~\.ssh\id_ed25519.pub | Set-Clipboard
   ```
   Abrir `github.com/settings/keys` → "New SSH key" → colar → salvar.
   (Isso só o usuário consegue fazer — precisa estar logado no navegador.)

4. **Testar a autenticação:**
   ```powershell
   ssh -T git@github.com
   ```
   Sucesso = mensagem confirmando `Hi henriquereolonpain-sys! You've
   successfully authenticated...`. Se pedir senha ou disser
   `Permission denied (publickey)`, ver Troubleshooting abaixo.

5. **Confirmar que o push funciona de verdade** (não só a autenticação SSH,
   mas o fluxo completo do projeto):
   ```powershell
   cd <pasta do repo clonado>
   git commit --allow-empty -m "teste de autenticacao"
   git push origin main
   git log --oneline -1   # confirma que subiu
   ```
   Se subiu, a automação (`runs/run_diario.py` → `_commit_push()`) vai funcionar
   igual, porque usa exatamente o mesmo mecanismo (`git push` via subprocess,
   sem token nem senha embutida — depende só da chave SSH do sistema).

## Troubleshooting comum

- **`Permission denied (publickey)`** → a chave pública não foi cadastrada
  no GitHub certo, ou está numa conta diferente da dona do repositório.
  Reconferir passo 3.
- **`ssh-agent` pedindo senha mesmo com `-N ""`** → a chave foi gerada com
  passphrase por engano. Gerar de novo (`ssh-keygen -t ed25519 ...`,
  sobrescrevendo) e ter certeza de deixar em branco — senão a tarefa
  agendada trava esperando input que nunca vem.
- **`git push` funciona manual mas falha na tarefa agendada** → a tarefa
  roda como um usuário/sessão diferente do PowerShell interativo, e pode
  não estar carregando o `ssh-agent`. Verificar se o serviço `ssh-agent`
  do Windows está com startup automático (`Get-Service ssh-agent`) e a
  chave adicionada a ele (`ssh-add -l`); se a chave não tem passphrase,
  normalmente nem precisa do agent — o `ssh.exe` lê `~/.ssh/id_ed25519`
  direto.
- **Host key verification failed** → primeira conexão SSH ao GitHub nessa
  máquina; rodar `ssh -T git@github.com` uma vez manualmente e aceitar
  (`yes`) o fingerprint antes de depender da tarefa agendada (ela não
  consegue responder a esse prompt sozinha).

## Depois de confirmar que funciona

Seguir o resto da configuração em [`TRANSICAO.md`](TRANSICAO.md) (clone,
dependências Python, registro da tarefa agendada). Este arquivo cobre só a
parte de autenticação; o outro cobre o projeto inteiro.
