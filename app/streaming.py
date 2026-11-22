"""Sites de streaming (Twitch e Kick) para acumular pontos de canal.

- Esses sites abrem no motor do Edge (ver edge.py), que toca H.264/AAC.
- Script injetado no início de toda página:
    * Qualidade mínima do player — com várias streams abertas faz muita
      diferença em CPU e internet. Twitch: pela preferência que o player lê
      ao abrir (160p). Kick: o player não guarda a escolha, então o script
      abre o menu "Qualidade" e clica na menor resolução (e refaz se precisar).
    * Clica em "Começar a assistir" nos avisos de conteúdo adulto da Twitch
      (só aparecem para quem está logado e é maior de idade), para a stream
      não ficar parada atrás do aviso.
    * Resgate automático (opcional, botão 🎁): clica no baú de bônus de pontos
      que a Twitch mostra de tempos em tempos embaixo do chat. A Kick não tem
      baú: os pontos dela sobem sozinhos enquanto você assiste logado.
- O Python consulta o script a cada poucos segundos (liga/desliga o resgate e
  lê quantos bônus já resgatou e se o vídeo está tocando).
"""
import json
import re
from urllib.parse import urlparse

PLATAFORMAS = {
    "twitch.tv": {"nome": "Twitch", "base": "https://www.twitch.tv/", "resgate": True},
    "kick.com": {"nome": "Kick", "base": "https://kick.com/", "resgate": False},
}

# Primeiros pedaços de caminho que não são canais
_RESERVADOS = {
    "directory", "search", "settings", "subscriptions", "wallet", "drops", "inventory",
    "downloads", "jobs", "p", "turbo", "prime", "friends", "messages", "videos", "following",
    "browse", "categories", "category", "dashboard", "login", "signup", "logout", "help",
    "terms", "privacy", "community-guidelines", "moderator", "popout", "embed", "u",
}

INTERVALO_MS = 5000

