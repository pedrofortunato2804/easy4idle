"""Motor do Microsoft Edge (WebView2) embutido num quadro do Qt.

Por que existe: o Qt WebEngine instalado pelo pip vem sem os codecs H.264/AAC,
que Twitch e Kick usam — as streams não tocam nele. O WebView2 é o Edge do
próprio Windows (já instalado no Windows 10/11) e toca tudo.

Como funciona: via pythonnet carregamos o controle WinForms do WebView2 (as
DLLs vêm no pacote pywebview) e "penduramos" a janela dele (SetParent) dentro
de um QWidget nativo. Os eventos do Edge chegam pela fila de mensagens do
Windows, que o próprio laço do Qt processa, então tudo roda na thread da tela.

Cada login usa uma pasta de dados própria (perfis/<perfil>/edge): vários
quadros com a mesma pasta compartilham o mesmo login.
"""
import ctypes
import json
import logging
import os

from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

log = logging.getLogger("easy4idle.edge")

# Mesmos argumentos em todos os quadros (o WebView2 exige que quadros que
# compartilham uma pasta de dados usem os mesmos argumentos).
ARGUMENTOS = "--autoplay-policy=no-user-gesture-required"

_net = None        # módulos .NET carregados (ver _carregar)
_erro_carga = None


def _carregar():
    """Carrega pythonnet + DLLs do WebView2 uma única vez. Devolve None ou o erro."""
    global _net, _erro_carga
    if _net is not None or _erro_carga is not None:
        return _erro_carga
    try:
        import webview  # só para achar as DLLs do WebView2 que vêm nele
        lib = os.path.join(os.path.dirname(webview.__file__), "lib")
        import clr  # pythonnet
        clr.AddReference("System.Windows.Forms")
        clr.AddReference(os.path.join(lib, "Microsoft.Web.WebView2.Core.dll"))
        clr.AddReference(os.path.join(lib, "Microsoft.Web.WebView2.WinForms.dll"))
        from System import Uri
        from Microsoft.Web.WebView2.Core import CoreWebView2Environment
        from Microsoft.Web.WebView2.WinForms import CoreWebView2CreationProperties, WebView2

        CoreWebView2Environment.SetLoaderDllFolderPath(
            os.path.join(lib, "runtimes", "win-x64", "native"))
        versao = CoreWebView2Environment.GetAvailableBrowserVersionString()
        _net = {"Uri": Uri, "WebView2": WebView2, "Props": CoreWebView2CreationProperties}
        log.info("WebView2 (Edge) %s carregado", versao)
    except ImportError as e:
        _erro_carga = (f"Faltam as dependências do Edge ({e.name}). "
                       "Feche o easy4idle e abra pelo iniciar.bat para instalar.")
    except Exception as e:  # runtime do WebView2 ausente etc.
        _erro_carga = (f"Não foi possível usar o Microsoft Edge (WebView2): {e}\n"
                       "Instale o “WebView2 Runtime” em "
                       "https://developer.microsoft.com/microsoft-edge/webview2/")
    if _erro_carga:
        log.error(_erro_carga)
    return _erro_carga


