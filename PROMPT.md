# Contexto
Jogo o jogo idle de navegador **pokeidle.io/app** com várias contas (hoje 4, quero poder ter mais).
Hoje preciso abrir um navegador diferente para cada conta, o que é trabalhoso e pesado.

# Objetivo
Criar um aplicativo desktop para Windows 10, chamado **easy4idle**, que permita rodar
várias contas do jogo ao mesmo tempo e acompanhar todas numa única janela.

# Requisitos funcionais
1. **Várias contas isoladas**: cada conta roda num perfil de navegador separado
   (cookies, localStorage e sessão próprios), para que os logins não se misturem.
2. **Sessões persistentes**: o login de cada conta continua salvo depois de fechar e abrir o programa.
3. **Visualização simultânea**: layout em grade (2x2, 3x3 etc.) mostrando todas as contas
   ao mesmo tempo, com a opção de ampliar uma conta específica (abas ou tela cheia).
4. **Gerenciar contas**: adicionar, renomear, remover e reordenar contas pela interface.
5. **Compatibilidade com o site**:
   - O captcha da Cloudflare ("Verify you are human") precisa funcionar normalmente
     (usar um motor Chromium atual e um User-Agent realista).
   - A área de transferência precisa funcionar (ex.: o botão "Copiar para o GPT" do jogo).
6. **Extensão do pokeidleguide.io**: integrar a extensão/ferramenta de rota de caça
   (pokeidleguide.io/#hunt) em todos os perfis.
7. **Desempenho**: consumo moderado de CPU/RAM com 4 ou mais contas abertas;
   o jogo deve continuar rodando mesmo quando a conta não está em foco.

# Requisitos técnicos
- Linguagem: Python 3 (informe a versão usada), com ambiente virtual (`.venv`) criado dentro do projeto.
- Lista de dependências em `requirements.txt`.
- Um arquivo `iniciar.bat` que abre o programa com dois cliques, sem precisar ativar o venv à mão.
- Tratamento de erros com log em arquivo (`logs/`), para que o programa não feche
  sem deixar uma mensagem quando der erro.
- Código organizado em módulos e comentado em português.

# Entregáveis
1. Código-fonte completo.
2. `README.md` com instalação, uso e solução de problemas comuns.
3. Passo a passo para testar: adicionar 4 contas, fazer login, reiniciar o programa e confirmar que as sessões continuam salvas.

# Forma de trabalho
- Antes de programar, apresente a arquitetura e as bibliotecas escolhidas, com uma justificativa curta.
- Depois implemente, rode e confirme que o programa abre sem erros.
- Se algum requisito não puder ser atendido (por exemplo, por limitação do site), explique o motivo e sugira uma alternativa.
