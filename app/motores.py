"""Motores de navegador de um quadro, com a mesma interface para o painel.

- MotorQt: Qt WebEngine (Chromium embutido). Usado nos jogos: tem as extensões
  (/hunt) e o autoclique de captura.
- MotorEdge: Microsoft Edge (WebView2). Usado em Twitch/Kick, que precisam de
  H.264/AAC (ver edge.py).

Os dois recebem o `perfil_id` (pasta em ./perfis): quadros com o mesmo perfil
compartilham o login.
"""
import ctypes
import logging
import os
import signal
from ctypes import wintypes

from PyQt6 import sip
from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWebEngineWidgets import QWebEngineView

from . import streaming
from .caminhos import PROFILES_DIR
from .paginas import GamePage, liberar_perfil, obter_perfil

log = logging.getLogger("easy4idle.motores")


class _MemoriaProcesso(ctypes.Structure):  # PROCESS_MEMORY_COUNTERS_EX
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
        (n, ctypes.c_size_t) for n in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
            "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
            "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")]


def _memoria_privada_mb(pid):
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        h = k32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return None
        try:
            m = _MemoriaProcesso()
            m.cb = ctypes.sizeof(m)
            if not k32.K32GetProcessMemoryInfo(wintypes.HANDLE(h), ctypes.byref(m), m.cb):
                return None
            return m.PrivateUsage // (1024 * 1024)
        finally:
            k32.CloseHandle(wintypes.HANDLE(h))
    except Exception:
        return None


class Motor(QObject):
    progresso = pyqtSignal(int)
    carregou = pyqtSignal(bool)
    icone = pyqtSignal(QIcon)
    url_mudou = pyqtSignal(str)
    travou = pyqtSignal(str)

    widget = None
    erros = ()  # avisos para o tooltip do status (ex.: extensões)

    def set_url(self, url): ...
    def url(self): return ""
    def reload(self): ...
    def set_zoom(self, z): ...
    def set_mudo(self, mudo): ...
    def run_js(self, codigo, callback=None): ...
    def shutdown(self): ...


class MotorQt(Motor):
    def __init__(self, perfil_id, parent_widget):
        super().__init__(parent_widget)
        self.perfil_id = perfil_id
        self.profile, self.erros = obter_perfil(perfil_id)
        self.view = QWebEngineView(parent_widget)
        self.page = GamePage(self.profile, self.view)
        self.view.setPage(self.page)
        self.widget = self.view
        self.view.loadProgress.connect(self.progresso)
        self.view.loadFinished.connect(self.carregou)
        self.view.iconChanged.connect(self.icone)
        self.view.urlChanged.connect(lambda u: self.url_mudou.emit(u.toString()))
        self.page.renderProcessTerminated.connect(
            lambda status, code: self.travou.emit(f"status={status}, código={code}"))

    def set_url(self, url):
        self.view.setUrl(QUrl(url))

    def url(self):
        return self.view.url().toString()

    def reload(self):
        self.view.reload()

    def set_zoom(self, z):
        self.view.setZoomFactor(z)

    def set_mudo(self, mudo):
        self.page.setAudioMuted(mudo)

    def run_js(self, codigo, callback=None):
        if callback:
            self.page.runJavaScript(codigo, callback)
        else:
            self.page.runJavaScript(codigo)

    def memoria_mb(self):
        """Memória própria (MB) do processo que desenha a página, ou None."""
        pid = self.page.renderProcessPid()
        return _memoria_privada_mb(pid) if pid else None

    def matar_pagina(self):
        """Encerra o processo da página travada; o Qt avisa (travou) e o painel recarrega."""
        pid = self.page.renderProcessPid()
        if not pid:
            return False
        try:
            os.kill(pid, signal.SIGTERM)  # no Windows: TerminateProcess
            return True
        except OSError:
            log.exception("Não consegui encerrar o processo %s da página", pid)
            return False

    def shutdown(self):
        """Apaga a página antes do perfil (ordem exigida pelo Qt WebEngine)."""
        sip.delete(self.view)  # apaga a página junto (é filha da view)
        liberar_perfil(self.perfil_id)


class MotorEdge(Motor):
    def __init__(self, perfil_id, parent_widget):
        super().__init__(parent_widget)
        from .edge import EdgeView  # só carrega o .NET quando há stream
        self.perfil_id = perfil_id
        pasta = PROFILES_DIR / perfil_id / "edge"
        pasta.mkdir(parents=True, exist_ok=True)
        self.view = EdgeView(pasta, parent_widget)
        self.view.adicionar_script(streaming.SCRIPT)
        self.widget = self.view
        self.view.progresso.connect(self.progresso)
        self.view.carregou.connect(self.carregou)
        self.view.url_mudou.connect(self.url_mudou)
        self.view.travou.connect(self.travou)
        self.erros = [self.view._erro] if self.view._erro else []

    def set_url(self, url):
        self.view.set_url(url)

    def url(self):
        return self.view.url()

    def reload(self):
        self.view.reload()

    def set_zoom(self, z):
        self.view.set_zoom(z)

    def set_mudo(self, mudo):
        self.view.set_mudo(mudo)

    def run_js(self, codigo, callback=None):
        self.view.run_js(codigo, callback)

    def shutdown(self):
        self.view.shutdown()
        sip.delete(self.view)


def criar_motor(url, perfil_id, parent_widget):
    cls = MotorEdge if streaming.eh_streaming(url) else MotorQt
    return cls(perfil_id, parent_widget)


def motor_certo(motor, url):
    """True se o motor atual serve para a URL (senão o painel troca de motor)."""
    return isinstance(motor, MotorEdge) == streaming.eh_streaming(url)
