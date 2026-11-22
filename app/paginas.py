"""Perfis de navegador, páginas e janelas pop-up (login etc.)."""
import logging
import re

from PyQt6 import sip
from PyQt6.QtCore import Qt
from PyQt6.QtWebEngineCore import (
    QWebEnginePage, QWebEnginePermission, QWebEngineProfile, QWebEngineSettings,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget

from .caminhos import PROFILES_DIR

log = logging.getLogger("easy4idle.paginas")

_popups = []  # mantém referências das janelas pop-up abertas
_perfis = {}  # perfil_id -> {"perfil": QWebEngineProfile, "usos": int, "erros": [...]}


def user_agent():
    # Usa o UA real do Chromium embutido, só removendo o token "QtWebEngine/x".
    # Um UA com versão diferente da real faz o Cloudflare (captcha) falhar,
    # pois ele compara o UA com os client hints (sec-ch-ua) e o JS.
    ua = QWebEngineProfile.defaultProfile().httpUserAgent()
    return re.sub(r"\s*QtWebEngine/\S+", "", ua)


def make_profile(acc_id):
    """Perfil isolado e persistente (cookies, localStorage) em ./perfis/<acc_id>."""
    path = PROFILES_DIR / acc_id
    profile = QWebEngineProfile(f"easy4idle_{acc_id}", QApplication.instance())
    profile.setPersistentStoragePath(str(path / "storage"))
    profile.setCachePath(str(path / "cache"))
    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
    )
    profile.setHttpUserAgent(user_agent())
    return profile


def obter_perfil(perfil_id):
    """Perfil do Qt compartilhado: vários quadros com o mesmo login usam o mesmo objeto.

    Na primeira vez cria o perfil e instala os scripts (extensões, autoclique).
    Devolve (perfil, erros_das_extensoes). Cada chamada deve ter um liberar_perfil.
    """
    item = _perfis.get(perfil_id)
    if item is None:
        from . import autocaptura
        from .extensoes import install_extension_scripts
        profile = make_profile(perfil_id)
        autocaptura.instalar(profile)
        item = {"perfil": profile, "usos": 0, "erros": install_extension_scripts(profile)}
        _perfis[perfil_id] = item
    item["usos"] += 1
    return item["perfil"], item["erros"]


def liberar_perfil(perfil_id):
    """Chamado depois de apagar a página. Apaga o perfil quando ninguém mais usa."""
    item = _perfis.get(perfil_id)
    if item is None:
        return
    item["usos"] -= 1
    if item["usos"] > 0:
        return
    del _perfis[perfil_id]
    for popup in popups_do_perfil(item["perfil"]):
        sip.delete(popup)
    sip.delete(item["perfil"])


class GamePage(QWebEnginePage):
    """Página que abre pop-ups (login etc.) no mesmo perfil da conta."""

    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        # Libera a área de transferência (botões "Copiar" dos jogos)
        s = self.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanPaste, True)
        self.permissionRequested.connect(self.on_permission)

    def on_permission(self, permission):
        if permission.permissionType() == QWebEnginePermission.PermissionType.ClipboardReadWrite:
            permission.grant()

    def createWindow(self, _type):
        popup = PopupWindow(self.profile())
        _popups.append(popup)
        popup.destroyed.connect(lambda *_: _popups.remove(popup) if popup in _popups else None)
        popup.show()
        return popup.page


class PopupWindow(QWidget):
    def __init__(self, profile):
        super().__init__(None, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.view = QWebEngineView(self)
        self.page = GamePage(profile, self.view)
        self.view.setPage(self.page)
        self.page.windowCloseRequested.connect(self.close)
        self.page.titleChanged.connect(self.setWindowTitle)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.view)
        self.resize(520, 680)


def popups_do_perfil(profile):
    return [p for p in _popups if p.page.profile() is profile]
