# Organiza — acesso privado pelo Tailscale

Estado em **29/10/2026**: aplicação **0.1.3** funcionando localmente e pelo **HTTPS privado ativo e testado**. Oito grupos de testes HTTPS reais passaram em base fictícia; a rota oficial foi verificada em leitura. Falta homologar iPhone/dois computadores por outra rede.

## Servidor e base únicos

Servidor confirmado: **DESKTOP-FLDE4SK**, Tailscale **100.108.133.59**. O IP corresponde ao informado por Hugo. Tailscale 1.104.4 estava conectado e MagicDNS ativo; um iPhone aparecia online. Isso não comprova acesso físico ao Organiza.

Aplicação e raiz Git:

```text
C:\Users\USER\Documents\01.Setor Desenvolvimento\01_DESENVOLVIMENTO_LOCAL\SISTEMA-ORGANIZACAO-FINANCEIRA
```

Banco efetivamente configurado e confirmado nos metadados do processo:

```text
C:\Users\USER\Documents\01.Setor Desenvolvimento\01_DESENVOLVIMENTO_LOCAL\SISTEMA-ORGANIZACAO-FINANCEIRA\data\finance.sqlite3
```

A unidade D: e o novo caminho informado não existem nesta sessão. Não foi criado substituto nem movida a instalação. Se D: corresponder a outra máquina, confirme-a antes de qualquer migração; não iniciar outra base financeira oficial.

Todos os quatro dispositivos acessam esta única aplicação/base. Os computadores clientes e o iPhone não precisam de Python, cópia do código ou SQLite. O banco ativo não deve ser sincronizado por Drive/Git. Cada pessoa usa sua conta do Organiza; o administrador associa cada conta ao espaço e ao perfil adequado.

## Endereços

- Local no servidor: **http://127.0.0.1:8765/**.
- Privado ativo: **https://desktop-flde4sk.tail08d4d6.ts.net/** — conectar o Tailscale antes de abrir nos clientes.

