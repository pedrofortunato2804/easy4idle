"""Autoclique de captura: lança pokébolas sozinho nos pokémons abatidos.

No SigmaIDLE, o painel "Captura" (canto da tela) lista os corpos dos monstros
derrubados, do mais perto para o mais longe, cada um com um botão "Lançar".
Este módulo injeta um script que, quando ligado, clica no primeiro botão
"Lançar" habilitado. Depois de cada clique ele espera aquele corpo sumir da
lista (captura resolvida) antes de lançar de novo, para não gastar duas bolas
no mesmo corpo. Se o corpo não sumir em alguns segundos, tenta de novo.

SHINY (opcional, `ultra_shiny` no contas.json): quando aparece um corpo shiny
(linha dourada no painel), o script troca a bola na mão para a Ultra Ball,
lança só nos shinies e, quando eles acabam, volta para a bola que estava antes.
Atenção: no SigmaIDLE, escolher uma bola na bolsa com corpos no chão já
arremessa uma na hora (o jogo escolhe o alvo), então cada troca pode gastar
uma bola extra — uma Ultra ao entrar, a bola comum ao voltar. Sem Ultra Ball
na bolsa (ou se ela "não vale" no lugar), segue lançando a bola de sempre.

CICLO: o autoclique trabalha em turnos — 1 hora lançando, 1 hora parado, e
assim por diante. O turno conta a partir do momento em que ele foi ligado
(salvo no contas.json), então continua certo mesmo depois de reiniciar o
programa. Quem decide se o turno é de lançar ou de pausa é o Python
(`fase`); o script na página só obedece ao liga/desliga.

O script roda no "mundo isolado" (ApplicationWorld): enxerga o DOM da página,
mas o jogo não enxerga o script.
"""
import json
import time
from urllib.parse import urlparse

from PyQt6.QtWebEngineCore import QWebEngineScript

WORLD = QWebEngineScript.ScriptWorldId.ApplicationWorld

# host do jogo -> seletores CSS do painel "Captura" e da bolsa de bolas
SELETORES = {
    "poke.sigmaproject.online": {
        "lancar": "button.hud-captura-lancar",  # botão "Lançar" de cada corpo
        "linha": "li.hud-captura-linha",        # linha de um corpo
        "shiny": "t-shiny",                     # classe da linha de um corpo shiny
        "bolsa": ".hud-bolsa",                  # barra de bolas/poções (".aberta" = gaveta)
        "casa": ".hud-bolsa-casa",              # casa fechada (bola na mão + ▾)
        "alca": ".hud-bolsa-alca",              # ▾ que abre a gaveta
        "fecha": ".hud-bolsa-fecha",            # ✕ que fecha a gaveta
        "bola": "[data-ball]",                  # botão de uma bola (data-ball = id)
    },
}

INTERVALO_MS = 500     # de quanto em quanto tempo procura um corpo
ESPERA_MAX_MS = 4000   # tempo máximo esperando o corpo clicado sumir
TROCA_MS = 1500        # depois de trocar de bola, espera o jogo atualizar
SEM_ULTRA_MS = 60000   # sem Ultra Ball na bolsa: só procura de novo depois disso

TURNO_LANCANDO_S = 60 * 60  # 1 hora lançando...
TURNO_PAUSA_S = 60 * 60     # ...1 hora parado

