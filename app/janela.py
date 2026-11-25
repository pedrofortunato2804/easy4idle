"""Janela principal: menu lateral com os jogos + a grade do jogo selecionado."""
import logging

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QButtonGroup, QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QStackedWidget, QToolButton,
    QVBoxLayout, QWidget,
)

from . import config
from .extensoes import ensure_hunt_extension, hunt_instalada
from .jogo import GameView

log = logging.getLogger("easy4idle.janela")

TAB_W = 84  # largura dos botões do menu lateral


def icone_letra(nome):
    """Ícone provisório (inicial do nome) até o site mandar o favicon."""
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor.fromHsv(sum(map(ord, nome)) * 37 % 360, 140, 190))
    p.drawRoundedRect(0, 0, 64, 64, 14, 14)
    fonte = p.font()
    fonte.setPixelSize(34)
    fonte.setBold(True)
    p.setFont(fonte)
    p.setPen(QColor("white"))
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, (nome.strip()[:1] or "?").upper())
    p.end()
    return QIcon(pm)


class DialogoJogo(QDialog):
    """Pede a URL e o nome de um jogo novo."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Adicionar jogo")
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://exemplo.com/jogo")
        self.nome_edit = QLineEdit()
        self.nome_edit.setPlaceholderText("opcional — usa o endereço do site")
        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.accepted.connect(self.validar)
        botoes.rejected.connect(self.reject)

        form = QFormLayout(self)
        form.addRow("URL do jogo:", self.url_edit)
        form.addRow("Nome:", self.nome_edit)
        form.addRow(QLabel("O jogo já abre com uma conta; adicione mais pela barra de cima."))
        form.addRow(botoes)
        self.resize(460, self.sizeHint().height())
        self.url = self.nome = None

    def validar(self):
        try:
            self.url = config.normalizar_url(self.url_edit.text())
        except ValueError as e:
            QMessageBox.warning(self, "URL inválida", str(e))
            self.url_edit.setFocus()
            return
        self.nome = self.nome_edit.text().strip() or config.nome_pelo_host(self.url)
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = config.carregar()
        self.tabs = []  # pares (botão da lateral, GameView)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)

        # --- menu lateral ---
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(TAB_W + 12)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(6, 6, 6, 6)
        side.setSpacing(6)
        self.tabs_box = QVBoxLayout()
        self.tabs_box.setSpacing(6)
        side.addLayout(self.tabs_box)
        self.btn_novo = QToolButton()
        self.btn_novo.setObjectName("addgame")
        self.btn_novo.setText("＋")
        self.btn_novo.setToolTip("Adicionar jogo")
        self.btn_novo.setFixedSize(TAB_W, 40)
        self.btn_novo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_novo.clicked.connect(self.new_game)
        side.addWidget(self.btn_novo)
        side.addStretch(1)

        # --- área dos jogos ---
        self.stack = QStackedWidget()
        self.vazio = QLabel("Nenhum jogo ainda.\nClique em ＋ na barra lateral para adicionar um.")
        self.vazio.setObjectName("hint")
        self.vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stack.addWidget(self.vazio)

        central = QWidget()
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self.sidebar)
        h.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        if any(config.eh_pokeidle(j["url"]) for j in self.cfg["jogos"]):
            ensure_hunt_extension(self)
        for jogo in self.cfg["jogos"]:
            self.add_game_view(jogo)
        atual = next((v for _, v in self.tabs if v.jogo["id"] == self.cfg.get("jogo_atual")),
                     self.tabs[0][1] if self.tabs else None)
        self.select(atual)

        # --- atalhos ---
        QShortcut(QKeySequence("Esc"), self, activated=lambda: self._na_atual("unfocus"))
        for i in range(1, 10):
            QShortcut(QKeySequence(f"Ctrl+{i}"), self,
                      activated=lambda i=i: self._na_atual("focus_index", i - 1))
        for seq, passo in (("Ctrl+Tab", 1), ("Ctrl+PgDown", 1),
                           ("Ctrl+Shift+Tab", -1), ("Ctrl+PgUp", -1)):
            QShortcut(QKeySequence(seq), self, activated=lambda p=passo: self.cycle(p))

    # ---- abas ----
    def add_game_view(self, jogo):
        view = GameView(jogo, self.all_account_ids)
        btn = QToolButton()
        btn.setObjectName("tab")
        btn.setCheckable(True)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        btn.setIconSize(QSize(32, 32))
        btn.setFixedSize(TAB_W, 62)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        btn.tem_favicon = False
        self.update_tab(btn, view)

        btn.clicked.connect(lambda _=False, v=view: self.select(v))
        btn.customContextMenuRequested.connect(
            lambda pos, b=btn, v=view: self.tab_menu(b, v, b.mapToGlobal(pos)))
        view.changed.connect(self.on_view_changed)
        view.icon_changed.connect(lambda icon, b=btn: self.set_tab_icon(b, icon))

        self.group.addButton(btn)
        self.tabs_box.addWidget(btn)
        self.stack.addWidget(view)
        self.tabs.append((btn, view))
        return view

    def update_tab(self, btn, view):
        nome = view.jogo["nome"]
        btn.setText(btn.fontMetrics().elidedText(nome, Qt.TextElideMode.ElideRight, TAB_W - 8))
        btn.setToolTip(f"{nome}\n{view.jogo['url']}\n\nBotão direito: renomear, alterar URL, remover")
        if not btn.tem_favicon:
            btn.setIcon(icone_letra(nome))

    def set_tab_icon(self, btn, icon):
        btn.tem_favicon = True
        btn.setIcon(icon)

    def tab_menu(self, btn, view, pos):
        menu = QMenu(self)
        menu.addAction("Renomear jogo…", lambda: self.rename_game(btn, view))
        menu.addAction("Alterar URL…", lambda: self.change_url(btn, view))
        menu.addSeparator()
        menu.addAction("Remover jogo…", lambda: self.remove_game(btn, view))
        menu.exec(pos)

    def current_view(self):
        w = self.stack.currentWidget()
        return w if isinstance(w, GameView) else None

    def _na_atual(self, metodo, *args):
        view = self.current_view()
        if view is not None:
            getattr(view, metodo)(*args)

    def select(self, view):
        if view is None:
            self.stack.setCurrentWidget(self.vazio)
            self.cfg["jogo_atual"] = None
        else:
            self.stack.setCurrentWidget(view)
            next(b for b, v in self.tabs if v is view).setChecked(True)
            self.cfg["jogo_atual"] = view.jogo["id"]
        self.update_title()
        self.save()

    def cycle(self, passo):
        if not self.tabs:
            return
        views = [v for _, v in self.tabs]
        atual = self.current_view()
        i = views.index(atual) if atual in views else 0
        self.select(views[(i + passo) % len(views)])

    def update_title(self):
        view = self.current_view()
        if view is None:
            self.setWindowTitle("easy4idle")
        else:
            self.setWindowTitle(f"easy4idle — {view.jogo['nome']} ({len(view.panels)} conta(s))")

    def on_view_changed(self):
        self.update_title()
        self.save()

    def all_account_ids(self):
        return {c["id"] for j in self.cfg["jogos"] for c in j["contas"]}

    # ---- gerenciar jogos ----
    def new_game(self):
        dlg = DialogoJogo(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        jogo_id = config.id_unico(config.slug(dlg.nome) or "jogo",
                                  {j["id"] for j in self.cfg["jogos"]})
        jogo = config.novo_jogo(jogo_id, dlg.nome, dlg.url)
        conta_id = config.id_unico(f"{jogo_id}_conta1", self.all_account_ids())
        jogo["contas"].append(config.nova_conta(conta_id, "Conta 1"))
        if config.eh_pokeidle(dlg.url):
            ensure_hunt_extension(self)
        self.cfg["jogos"].append(jogo)
        log.info("Jogo %s adicionado (%s)", jogo_id, dlg.url)
        self.select(self.add_game_view(jogo))

    def rename_game(self, btn, view):
        nome, ok = QInputDialog.getText(self, "Renomear jogo", "Nome:", text=view.jogo["nome"])
        if ok and nome.strip():
            view.jogo["nome"] = nome.strip()
            self.update_tab(btn, view)
            self.update_title()
            self.save()

    def change_url(self, btn, view):
        texto, ok = QInputDialog.getText(self, "Alterar URL", "URL do jogo:", text=view.jogo["url"])
        if not ok:
            return
        try:
            url = config.normalizar_url(texto)
        except ValueError as e:
            QMessageBox.warning(self, "URL inválida", str(e))
            return
        tinha_hunt = hunt_instalada()
        if config.eh_pokeidle(url):
            ensure_hunt_extension(self)
        view.set_url(url)
        self.update_tab(btn, view)
        self.save()
        if config.eh_pokeidle(url) and not tinha_hunt and hunt_instalada():
            QMessageBox.information(self, "Extensão /hunt",
                                    "Feche e abra o easy4idle para ativar a /hunt nessas contas.")

    def remove_game(self, btn, view):
        n = len(view.panels)
        resp = QMessageBox.question(
            self, "Remover jogo",
            f"Remover o jogo “{view.jogo['nome']}” e suas {n} conta(s)?\n\n"
            "Os dados de login continuam na pasta perfis/ — apague as pastas "
            "manualmente se quiser descartá-los.",
        )
        if resp != QMessageBox.StandardButton.Yes:
            return
        era_atual = view is self.current_view()
        i = next(k for k, (_, v) in enumerate(self.tabs) if v is view)
        self.tabs.pop(i)
        self.group.removeButton(btn)
        self.tabs_box.removeWidget(btn)
        btn.deleteLater()
        self.stack.removeWidget(view)
        view.shutdown()
        view.deleteLater()
        self.cfg["jogos"].remove(view.jogo)
        log.info("Jogo %s removido", view.jogo["id"])
        if era_atual:
            self.select(self.tabs[min(i, len(self.tabs) - 1)][1] if self.tabs else None)
        else:
            self.save()

    # ---- fim ----
    def save(self):
        config.salvar(self.cfg)

    def closeEvent(self, event):
        self.save()
        for _, view in self.tabs:
            view.shutdown()
        self.tabs.clear()
        super().closeEvent(event)


STYLE = """
QMainWindow, QWidget { background: #1e1f24; color: #e6e6e6; font-size: 12px; }
QFrame#sidebar { background: #17181c; border-right: 1px solid #2c2e35; }
QToolButton#tab { background: transparent; border: none; border-radius: 6px;
                  padding: 4px 2px; color: #b8bac4; }
QToolButton#tab:hover { background: #2a2c33; }
QToolButton#tab:checked { background: #33353d; color: #ffffff; border-left: 3px solid #ffcb05; }
QToolButton#addgame { background: transparent; border: 1px dashed #4a4d57; border-radius: 6px;
                      font-size: 20px; color: #8a8d99; }
QToolButton#addgame:hover { border-color: #ffcb05; color: #ffcb05; }
QToolBar { background: #26272d; border: none; padding: 3px; spacing: 6px; }
QToolBar QToolButton { padding: 4px 8px; border-radius: 4px; }
QToolBar QToolButton:hover { background: #3a3c45; }
QFrame#panel { border: 1px solid #3a3c45; border-radius: 4px; background: #26272d; }
QPushButton { background: #33353d; border: none; border-radius: 3px; }
QPushButton:hover { background: #454852; }
QPushButton#name { background: transparent; font-weight: bold; padding: 0 6px; text-align: left; }
QPushButton#name:hover { color: #ffcb05; }
QPushButton#captura:checked { background: #2e7d32; border: 1px solid #66bb6a; }
QLabel#status, QLabel#hint { color: #8a8d99; }
QSpinBox, QLineEdit { background: #33353d; border: none; padding: 3px 4px; }
QMenu { background: #26272d; border: 1px solid #3a3c45; }
QMenu::item:selected { background: #3a3c45; }
"""