class EdgeView(QWidget):
    """QWidget com uma página do Edge dentro. API parecida com a do QWebEngineView."""

    progresso = pyqtSignal(int)
    carregou = pyqtSignal(bool)
    url_mudou = pyqtSignal(str)
    travou = pyqtSignal(str)

    def __init__(self, pasta_dados, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors)
        self.wv = None
        self._pronto = False
        self._scripts = []       # scripts a injetar no início de toda página
        self._mudo = True
        self._url_pendente = None
        self._handlers = []      # mantém os delegates .NET vivos
        self._erro = _carregar()
        if self._erro:
            lay = QVBoxLayout(self)
            aviso = QLabel(self._erro)
            aviso.setWordWrap(True)
            aviso.setAlignment(Qt.AlignmentFlag.AlignCenter)
            aviso.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lay.addWidget(aviso)
            return

        net = _net
        self.wv = net["WebView2"]()
        props = net["Props"]()
        props.UserDataFolder = str(pasta_dados)
        props.AdditionalBrowserArguments = ARGUMENTOS
        self.wv.CreationProperties = props
        self._ligar(self.wv, "CoreWebView2InitializationCompleted", self._on_init)
        hwnd = int(self.wv.Handle.ToInt64())
        ctypes.windll.user32.SetParent(hwnd, int(self.winId()))
        self._ajustar()

    # ---- infraestrutura ----
    def _ligar(self, obj, evento, fn):
        """Assina um evento .NET protegendo contra exceções (que derrubariam o processo)."""
        def seguro(sender, args):
            try:
                fn(args)
            except Exception:
                log.exception("Erro tratando o evento %s do Edge", evento)
        self._handlers.append(seguro)
        getattr(obj, evento).__iadd__(seguro)

    def _on_init(self, args):
        if not args.IsSuccess:
            msg = str(args.InitializationException)
            log.error("Falha ao iniciar o Edge: %s", msg)
            self.travou.emit(msg)
            return
        core = self.wv.CoreWebView2
        self._pronto = True
        core.Settings.IsStatusBarEnabled = False
        core.IsMuted = self._mudo
        for js in self._scripts:
            core.AddScriptToExecuteOnDocumentCreatedAsync(js)
        self._ligar(core, "NavigationStarting", lambda a: self.progresso.emit(10))
        self._ligar(core, "ContentLoading", lambda a: self.progresso.emit(60))
        self._ligar(core, "NavigationCompleted", lambda a: self.carregou.emit(bool(a.IsSuccess)))
        self._ligar(core, "SourceChanged", lambda a: self.url_mudou.emit(self.url()))
        self._ligar(core, "ProcessFailed",
                    lambda a: self.travou.emit(str(a.ProcessFailedKind)))
        if self._url_pendente:
            core.Navigate(self._url_pendente)
            self._url_pendente = None

    def _ajustar(self):
        if self.wv is None:
            return
        dpr = self.devicePixelRatioF()
        r = self.rect()
        self.wv.SetBounds(0, 0, max(1, round(r.width() * dpr)), max(1, round(r.height() * dpr)))

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._ajustar()

    def showEvent(self, ev):
        super().showEvent(ev)
        self._ajustar()

    # ---- API ----
    def adicionar_script(self, js):
        """Script que roda no início de toda página (antes dos scripts do site)."""
        self._scripts.append(js)
        if self._pronto:
            self.wv.CoreWebView2.AddScriptToExecuteOnDocumentCreatedAsync(js)

    def set_url(self, url):
        if self.wv is None:
            return
        if self._pronto:
            self.wv.CoreWebView2.Navigate(url)
        elif self.wv.Source is None:
            self._url_pendente = None
            self.wv.Source = _net["Uri"](url)  # também dispara a inicialização
        else:
            self._url_pendente = url

    def url(self):
        if self.wv is None or self.wv.Source is None:
            return ""
        return str(self.wv.Source.AbsoluteUri)

    def reload(self):
        if self._pronto:
            self.wv.CoreWebView2.Reload()

    def set_zoom(self, z):
        if self.wv is not None:
            self.wv.ZoomFactor = float(z)

    def set_mudo(self, mudo):
        self._mudo = mudo
        if self._pronto:
            self.wv.CoreWebView2.IsMuted = mudo

    def _esperar(self, tarefa, callback, timeout_ms=10000):
        """Espera uma Task .NET (sem travar a tela) e entrega o resultado JSON já convertido."""
        if callback is None:
            return
        restante = [timeout_ms]

        def conferir():
            if self.wv is None:
                return  # quadro fechado no meio do caminho
            if tarefa.IsCompleted:
                try:
                    res = json.loads(tarefa.Result) if not tarefa.IsFaulted and tarefa.Result else None
                except Exception:
                    res = None
                callback(res)
            elif restante[0] <= 0:
                callback(None)
            else:
                restante[0] -= 100
                QTimer.singleShot(100, conferir)
        conferir()

    def run_js(self, codigo, callback=None, timeout_ms=10000):
        """Executa JS na página; `callback(resultado_python)` quando terminar."""
        if not self._pronto:
            if callback:
                callback(None)
            return
        self._esperar(self.wv.ExecuteScriptAsync(codigo), callback, timeout_ms)

    def cdp(self, metodo, params=None, callback=None):
        """Chama um método do protocolo de depuração do Chromium (DevTools) na página."""
        if not self._pronto:
            if callback:
                callback(None)
            return
        tarefa = self.wv.CoreWebView2.CallDevToolsProtocolMethodAsync(
            metodo, json.dumps(params or {}))
        self._esperar(tarefa, callback)

    def mouse(self, tipo, x, y, callback=None):
        """Evento de mouse "de verdade" na página (coordenadas CSS da janela da página).

        Não mexe no cursor do Windows: é um mouse virtual só desta página. Serve para
        menus que ignoram cliques simulados por JavaScript.
        """
        params = {"type": tipo, "x": float(x), "y": float(y)}
        if tipo in ("mousePressed", "mouseReleased"):
            params.update(button="left", clickCount=1)
        self.cdp("Input.dispatchMouseEvent", params, callback)

    def clicar(self, x, y, callback=None):
        self.mouse("mouseMoved", x, y)
        self.mouse("mousePressed", x, y)
        self.mouse("mouseReleased", x, y, callback)

    def shutdown(self):
        if self.wv is not None:
            try:
                self.wv.Dispose()
            except Exception:
                log.exception("Erro ao fechar o Edge")
            self.wv = None
            self._pronto = False