O backend fica somente em 127.0.0.1. Não se usa o IP 100.108.133.59:8765 diretamente; o acesso dos clientes será pelo HTTPS do Serve. O DNS privado vem de Self.DNSName informado pelo próprio Tailscale, sem inventar domínio. Serve é acesso da tailnet; Funnel é acesso público e não integra esta configuração. [Serve oficial](https://tailscale.com/docs/features/tailscale-serve), [diferença do Funnel](https://tailscale.com/docs/features/tailscale-funnel).

## Habilitação administrativa concluída

A tentativa inicial retornou **“Serve is not enabled on your tailnet.”**. Hugo depois apresentou a tela **“Serve está pronto para usar”**, com Funnel opcional desmarcado. A liberação passou a permitir aplicar Serve. A rota temporária foi usada e removida após testes; a rota oficial está ativa. **Esse passo já está resolvido; não clicar em Habilitar funil.** O procedimento abaixo fica como referência para recuperação, caso a tailnet seja alterada futuramente.

1. O responsável entra no console administrativo da **mesma tailnet**.
2. Em **DNS**, mantém MagicDNS ativo e habilita **HTTPS Certificates**.
3. Libera o uso de **Serve**, se o console ainda solicitar. **Não habilitar Funnel.** Se a tela oferecer habilitação conjunta obrigatória, interromper e informar a mensagem antes de prosseguir.
4. Depois da liberação, aplicar a rota escopada e testar. A configuração atual da aplicação já aceita somente a origem privada específica.

Referências: [habilitar HTTPS](https://tailscale.com/docs/how-to/set-up-https-certificates) e [CLI Serve](https://tailscale.com/docs/reference/tailscale-cli/serve). A habilitação exige acesso administrativo da tailnet; não foi solicitada nem armazenada senha no projeto.

## Aplicar, conferir e remover apenas a rota do Organiza

Configuração já aplicada. Para consultar ou reaplicar de forma idempotente, executar na raiz exclusiva acima:

```powershell
powershell -NoProfile -File .\start.ps1
.\.venv\Scripts\python.exe tools\configure_tailscale.py check
.\.venv\Scripts\python.exe tools\configure_tailscale.py apply
.\.venv\Scripts\python.exe tools\configure_tailscale.py check --verify
powershell -NoProfile -File .\status.ps1
```

O helper verifica a máquina, DNS, porta, banco existente e configurações atuais; salva snapshot local e recusa outro projeto ou endpoint público em conflito. Aplica somente `tailscale serve --bg --https=443 --set-path=/ http://127.0.0.1:8765`. Nunca usa reset global, clear ou Funnel. Se o Windows negar a alteração do Serve, executar **somente a configuração do Serve** em terminal administrativo; o processo Python do Organiza permanece no usuário comum.

Para remover exclusivamente a rota cujo destino ainda seja este Organiza:

```powershell
.\.venv\Scripts\python.exe tools\configure_tailscale.py disable
```

Isso não para o backend, não apaga dados e não remove serviços alheios. O helper recusa a remoção se o destino tiver mudado. Nunca usar `tailscale serve reset` ou `tailscale funnel` nesta operação.

## Iniciar, consultar e parar

```powershell
powershell -NoProfile -File .\start.ps1
powershell -NoProfile -File .\status.ps1
powershell -NoProfile -File .\stop.ps1
```

Início em segundo plano, sem duplicação. A parada verifica processo, raiz e dono da porta. Porta ocupada por outro aplicativo resulta em erro claro; o outro processo não é encerrado. O banco existente é obrigatório: nenhum destes comandos cria instalação vazia ou aplica migração automática.

Logs operacionais: `data/runtime/lifecycle.log` e `data/runtime/organiza-*.stdout.log`/`stderr.log`. Não registrar senhas, corpos financeiros ou credenciais nesses logs. O status informa separadamente conexão Tailscale e situação da rota Serve. `private_url` é configuração, não prova de disponibilidade; `not_configured` continua pendente.

Se a política local impedir scripts PowerShell, os comandos equivalentes são `.\.venv\Scripts\python.exe tools\organiza_runtime.py start`, `status` e `stop`. Não alterar a política global silenciosamente.

## Inicialização automática opcional

**Permanece desativada.** Para consultar, ativar ou desativar a entrada própria de logon deste usuário:

```powershell
powershell -NoProfile -File .\tools\configure_autostart.ps1
powershell -NoProfile -File .\tools\configure_autostart.ps1 -Enable
powershell -NoProfile -File .\tools\configure_autostart.ps1 -Disable
```

Usa somente uma entrada HKCU Run identificada por esta raiz, com janela oculta e sem administrador. Não cria serviço de sistema. O início ocorre após o logon desse usuário; não promete execução antes do logon. Se a política de execução bloquear scripts, o helper recusa ativar em vez de enfraquecer a política global. A opção Run unattended do Tailscale é independente e não inicia o Organiza; não foi alterada. [Documentação Windows](https://tailscale.com/docs/how-to/run-unattended).

O servidor precisa permanecer **ligado, sem suspensão e conectado à internet**, com Tailscale ativo, para uso remoto por outra rede. Suspensão, desligamento, falha de internet ou saída da tailnet interrompem o acesso. Nenhuma configuração de energia/suspensão foi modificada; o responsável decide esses ajustes explicitamente.

## Dois computadores adicionais

1. Instalar o Tailscale pelo [site oficial](https://tailscale.com/download) e conectar à tailnet autorizada por Hugo.
2. Abrir **https://desktop-flde4sk.tail08d4d6.ts.net/** com Tailscale conectado.
3. Entrar com o acesso individual do Organiza. Se faltar o espaço, o administrador deve associar o usuário ao espaço/perfil; não compartilhar a senha de outra pessoa.
4. Criar atalho no navegador ou, no Windows, Área de Trabalho → Novo → Atalho → colar o endereço HTTPS.

Não instalar Python ou copiar banco nos clientes. Se algum computador também for usado para desenvolvimento, usar uma cópia de código em Git privado **somente após aprovação do remoto**, com banco fictício próprio e fora da operação oficial. Nesta tarefa nenhum remoto foi configurado e nenhum código foi enviado.

## iPhone e homologação física

Com Tailscale conectado à mesma rede autorizada, abrir o endereço HTTPS no Safari. Se desejar, Compartilhar → Adicionar à Tela de Início. Isso é um atalho web, não uma cópia do banco e não oferece edição offline.

Roteiro ainda pendente para iPhone e cada computador adicional:

1. Abrir o HTTPS com Tailscale ativo e conferir certificado sem ignorar alertas.
2. Entrar/sair com conta individual e conferir somente os espaços/perfis autorizados.
3. Usar um espaço fictício separado para criar conta/compra e confirmar pagamento; conferir atualização em outro dispositivo. Leitor deve permanecer sem permissão de gravação.
4. Em duas sessões, confirmar a mesma parcela de teste: apenas um pagamento deve ser aceito; o outro deve exigir nova conferência, sem sobrescrita silenciosa.
5. Reiniciar apenas o Organiza e conferir persistência dos dados e das sessões.
6. No iPhone, desligar Wi-Fi e repetir por dados móveis com Tailscale ativo. Em um computador, repetir por outra rede autorizada.

Nenhum aparelho físico ou acesso por outra rede foi testado ou confirmado nesta execução. O fato de o iPhone aparecer online no Tailscale não substitui esses testes.

## Testes técnicos reproduzíveis

```powershell
.\.venv\Scripts\python.exe manage.py test finance --verbosity 1
.\.venv\Scripts\python.exe tools\verify_runtime.py
.\.venv\Scripts\python.exe tools\verify_private_access.py
.\.venv\Scripts\python.exe -m unittest tools.test_tailscale_config
```

Os testes de gravação usam bancos fictícios isolados. O ensaio HTTP não comprova TLS. Para ensaiar HTTPS real sem escrever no banco oficial, reservar uma rota temporária HTTPS **8443 → 127.0.0.1:8771**, somente após inspecionar que não pertence a outro projeto, e executar:

```powershell
.\.venv\Scripts\python.exe tools\verify_private_access.py --base-url https://desktop-flde4sk.tail08d4d6.ts.net:8443 --port 8771
```

Esse script inicia/encerra somente seu backend/banco fictício e valida certificado normalmente. A rota temporária precisa ser criada e removida separadamente, com flags da porta 8443 e caminho `/`, nunca com reset. **Executado com sucesso em 29/10/2026: oito grupos HTTPS reais aprovados**, evidência `test-results/private-access-https-evidence.json`; backend 8771 e rota 8443 encerrados/removidos depois. A rota oficial 443 foi aplicada e conferida em HTTP/HTTPS sem gravação no banco oficial. Novas repetições exigem verificar previamente que a porta de teste está livre e preservar a rota oficial. Fontes de proxy: [Waitress](https://docs.pylonsproject.org/projects/waitress/en/latest/reverse-proxy.html) e [Django](https://docs.djangoproject.com/en/5.2/ref/settings/).