_JS = r"""(function () {
  if (window.__e4iCaptura) return;
  var SELETORES = %(seletores)s;
  var S = SELETORES[location.hostname];
  var ligado = false, timer = null, pendente = null, desde = 0, lancadas = 0;
  var ultraShiny = false;   // opção "Ultra Ball em shiny"
  var anterior = null;      // id da bola que estava na mão antes de trocar p/ Ultra
  var ocupadoAte = 0;       // espera depois de abrir a gaveta / trocar de bola
  var semUltraAte = 0;      // não achou Ultra Ball: não procura até esse momento
  var shinyLancadas = 0, trocas = 0;

  function habilitado(b) {
    return !!b && !b.disabled && b.getAttribute('aria-disabled') !== 'true';
  }
  function norm(t) {
    return (t || '').normalize('NFD').replace(/[̀-ͯ]/g, '')
                    .toLowerCase().replace(/[^a-z0-9]/g, '');
  }
  // O aria-label da bola é "Nome — dica (xN)": fica só com o nome.
  function nomeBola(b) {
    return ((b.getAttribute('aria-label') || '').split(' — ')[0] || '').trim();
  }
  function ehUltra(b) { return norm(nomeBola(b)).indexOf('ultraball') === 0; }
  function idBola(b) { return b ? b.getAttribute('data-ball') : null; }

  // Botões "Lançar" dos corpos shiny no painel.
  function lancarShinies() {
    var r = [], linhas = document.querySelectorAll(S.linha);
    for (var i = 0; i < linhas.length; i++) {
      if (!linhas[i].classList.contains(S.shiny)) continue;
      var b = linhas[i].querySelector(S.lancar);
      if (b) r.push(b);
    }
    return r;
  }

  function bolsa() { return document.querySelector(S.bolsa); }
  function aberta() { var g = bolsa(); return !!(g && g.classList.contains('aberta')); }
  // Bola na mão: o botão da casa fechada, ou o marcado na gaveta aberta.
  function bolaNaMao() {
    var g = bolsa();
    if (!g) return null;
    if (aberta()) return g.querySelector(S.bola + '.escolhido');
    var casas = g.querySelectorAll(S.casa);
    for (var i = 0; i < casas.length; i++) {
      var b = casas[i].querySelector(S.bola);
      if (b) return b;
    }
    return null;
  }
  function fecharGaveta() {
    var g = bolsa();
    var x = g && aberta() ? g.querySelector(S.fecha) : null;
    if (x) x.click();
  }

  // Põe na mão a bola que `quer(botao)` aceita. Cada chamada dá no máximo um
  // passo (abrir a gaveta ou escolher a bola) e devolve:
  //   'ok' já está na mão · 'andando' deu um passo · 'falta' não tem essa bola
  function trocarPara(quer) {
    var g = bolsa();
    if (!g) return 'falta';
    var atual = bolaNaMao();
    if (atual && !aberta() && quer(atual)) return 'ok';
    if (!aberta()) {
      var casas = g.querySelectorAll(S.casa);
      for (var i = 0; i < casas.length; i++) {
        if (!casas[i].querySelector(S.bola)) continue;
        var alca = casas[i].querySelector(S.alca);
        if (!alca) return 'falta';  // só um tipo de bola na bolsa
        alca.click();
        ocupadoAte = Date.now() + 300;
        return 'andando';
      }
      return 'falta';
    }
    var opcoes = g.querySelectorAll(S.bola);
    for (var j = 0; j < opcoes.length; j++) {
      var o = opcoes[j];
      if (!quer(o) || o.classList.contains('recusado')) continue;
      if (o.classList.contains('escolhido')) { fecharGaveta(); return 'ok'; }
      o.click();  // escolhe (e, com corpos no chão, o jogo já arremessa uma)
      trocas++;
      ocupadoAte = Date.now() + %(troca)d;
      return 'andando';
    }
    fecharGaveta();
    return 'falta';
  }

  function lancar(b) {
    b.click();
    pendente = b;
    desde = Date.now();
    lancadas++;
  }

  function passo() {
    if (!ligado || !S) return;
    // Ainda esperando o corpo do último lançamento sumir?
    if (pendente && pendente.isConnected && Date.now() - desde < %(espera)d) return;
    pendente = null;
    if (Date.now() < ocupadoAte) return;

    if (ultraShiny) {
      var shinies = lancarShinies();
      if (shinies.length && Date.now() >= semUltraAte) {
        var atual = bolaNaMao();
        var r = trocarPara(ehUltra);
        if (r === 'andando' && anterior === null && atual && !ehUltra(atual)) {
          anterior = idBola(atual);
        }
        if (r === 'ok') {
          for (var i = 0; i < shinies.length; i++) {
            if (habilitado(shinies[i])) { lancar(shinies[i]); shinyLancadas++; return; }
          }
          return;  // shiny ainda sem botão ativo: espera, sem gastar Ultra em outro corpo
        }
        if (r === 'andando') return;
        semUltraAte = Date.now() + %(sem_ultra)d;  // sem Ultra: segue com a bola de sempre
      } else if (!shinies.length && anterior !== null) {
        // Shinies resolvidos: volta para a bola de antes
        var volta = anterior;
        var r2 = trocarPara(function (b) { return idBola(b) === volta; });
        if (r2 === 'andando') return;
        anterior = null;  // já voltou (ou essa bola acabou)
      }
    }

    var botoes = document.querySelectorAll(S.lancar);
    for (var k = 0; k < botoes.length; k++) {
      if (habilitado(botoes[k])) { lancar(botoes[k]); return; }
    }
  }

  // Liga/desliga; devolve o que o script está vendo (para o tooltip e o log).
  window.__e4iCaptura = function (on, opcoes) {
    if (opcoes) ultraShiny = !!opcoes.ultraShiny;
    if (on !== undefined && !!on !== ligado) {
      ligado = !!on;
      clearInterval(timer);
      timer = ligado ? setInterval(passo, %(intervalo)d) : null;
      pendente = null;
    }
    var botoes = S ? document.querySelectorAll(S.lancar) : [];
    var habilitados = 0;
    for (var i = 0; i < botoes.length; i++) if (habilitado(botoes[i])) habilitados++;
    var mao = S ? bolaNaMao() : null;
    return { lancadas: lancadas, ligado: ligado, corpos: botoes.length,
             habilitados: habilitados, visibilidade: document.visibilityState,
             shinies: S ? lancarShinies().length : 0, shiny_lancadas: shinyLancadas,
             trocas: trocas, bola: mao ? nomeBola(mao) : null,
             sem_ultra: Date.now() < semUltraAte };
  };
})();"""


