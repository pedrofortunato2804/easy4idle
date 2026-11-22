# easy4idle

Aplicativo desktop para Windows que roda **várias contas de jogos idle de navegador ao mesmo tempo, numa única janela**, em vez de abrir um navegador diferente para cada conta.

Cada conta usa um perfil de navegador isolado (cookies, localStorage e sessão próprios), então os logins não se misturam e continuam salvos depois de fechar o programa.

## Recursos

- **Vários jogos**: cada jogo é uma aba no menu lateral (PokeIdle, SigmaIDLE, Twitch… ou qualquer site que você adicionar).
- **Várias contas por jogo**, exibidas em grade com número de colunas ajustável, e a opção de ampliar uma conta só.
- **Sessões persistentes**: o login de cada conta fica salvo em `perfis/<id>`.
- **Roda em segundo plano**: o Chromium não "congela" as contas quando a janela está minimizada ou atrás de outras.
- **Extensão /hunt** do PokeIdle injetada em todas as contas, mostrando as melhores hunts por XP/h e ouro/h.
- **Auto-captura** (SigmaIDLE): clica sozinho em "Lançar" nos pokémons abatidos, em turnos de 1 hora ligada e 1 hora parada.
- **Streams (Twitch/Kick)** para acumular pontos de canal:
  - usa o motor do Microsoft Edge (WebView2), que toca H.264/AAC;
  - força a qualidade mínima do player para economizar CPU e internet;
  - resgata automaticamente o baú de bônus de pontos da Twitch (opcional);
  - vários quadros podem compartilhar o mesmo login.
- **Log de erros** em `logs/easy4idle.log`.

## Requisitos

- Windows 10 ou 11
- [Python 3.12](https://www.python.org/downloads/) instalado pelo site python.org (não pela Microsoft Store), com a opção **"Add python.exe to PATH"** marcada
- Microsoft Edge WebView2 (já vem no Windows 10/11), usado só para as streams

## Instalação e uso

1. Baixe o projeto:
   ```
   git clone https://github.com/pedrofortunato2804/easy4idle.git
   ```
   ou use **Code → Download ZIP** no GitHub e extraia.
2. Dê dois cliques em **`iniciar.bat`**.

Na primeira execução, o `iniciar.bat` cria o ambiente virtual (`.venv`) e instala as dependências do `requirements.txt`. Nas próximas, ele abre o programa direto. Quando o `requirements.txt` muda, ele reinstala as dependências sozinho.

Para rodar manualmente:

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python easy4idle.py
```

## Como usar

- **Adicionar jogo**: botão **＋** no menu lateral. Clique com o botão direito numa aba para renomear o jogo, alterar a URL ou removê-lo.
- **Adicionar conta**: **＋ Adicionar conta** na barra do jogo. Cada conta nova abre com um login em branco: faça o login no quadro, e ele fica salvo.
- **Opções de uma conta**: clique no nome da conta para renomear, trocar o endereço ou abrir outro quadro com o mesmo login.
- **Barra do jogo**: recarregar todas, silenciar todas, mostrar todas, auto-captura em todas (🎯), resgate em todas (🎁) e atualizar a extensão /hunt (🧩).

### Atalhos

| Atalho | Ação |
|---|---|
| `Ctrl+1` … `Ctrl+9` | Amplia a conta 1 a 9 do jogo atual |
| `Esc` | Volta a mostrar todas as contas |
| `Ctrl+Tab` / `Ctrl+PgDown` | Próximo jogo |
| `Ctrl+Shift+Tab` / `Ctrl+PgUp` | Jogo anterior |

## Configuração (`contas.json`)

Os jogos e as contas ficam salvos em `contas.json`, e o programa grava esse arquivo sozinho. Se ele não existir, o easy4idle cria uma configuração padrão com 4 contas de PokeIdle.

O arquivo **[`contas.exemplo.json`](contas.exemplo.json)** mostra o formato. Para usá-lo como ponto de partida, copie com o nome `contas.json`.

Campos principais de cada conta:

| Campo | Descrição |
|---|---|
| `id` | Identificador único entre todos os jogos. Também é o nome da pasta do perfil em `perfis/`. |
| `nome` | Nome exibido no quadro. |
| `zoom` | Zoom da página (ex.: `0.75`). |
| `mudo` | `true` para começar sem som. |
| `url` | *(opcional)* Endereço próprio do quadro, como o canal da stream. Substitui a URL do jogo. |
| `perfil` | *(opcional)* `id` de outra conta cujo login este quadro usa. Serve para abrir várias streams com um login só. |
| `autocaptura` | *(opcional, SigmaIDLE)* Liga ou desliga o autoclique de captura. |

> `contas.json` e a pasta `perfis/` não vão para o Git (estão no `.gitignore`), porque contêm os nomes das suas contas e as sessões logadas. **Nunca compartilhe a pasta `perfis/`**: ela dá acesso às suas contas.

## Estrutura do projeto

```
easy4idle.py          ponto de entrada
iniciar.bat           cria o .venv, instala dependências e abre o programa
requirements.txt      dependências (PyQt6, PyQt6-WebEngine, pythonnet, pywebview)
contas.exemplo.json   modelo de configuração
app/
  janela.py           janela principal e menu lateral de jogos
  jogo.py             aba de um jogo: barra de ferramentas e grade de contas
  painel.py           quadro de uma conta (cabeçalho e página)
  motores.py          motores de navegador: Qt WebEngine (jogos) e Edge (streams)
  edge.py             Microsoft Edge (WebView2) embutido no Qt
  paginas.py          perfis de navegador, páginas e pop-ups de login
  extensoes.py        download e injeção da extensão /hunt
  autocaptura.py      autoclique de pokébolas (SigmaIDLE)
  streaming.py        Twitch/Kick: qualidade mínima e resgate de pontos
  config.py           leitura, migração e gravação do contas.json
  caminhos.py         caminhos usados pelo programa
  registro.py         log em arquivo e captura de erros
extensoes/hunt/       extensão /hunt descompactada
perfis/               perfis de navegador de cada conta (gerado, ignorado pelo Git)
logs/                 easy4idle.log (gerado, ignorado pelo Git)
```

## Solução de problemas

**"Python não encontrado" ao abrir o `iniciar.bat`**
Instale o Python 3.12 pelo [python.org](https://www.python.org/downloads/) e marque **"Add python.exe to PATH"**. Não use a versão da Microsoft Store.

**"Ambiente Python inválido neste PC" ou erro ao criar o `.venv`**
Acontece quando a pasta `.venv` veio de outro computador ou ficou incompleta. O `iniciar.bat` tenta recriá-la sozinho. Se não conseguir, feche o easy4idle, apague a pasta `.venv` manualmente e rode o `iniciar.bat` de novo.

**Falha ao instalar as dependências**
Verifique a conexão com a internet e rode o `iniciar.bat` novamente.

**O programa fechou ou não abriu**
Veja os detalhes do erro em `logs/easy4idle.log`.

**A extensão /hunt não aparece**
Ela é baixada da Chrome Web Store na primeira execução. Se falhar, use **🧩 Atualizar /hunt** na barra do jogo e depois feche e abra o easy4idle.

**A stream não toca ou fica parada**
- Confira se o Microsoft Edge WebView2 está instalado.
- Na Kick, responda o aviso de cookies ou a confirmação de idade dentro do quadro: o status do quadro avisa quando é preciso.

**Uma conta perdeu o login**
O login fica na pasta `perfis/<id da conta>`. Se você mudar o `id` de uma conta no `contas.json`, ela passa a usar outra pasta e abre deslogada.
