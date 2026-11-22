"""Aba de um jogo: barra de ferramentas própria + grade com as contas dele."""
import logging

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QGridLayout, QInputDialog, QLabel, QMessageBox, QSpinBox, QToolBar, QVBoxLayout, QWidget,
)

from . import autocaptura, config, streaming
from .extensoes import atualizar_hunt
from .painel import AccountPanel

log = logging.getLogger("easy4idle.jogo")

MAX_GRID = 12


class GameView(QWidget):
    changed = pyqtSignal()           # algo mudou e precisa ser salvo
    icon_changed = pyqtSignal(QIcon)  # favicon do site, para a aba lateral

    def __init__(self, jogo, ids_existentes):
        """`ids_existentes` devolve os ids de todas as contas (de todos os jogos)."""
        super().__init__()
        self.jogo = jogo
        self._ids_existentes = ids_existentes
        self.panels = []
        self.focused = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.build_toolbar())

        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(4, 4, 4, 4)
        self.grid.setSpacing(4)
        lay.addWidget(self.grid_host, 1)

        for acc in jogo["contas"]:
            self.add_panel(acc)
        self.relayout()

    # ---- toolbar ----
    def build_toolbar(self):
        tb = QToolBar(self.jogo["nome"])
        tb.setMovable(False)

        self.act_conta = tb.addAction("＋ Adicionar conta", self.new_account)
        tb.addSeparator()
        tb.addWidget(QLabel(" Colunas: "))
        self.cols_spin = QSpinBox()
        self.cols_spin.setRange(1, 6)
        self.cols_spin.setValue(self.jogo.get("colunas", 2))
        self.cols_spin.valueChanged.connect(self.set_columns)
        tb.addWidget(self.cols_spin)
        tb.addSeparator()
        tb.addAction("⟳ Recarregar todas", lambda: [p.reload() for p in self.panels])
        tb.addAction("🔇 Silenciar todas", lambda: self.mute_all(True))
        tb.addAction("▦ Mostrar todas", self.unfocus)
        # Autoclique de captura (só nos jogos em que ele sabe onde clicar)
        self.sep_captura = tb.addSeparator()
        self.act_captura = tb.addAction("🎯 Auto-captura em todas", self.toggle_captura_all)
        self.act_captura.setToolTip("Liga o autoclique de pokébola em todas as contas deste jogo "
                                    "(ou desliga, se todas já estiverem ligadas)")
        # Streams (Twitch): resgate do baú de bônus
        self.sep_resgate = tb.addSeparator()
        self.act_resgate = tb.addAction("🎁 Resgate em todas", self.toggle_resgate_all)
        self.act_resgate.setToolTip("Liga o resgate automático do bônus de pontos em todas as "
                                    "streams da Twitch (ou desliga, se todas já estiverem ligadas)")
        # Exclusivo do pokeidle
        self.sep_hunt = tb.addSeparator()
        self.act_hunt = tb.addAction("🧩 Atualizar /hunt", lambda: atualizar_hunt(self))
        tb.addSeparator()
        hint = QLabel("  Ctrl+1..9: expandir conta  ·  Esc: voltar à grade  ·  Ctrl+Tab: trocar de jogo")
        hint.setObjectName("hint")
        tb.addWidget(hint)
        self.update_game_kind()
        return tb

    def update_game_kind(self):
        pokeidle = config.eh_pokeidle(self.jogo["url"])
        self.sep_hunt.setVisible(pokeidle)
        self.act_hunt.setVisible(pokeidle)
        captura = autocaptura.suportado(self.jogo["url"])
        self.sep_captura.setVisible(captura)
        self.act_captura.setVisible(captura)
        resgate = streaming.tem_resgate(self.jogo["url"])
        self.sep_resgate.setVisible(resgate)
        self.act_resgate.setVisible(resgate)
        if streaming.eh_streaming(self.jogo["url"]):
            self.act_conta.setText("＋ Adicionar conta (novo login)")
            self.act_conta.setToolTip("Abre um quadro com um login NOVO. Para mais uma stream numa "
                                      "conta que já existe, use o ＋ no cabeçalho dela.")
        else:
            self.act_conta.setText("＋ Adicionar conta")
            self.act_conta.setToolTip("")

    # ---- contas ----
    def add_panel(self, acc, posicao=None):
        panel = AccountPanel(acc, self.jogo["url"])
        panel.changed.connect(self.changed)
        panel.focus_requested.connect(self.toggle_focus)
        panel.remove_requested.connect(self.remove_account)
        panel.stream_requested.connect(self.new_stream)
        panel.icon_changed.connect(self._on_icon)
        if posicao is None:
            self.panels.append(panel)
        else:
            self.panels.insert(posicao, panel)
        return panel

    def _on_icon(self, icon):
        if not icon.isNull():
            self.icon_changed.emit(icon)

    def new_account(self):
        nomes = {a["nome"] for a in self.jogo["contas"]}
        n = 1
        while f"Conta {n}" in nomes:
            n += 1
        name, ok = QInputDialog.getText(self, "Nova conta",
                                        f"Nome da conta em {self.jogo['nome']}:", text=f"Conta {n}")
        if not ok:
            return
        name = name.strip() or f"Conta {n}"
        base = f"{self.jogo['id']}_{config.slug(name) or 'conta'}"
        acc = config.nova_conta(config.id_unico(base, self._ids_existentes()), name)
        self.jogo["contas"].append(acc)
        self.add_panel(acc)
        self.focused = None
        self.relayout()
        log.info("Conta %s adicionada ao jogo %s", acc["id"], self.jogo["id"])
        self.changed.emit()

    def new_stream(self, origem):
        """Novo quadro com o MESMO login de `origem` (outra stream na mesma conta)."""
        stream = origem.eh_stream()
        titulo = "Outra stream nesta conta" if stream else "Outro quadro com este login"
        rotulo = (f"Canal ou link da stream para “{origem.data['nome']}”\n"
                  "(ex.: gaules, twitch.tv/gaules, kick.com/xqc):" if stream else
                  "Endereço do novo quadro (vazio = o do jogo):")
        texto, ok = QInputDialog.getText(self, titulo, rotulo)
        if not ok:
            return
        url = None
        try:
            if texto.strip():
                url = (streaming.url_do_canal(texto, origem.url()) if stream
                       else config.normalizar_url(texto))
        except ValueError as e:
            QMessageBox.warning(self, titulo, str(e))
            return
        perfil = origem.perfil()
        base = f"{self.jogo['id']}_{config.slug(origem.data['nome']) or 'conta'}"
        acc = config.nova_conta(config.id_unico(base, self._ids_existentes()), origem.data["nome"],
                                perfil=perfil, url=url)
        acc["zoom"] = origem.data.get("zoom", acc["zoom"])
        # Entra logo depois do último quadro deste login (ficam juntos na grade)
        ultimo = max(i for i, p in enumerate(self.panels) if p.perfil() == perfil)
        self.jogo["contas"].insert(self.jogo["contas"].index(self.panels[ultimo].data) + 1, acc)
        self.add_panel(acc, ultimo + 1)
        self.focused = None
        self.relayout()
        log.info("Quadro %s adicionado ao login %s (%s)", acc["id"], perfil, url or "endereço do jogo")
        self.changed.emit()

    def remove_account(self, panel):
        outros = [p for p in self.panels if p is not panel and p.perfil() == panel.perfil()]
        if outros:
            detalhe = (f"O login continua sendo usado por {len(outros)} outro(s) quadro(s) "
                       "desta conta.")
        else:
            detalhe = (f"Os dados de login continuam em perfis/{panel.perfil()} — "
                       "apague a pasta manualmente se quiser descartá-los.")
        resp = QMessageBox.question(
            self, "Remover quadro",
            f"Remover “{panel.name_btn.text()}” da grade?\n\n{detalhe}",
        )
        if resp != QMessageBox.StandardButton.Yes:
            return
        if self.focused is panel:
            self.focused = None
        self.panels.remove(panel)
        self.jogo["contas"].remove(panel.data)
        self.grid.removeWidget(panel)
        panel.shutdown()
        panel.deleteLater()
        self.relayout()
        log.info("Conta %s removida do jogo %s", panel.data["id"], self.jogo["id"])
        self.changed.emit()

    def set_url(self, url):
        self.jogo["url"] = url
        for p in self.panels:
            p.set_game_url(url)
        self.update_game_kind()

    # ---- layout ----
    def set_columns(self, n):
        self.jogo["colunas"] = n
        self.relayout()
        self.changed.emit()

    def toggle_focus(self, panel):
        self.focused = None if self.focused is panel else panel
        self.relayout()

    def focus_index(self, i):
        if i < len(self.panels):
            self.toggle_focus(self.panels[i])

    def unfocus(self):
        if self.focused is not None:
            self.focused = None
            self.relayout()

    def relayout(self):
        for p in self.panels:
            self.grid.removeWidget(p)
        visible = [self.focused] if self.focused else self.panels
        cols = 1 if self.focused else max(1, self.jogo.get("colunas", 2))
        rows = max(1, -(-len(visible) // cols))
        for i in range(MAX_GRID):
            self.grid.setRowStretch(i, 1 if i < rows else 0)
            self.grid.setColumnStretch(i, 1 if i < cols else 0)
        for p in self.panels:
            p.setVisible(p in visible)
            p.set_focused(p is self.focused)
        for i, p in enumerate(visible):
            self.grid.addWidget(p, i // cols, i % cols)

    def toggle_captura_all(self):
        ligar = not all(p.data.get("autocaptura", False) for p in self.panels)
        for p in self.panels:
            p.set_captura(ligar)
        self.changed.emit()

    def toggle_resgate_all(self):
        streams = [p for p in self.panels if streaming.tem_resgate(p.url())]
        ligar = not all(p.data.get("resgate", True) for p in streams)
        for p in streams:
            p.set_resgate(ligar)
        self.changed.emit()

    def mute_all(self, muted):
        for p in self.panels:
            p.set_muted(muted)
        self.changed.emit()

    def shutdown(self):
        for p in self.panels:
            p.shutdown()
        self.panels.clear()