# Faz o jogo achar que a página está sempre visível. Quando a conta não está na
# tela (outra aba de jogo, outra conta expandida, janela minimizada) o Qt marca
# a página como "oculta", e o SigmaIDLE só reconecta ao servidor quando ela
# volta a ficar visível — sem conexão o painel "Captura" para de receber
# corpos e o autoclique fica sem onde clicar. Roda no mundo da página (MAIN).
_JS_VISIVEL = """%(cabecalho)s(function () {
  try {
    Object.defineProperty(Document.prototype, 'visibilityState',
                          { get: function () { return 'visible'; }, configurable: true });
    Object.defineProperty(Document.prototype, 'hidden',
                          { get: function () { return false; }, configurable: true });
    // Engole o evento antes de qualquer ouvinte do jogo (captura na window).
    window.addEventListener('visibilitychange',
                            function (e) { e.stopImmediatePropagation(); }, true);
  } catch (e) {}
})();"""


def suportado(url):
    """True se o easy4idle sabe onde fica o botão de lançar neste jogo."""
    return (urlparse(url).hostname or "") in SELETORES


def instalar(profile):
    """Coloca o script (desligado) em todas as páginas do perfil."""
    script = QWebEngineScript()
    script.setName("easy4idle/autocaptura")
    script.setSourceCode(_JS % {
        "seletores": json.dumps(SELETORES),
        "intervalo": INTERVALO_MS,
        "espera": ESPERA_MAX_MS,
        "troca": TROCA_MS,
        "sem_ultra": SEM_ULTRA_MS,
    })
    script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    script.setWorldId(WORLD)
    script.setRunsOnSubFrames(False)
    profile.scripts().insert(script)

    cabecalho = "// ==UserScript==\n" + "".join(
        f"// @match https://{host}/*\n" for host in SELETORES
    ) + "// ==/UserScript==\n"
    visivel = QWebEngineScript()
    visivel.setName("easy4idle/sempre-visivel")
    visivel.setSourceCode(_JS_VISIVEL % {"cabecalho": cabecalho})
    visivel.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    visivel.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    visivel.setRunsOnSubFrames(False)
    profile.scripts().insert(visivel)


def aplicar(page, ligado, ultra_shiny=False, callback=None):
    """Liga/desliga o autoclique na página. `callback(estado: dict | None)` opcional.

    `ultra_shiny`: troca para a Ultra Ball quando houver um corpo shiny.
    """
    opcoes = json.dumps({"ultraShiny": bool(ultra_shiny)})
    js = (f"window.__e4iCaptura ? window.__e4iCaptura({'true' if ligado else 'false'}, "
          f"{opcoes}) : null")
    if callback:
        page.runJavaScript(js, WORLD, callback)
    else:
        page.runJavaScript(js, WORLD)


def fase(inicio, agora=None):
    """Turno atual do ciclo que começou em `inicio` (epoch, s).

    Devolve (lancando: bool, segundos_ate_trocar: int).
    """
    agora = time.time() if agora is None else agora
    ciclo = TURNO_LANCANDO_S + TURNO_PAUSA_S
    pos = max(0.0, agora - inicio) % ciclo
    if pos < TURNO_LANCANDO_S:
        return True, int(TURNO_LANCANDO_S - pos)
    return False, int(ciclo - pos)


def minutos(seg):
    m = max(1, -(-seg // 60))  # arredonda para cima, mínimo 1
    return f"{m // 60}h{m % 60:02d}" if m >= 60 else f"{m} min"