SCRIPT = r"""(function () {
  if (window.__e4iStream) return;
  var host = location.hostname;
  var twitch = /(^|\.)twitch\.tv$/.test(host);
  var kick = /(^|\.)kick\.com$/.test(host);
  var resgatar = false, resgates = 0;

  // Qualidade mínima na Twitch (o player lê isto ao abrir).
  if (twitch) {
    try { localStorage.setItem('video-quality', JSON.stringify({ default: '160p30' })); } catch (e) {}
  }

  function clicar(sel) {
    var el = document.querySelector(sel);
    if (el) { el.click(); return true; }
    return false;
  }

  // ---- Kick: qualidade mínima pelo menu "Qualidade" do player ----
  // O player da Kick não guarda a escolha e o menu dele ignora cliques feitos
  // por JavaScript. Então este script só diz ONDE clicar (e quando é preciso);
  // quem clica é o Python, com eventos de mouse reais do Edge (ver
  // QualidadeKick). As opções são achadas pelo valor ("160p", "360p"…), que
  // não muda com o idioma. Refaz ao trocar de canal ou se a qualidade subir.
  var kq = { caminho: null, altura: 0, tentativa: 0, diag: '' };
  function resolucao(v) { var m = /^(\d+)p/.exec(v || ''); return m ? +m[1] : null; }
  function centro(el) {
    var r = el.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  }
  function kickPrecisa() {
    var v = document.querySelector('video');
    if (!v || !v.videoHeight || v.paused) return false;
    if (kq.caminho === location.pathname && v.videoHeight <= kq.altura) return false;
    return Date.now() - kq.tentativa >= 30000;
  }
  window.__e4iKick = {
    // Começa uma tentativa: devolve o centro do vídeo (para o mouse passar por cima)
    comecar: function () {
      kq.tentativa = Date.now();
      var v = document.querySelector('video');
      if (!v) return null;
      var c = centro(v);
      // Os controles do player aparecem com estes eventos de "mouse em cima"
      ['pointerover', 'pointerenter', 'pointermove', 'mouseover', 'mouseenter', 'mousemove'].forEach(function (t) {
        v.dispatchEvent(new MouseEvent(t, { bubbles: true, clientX: c.x, clientY: c.y }));
      });
      return c;
    },
    // Centro do botão "Qualidade" visível (de preferência dentro do contêiner do vídeo)
    botao: function () {
      var v = document.querySelector('video'), caixa = v;
      for (var i = 0; caixa && i < 6 && caixa.parentElement; i++) caixa = caixa.parentElement;
      function achar(raiz) {
        return [].slice.call(raiz.querySelectorAll('button[aria-label]')).filter(function (b) {
          return /qualid|quality|calidad/i.test(b.getAttribute('aria-label')) && b.getClientRects().length;
        })[0];
      }
      var b = (caixa && achar(caixa)) || achar(document);
      if (!b) return null;
      var c = centro(b), el = document.elementFromPoint(c.x, c.y);
      // Algo na frente do botão (ex.: aviso de cookies) receberia o clique
      c.livre = !!el && (el === b || b.contains(el));
      c.naFrente = c.livre ? '' : (el ? (el.id || '') + ' ' + String(el.className || '').slice(0, 40) +
                                   ' “' + (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 80) + '”' : '?');
      // Aviso "tenho 18 anos" da Kick cobrindo o player
      var idade = document.querySelector('[data-testid="mature"]');
      if (!c.livre && ((idade && idade.getClientRects().length) ||
                       /confirmar sua idade|confirm your age|confirmar tu edad|18\+/i.test(el && el.textContent || '')))
        c.naFrente = 'aviso-idade';
      return c;
    },
    // Opções de resolução do menu aberto, da menor para a maior. A Kick usa dois
    // formatos: rádios com value="160p" ou itens de menu cujo texto começa com "160p".
    opcoes: function () {
      var itens = [].slice.call(document.querySelectorAll('[role="radio"][value], [role="menuitemradio"]'));
      return itens.map(function (e) {
        var valor = e.getAttribute('value') || (e.textContent || '').trim();
        var altura = resolucao(valor);
        if (!altura || !e.getClientRects().length) return null;
        if (e.getAttribute('aria-disabled') === 'true' || e.hasAttribute('data-disabled')) return null;
        var c = centro(e);
        return { valor: (/^\d+p\d*/.exec(valor) || [valor])[0], altura: altura,
                 marcada: e.getAttribute('aria-checked') === 'true', x: c.x, y: c.y };
      }).filter(Boolean).sort(function (a, b) { return a.altura - b.altura; });
    },
    concluir: function (altura, diag) { kq.caminho = location.pathname; kq.altura = altura; kq.diag = diag; },
    falhou: function (diag) { kq.diag = diag; },
    fecharMenu: function () {
      var alvo = document.activeElement || document.body;
      alvo.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true }));
    }
  };

  function passo() {
    if (!twitch) return;
    // Avisos de conteúdo adulto/classificação na frente do player
    clicar('[data-a-target="content-classification-gate-overlay-start-watching-button"]');
    clicar('[data-a-target="player-overlay-mature-accept"]');
    // Baú de bônus de pontos embaixo do chat
    if (resgatar) {
      var icone = document.querySelector('.community-points-summary .claimable-bonus__icon') ||
                  document.querySelector('.claimable-bonus__icon');
      var botao = icone && icone.closest('button');
      if (botao && !botao.disabled) { botao.click(); resgates++; }
    }
  }
  setInterval(passo, %(intervalo)d);

  window.__e4iStream = function (on) {
    if (on !== undefined) resgatar = !!on;
    var v = document.querySelector('video');
    return { resgates: resgates, resgatar: resgatar,
             tocando: !!(v && !v.paused && v.readyState > 2),
             altura: v ? v.videoHeight : 0, qualidadeMinima: kick ? kq.altura : null, diagQualidade: kick ? kq.diag : null,
             kickPrecisa: kick ? kickPrecisa() : false };
  };
})();""" % {"intervalo": INTERVALO_MS}


def plataforma(url):
    host = (urlparse(url).hostname or "").lower()
    for dominio, info in PLATAFORMAS.items():
        if host == dominio or host.endswith("." + dominio):
            return info
    return None


def eh_streaming(url):
    return plataforma(url) is not None


def tem_resgate(url):
    p = plataforma(url)
    return bool(p and p["resgate"])


