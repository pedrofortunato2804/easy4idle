# Contexto
Assisto lives na Twitch e na Kick só para acumular pontos de canal, com mais de uma conta
e em vários canais ao mesmo tempo. Já tentei fazer isso dentro de outro programa meu
(easy4idle, PyQt6), mas com 7 lives abertas o consumo de CPU e memória ficou alto demais.
Quero um programa separado, só para isso, que seja o mais leve possível.

# Objetivo
Criar um aplicativo desktop para Windows 10/11, chamado **easy4lives**, que rode várias lives
ao mesmo tempo numa única janela, gastando o mínimo de CPU, memória e internet.

# Requisitos funcionais
1. **Canais**: adicionar, remover, renomear e reordenar quadros pela interface. Aceitar
   `gaules`, `twitch.tv/gaules`, `kick.com/xqc` ou o link completo.
2. **Logins**: várias contas (Twitch e Kick), cada uma com perfil isolado e sessão
   persistente. Vários quadros podem usar o mesmo login (ex.: conta A assistindo 3 canais).
3. **Visualização**: grade com número de colunas ajustável e opção de ampliar um quadro.
4. **Qualidade mínima** sempre:
   - Twitch: gravar a preferência de qualidade que o player lê ao abrir (160p) antes da
     página carregar.
   - Kick: o player não guarda a escolha. Abrir o menu "Qualidade" e clicar na menor
     resolução, e refazer se o player voltar ao automático.
5. **Resgate automático do baú de bônus da Twitch** (liga/desliga por quadro e "em todos"),
   com contador de resgates. O baú só aparece com o chat aberto.
6. **Avisos que travam a live**: clicar sozinho em "Começar a assistir" no aviso de conteúdo
   adulto da Twitch. Na Kick, avisar no quadro quando o aviso de cookies ou a confirmação de
   idade estiver na frente do player (o usuário responde uma vez).
7. **Status por quadro**: tocando / vídeo parado / offline / carregando, e um alerta quando a
   live caiu ou o vídeo parou (pontos não sobem).
8. **Som**: todos os quadros começam mudos; botão de silenciar todos.

# Desempenho (prioridade máxima)
- Twitch e Kick usam vídeo H.264/AAC: o motor precisa tocar isso. O Qt WebEngine padrão não
  toca. No easy4idle usei o Microsoft Edge WebView2, que funciona; avalie se é a melhor escolha.
- Quadros do mesmo login devem compartilhar o mesmo ambiente/processo do navegador (mesma
  pasta de dados), em vez de abrir um navegador inteiro por quadro.
- Medir e mostrar CPU e memória por quadro e no total. Testar com 7 lives abertas e informar
  os números antes e depois de cada otimização.
- Avaliar e aplicar o que reduzir consumo sem parar a contagem de pontos: resolução mínima,
  chat leve ou recolhido (sem quebrar o baú), bloquear anúncios/recursos pesados que não sejam
  o player, limite de memória do WebView2, reduzir o tamanho do quadro.
- Não ocultar nem "congelar" os quadros fora da tela se isso pausar o player: os pontos
  exigem que a live esteja tocando. Explique o que o motor faz com páginas fora da tela.
- Opção de limitar quantas lives ficam abertas ao mesmo tempo.

# Requisitos técnicos
- Proponha a linguagem/stack (ex.: Python + WebView2, ou C#/.NET + WebView2), com justificativa
  curta focada em consumo de recursos.
- Configuração em `config.json` gravada pelo próprio programa (com gravação segura via arquivo
  temporário), mais um `config.exemplo.json`.
- Um `iniciar.bat` que abre o programa com dois cliques (cria o ambiente e instala dependências
  na primeira vez).
- Log de erros em `logs/`, para o programa nunca fechar sem deixar mensagem.
- Código organizado em módulos e comentado em português.

# Entregáveis
1. Código-fonte completo.
2. `README.md` com instalação, uso e solução de problemas (live não toca, avisos da Kick, baú
   não resgata).
3. Passo a passo de teste: 2 logins, 3 canais em cada, reiniciar o programa e confirmar que as
   sessões continuam salvas, a qualidade fica no mínimo e o baú é resgatado.
4. Tabela de consumo (CPU/memória) com 1, 3 e 7 lives.

# Forma de trabalho
- Antes de programar, apresente a arquitetura e as bibliotecas, com justificativa curta.
- Depois implemente, rode e confirme que o programa abre sem erros.
- Se algo não puder ser atendido (limitação dos sites ou do motor), explique o motivo e sugira
  uma alternativa.
