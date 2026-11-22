"""Autoclique de captura: lança pokébolas sozinho nos pokémons abatidos.

No SigmaIDLE, o painel "Captura" (canto da tela) lista os corpos dos monstros
derrubados, do mais perto para o mais longe, cada um com um botão "Lançar".
Este módulo injeta um script que, quando ligado, clica no primeiro botão
"Lançar" habilitado. Depois de cada clique ele espera aquele corpo sumir da
lista (captura resolvida) antes de lançar de novo, para não gastar duas bolas
no mesmo corpo. Se o corpo não sumir em alguns segundos, tenta de novo.

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

# host do jogo -> seletor CSS do botão de lançar a bola num corpo
SELETORES = {
    "poke.sigmaproject.online": "button.hud-captura-lancar",
}

INTERVALO_MS = 500     # de quanto em quanto tempo procura um corpo
ESPERA_MAX_MS = 4000   # tempo máximo esperando o corpo clicado sumir

TURNO_LANCANDO_S = 60 * 60  # 1 hora lançando...
TURNO_PAUSA_S = 60 * 60     # ...1 hora parado

_JS = """(function () {
  if (window.__e4iCaptura) return;
  var SELETORES = %(seletores)s;
  var seletor = SELETORES[location.hostname];
  var ligado = false, timer = null, pendente = null, desde = 0, lancadas = 0;

  function passo() {
    if (!ligado || !seletor) return;
    // Ainda esperando o corpo do último lançamento sumir?
    if (pendente && pendente.isConnected && Date.now() - desde < %(espera)d) return;
    pendente = null;
    var botoes = document.querySelectorAll(seletor);
    for (var i = 0; i < botoes.length; i++) {
      var b = botoes[i];
      if (b.disabled || b.getAttribute('aria-disabled') === 'true') continue;
      b.click();
      pendente = b;
      desde = Date.now();
      lancadas++;
      return;
    }
  }

  // Liga/desliga; devolve o que o script está vendo (para o tooltip e o log).
  window.__e4iCaptura = function (on) {
    if (on !== undefined && !!on !== ligado) {
      ligado = !!on;
      clearInterval(timer);
      timer = ligado ? setInterval(passo, %(intervalo)d) : null;
      pendente = null;
    }
    var botoes = seletor ? document.querySelectorAll(seletor) : [];
    var habilitados = 0;
    for (var i = 0; i < botoes.length; i++) if (!botoes[i].disabled) habilitados++;
    return { lancadas: lancadas, ligado: ligado, corpos: botoes.length,
             habilitados: habilitados, visibilidade: document.visibilityState };
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


def aplicar(page, ligado, callback=None):
    """Liga/desliga o autoclique na página. `callback(estado: dict | None)` opcional."""
    js = f"window.__e4iCaptura ? window.__e4iCaptura({'true' if ligado else 'false'}) : null"
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