def canal_da_url(url):
    """'https://www.twitch.tv/gaules' -> 'gaules' (None se não for página de canal)."""
    if not eh_streaming(url):
        return None
    partes = [p for p in urlparse(url).path.split("/") if p]
    if len(partes) != 1 or partes[0].lower() in _RESERVADOS:
        return None
    return partes[0] if re.fullmatch(r"[A-Za-z0-9_-]{2,40}", partes[0]) else None


def url_do_canal(texto, url_atual):
    """Aceita 'gaules', 'twitch.tv/gaules' ou o link completo. ValueError se inválido."""
    t = texto.strip().lstrip("@")
    if not t:
        raise ValueError("Informe o nome do canal ou o link da stream.")
    if re.fullmatch(r"[A-Za-z0-9_-]{2,40}", t):
        p = plataforma(url_atual) or PLATAFORMAS["twitch.tv"]
        return p["base"] + t
    from .config import normalizar_url
    return normalizar_url(t)


def script_estado(resgatar):
    return f"window.__e4iStream ? window.__e4iStream({'true' if resgatar else 'false'}) : null"


AVISO_COOKIES = "aviso de cookies na frente do player"
AVISO_IDADE = "aviso de +18 na frente do player"


class QualidadeKick:
    """Põe a stream da Kick na menor resolução usando o menu "Qualidade" do player.

    O menu da Kick ignora cliques simulados por JavaScript, então os cliques são
    eventos de mouse reais do Edge (EdgeView.clicar). O script da página só diz
    onde clicar. Passos: mouse sobre o vídeo (o script também simula o "mouse em
    cima", que é o que de fato mostra os controles) → clica em
    "Qualidade" → clica na menor resolução → tira o mouse (controles somem).
    """

    def __init__(self, view):
        self.view = view
        self.rodando = False
        self._esperas = 0

    def _vivo(self):
        from PyQt6 import sip
        return not sip.isdeleted(self.view) and self.view.wv is not None

    def _js(self, codigo, callback=None):
        if not self._vivo():
            self.rodando = False
            return
        self.view.run_js(f"window.__e4iKick ? window.__e4iKick.{codigo} : null", callback)

    def _depois(self, ms, fn):
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(ms, lambda: fn() if self._vivo() else setattr(self, "rodando", False))

    def rodar(self):
        if self.rodando or not self._vivo():
            return
        self.rodando = True
        self._js("comecar()", self._sobre_video)

    def _fim(self, diag=None):
        if self._vivo():
            if diag:
                self._js(f"falhou({json.dumps(diag)})")
            self.view.mouse("mouseMoved", 2, 2)  # tira o mouse de cima: controles somem
        self.rodando = False

    def _sobre_video(self, c):
        if not c:
            return self._fim()  # página trocando de canal: tenta de novo no próximo ciclo
        self.view.mouse("mouseMoved", c["x"], c["y"])
        self._depois(400, lambda: self._js("botao()", self._no_botao))

    def _no_botao(self, b):
        if not b:
            return self._fim("sem botão Qualidade")
        if not b.get("livre", True):
            na_frente = b.get("naFrente", "")
            if "onetrust" in na_frente.lower():
                return self._fim(AVISO_COOKIES)
            if na_frente == "aviso-idade":
                return self._fim(AVISO_IDADE)
            return self._fim(f"algo na frente do player ({na_frente.strip()})")
        self.view.clicar(b["x"], b["y"])
        self._esperas = 0
        self._depois(500, lambda: self._js("opcoes()", self._nas_opcoes))

    def _nas_opcoes(self, opcoes):
        if not opcoes:
            self._esperas += 1
            if self._esperas < 8:  # o menu abre com animação
                return self._depois(250, lambda: self._js("opcoes()", self._nas_opcoes))
            return self._fim("menu sem opções")
        menor = opcoes[0]
        if menor["marcada"]:
            self._js("fecharMenu()")
        else:
            self.view.clicar(menor["x"], menor["y"])
        self._js(f"concluir({int(menor['altura'])}, {json.dumps('ok ' + menor['valor'])})")
        self._depois(500, self._fim)
