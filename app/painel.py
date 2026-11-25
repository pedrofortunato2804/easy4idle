"""Painel de uma conta: cabeçalho com controles + a página do jogo.

Cada painel tem um "perfil" (pasta em ./perfis com o login). Normalmente é
o próprio id da conta, mas vários painéis podem apontar para o mesmo perfil
("Abrir outro quadro com este login").
"""
import logging
import time

from PyQt6 import sip
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QInputDialog, QLabel, QMenu, QMessageBox, QPushButton, QVBoxLayout,
)

from . import autocaptura, config
from .motores import MotorQt

log = logging.getLogger("easy4idle.painel")

# Vigia das páginas de jogo (ver AccountPanel._vigiar)
VIGIA_INTERVALO_MS = 20000  # de quanto em quanto tempo confere
VIGIA_FALHAS = 5            # conferidas seguidas sem resposta (~100 s) = travada
VIGIA_MEMORIA_MB = 3000     # acima disso a página é reiniciada antes de congelar


def small_button(text, tip):
    b = QPushButton(text)
    b.setToolTip(tip)
    b.setFixedSize(28, 22)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


class AccountPanel(QFrame):
    changed = pyqtSignal()
    focus_requested = pyqtSignal(object)
    remove_requested = pyqtSignal(object)
    clone_requested = pyqtSignal(object)  # "abrir outro quadro com este login"
    icon_changed = pyqtSignal(QIcon)

    def __init__(self, data, game_url):
        super().__init__()
        self.data = data
        self.game_url = game_url
        self.setObjectName("panel")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.motor = None

        # --- cabeçalho ---
        self.name_btn = QPushButton()
        self.name_btn.setObjectName("name")
        self.name_btn.setFlat(True)
        self.name_btn.setToolTip("Clique para renomear, trocar o endereço ou abrir outro quadro "
                                 "com este login")
        self.name_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.name_btn.clicked.connect(self.show_menu)

        self.status = QLabel("")
        self.status.setObjectName("status")

        self.btn_captura = small_button("🎯", "")
        self.btn_captura.setObjectName("captura")
        self.btn_captura.setCheckable(True)
        self.btn_reload = small_button("⟳", "Recarregar")
        self.btn_zoom_out = small_button("−", "Diminuir zoom")
        self.btn_zoom_in = small_button("+", "Aumentar zoom")
        self.zoom_label = QLabel()
        self.zoom_label.setFixedWidth(38)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_mute = small_button("", "Som liga/desliga")
        self.btn_focus = small_button("⛶", "Expandir / voltar à grade")
        self.btn_remove = small_button("✕", "Remover este quadro")

        self.btn_captura.clicked.connect(self.toggle_captura)
        self.btn_reload.clicked.connect(self.reload)
        self.btn_zoom_out.clicked.connect(lambda: self.change_zoom(-0.05))
        self.btn_zoom_in.clicked.connect(lambda: self.change_zoom(+0.05))
        self.btn_mute.clicked.connect(self.toggle_mute)
        self.btn_focus.clicked.connect(lambda: self.focus_requested.emit(self))
        self.btn_remove.clicked.connect(lambda: self.remove_requested.emit(self))

        header = QHBoxLayout()
        header.setContentsMargins(4, 2, 4, 2)
        header.setSpacing(3)
        header.addWidget(self.name_btn)
        header.addWidget(self.status, 1)
        for w in (self.btn_captura, self.btn_reload, self.btn_zoom_out, self.zoom_label, self.btn_zoom_in,
                  self.btn_mute, self.btn_focus, self.btn_remove):
            header.addWidget(w)

        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(1, 1, 1, 1)
        self.lay.setSpacing(0)
        self.lay.addLayout(header)

        # --- autoclique de captura (jogos) ---
        self.lancadas = 0
        self._captura_fase = None
        self._captura_turno = None
        self._captura_ultimo_log = 0.0
        # Consulta o script de tempos em tempos (turno lançando ou em pausa) para o 🎯
        self.timer_captura = QTimer(self)
        self.timer_captura.setInterval(3000)
        self.timer_captura.timeout.connect(self.apply_captura)

        # --- vigia: reinicia a página de jogo que travou ou pesou demais ---
        self.timer_vigia = QTimer(self)
        self.timer_vigia.setInterval(VIGIA_INTERVALO_MS)
        self.timer_vigia.timeout.connect(self._vigiar)
        self.timer_vigia.start()

        self._criar_motor()
        self.set_url_atual(self.url())

    # ---- motor (Qt WebEngine) ----
    def _criar_motor(self):
        self._pagina_pronta = False
        self._vigia_zerar()
        self.motor = MotorQt(self.perfil(), self)
        self.lay.addWidget(self.motor.widget, 1)
        self.motor.progresso.connect(lambda p: self.status.setText(f"carregando {p}%"))
        self.motor.carregou.connect(self.on_load_finished)
        self.motor.travou.connect(self.on_crash)
        self.motor.icone.connect(self._on_icon)
        if self.motor.erros:
            self.status.setToolTip("Avisos:\n" + "\n".join(self.motor.erros))
        self.apply_zoom()
        self.apply_mute()
        self.update_kind()

    def _on_icon(self, icon):
        if not icon.isNull():
            self.icon_changed.emit(icon)

    # ---- endereço ----
    def perfil(self):
        """Pasta do login em ./perfis (compartilhada pelos quadros do mesmo login)."""
        return self.data.get("perfil") or self.data["id"]

    def url(self):
        """URL própria da conta (se tiver) ou a do jogo."""
        return self.data.get("url") or self.game_url

    def set_url_atual(self, url):
        self.motor.set_url(url)
        self.update_kind()

    def set_game_url(self, url):
        self.game_url = url
        if not self.data.get("url"):
            self.set_url_atual(url)
        else:
            self.update_kind()

    def update_kind(self):
        """Mostra os botões que fazem sentido para o site."""
        self.update_name()
        self.update_captura_visibility()

    def update_name(self):
        self.name_btn.setText(self.data["nome"])

    # ---- ações ----
    def reload(self):
        self.motor.reload()

    def on_load_finished(self, ok):
        self._pagina_pronta = self._pagina_pronta or ok
        self.status.setText("" if ok else "falha ao carregar")
        self.apply_zoom()
        self.apply_captura()  # a página recarregada volta com o autoclique desligado

    def on_crash(self, detalhe):
        log.warning("Conta %s travou (%s); recarregando", self.data["id"], detalhe)
        self.status.setText("travou — recarregando…")
        self._vigia_zerar()
        self.motor.reload()

    # ---- vigia da página (jogos) ----
    def _vigia_zerar(self):
        self._vigia_esperando = False
        self._vigia_sem_resposta = 0

    def _vigiar(self):
        """A cada 20 s: a página responde? Está usando memória demais?

        Jogos abertos por muitas horas vão acumulando memória até o navegador
        engasgar e a página congelar (o jogo para e o autoclique junto). Nesses
        casos o processo da página é encerrado e ela é recarregada.
        """
        motor = self.motor
        if not self._pagina_pronta:
            return
        mb = motor.memoria_mb()
        if mb and mb > VIGIA_MEMORIA_MB:
            self._reiniciar_pagina(f"usando {mb} MB de memória", "memória alta")
            return
        if self._vigia_esperando:
            self._vigia_sem_resposta += 1
            if self._vigia_sem_resposta >= VIGIA_FALHAS:
                seg = self._vigia_sem_resposta * VIGIA_INTERVALO_MS // 1000
                self._reiniciar_pagina(f"sem responder há ~{seg} s (memória: {mb} MB)",
                                       "página travada")
            return  # não empilha mais pedidos numa página que não responde

        def resposta(_):
            if sip.isdeleted(self) or self.motor is not motor:
                return
            self._vigia_zerar()
        self._vigia_esperando = True
        motor.run_js("1", resposta)

    def _reiniciar_pagina(self, motivo, curto):
        log.warning("Conta %s: página %s; reiniciando a página", self.data["id"], motivo)
        self.status.setText(f"{curto} — recarregando…")
        self._vigia_zerar()
        self._pagina_pronta = False  # o vigia descansa até a página carregar de novo
        if not self.motor.matar_pagina():  # se der certo, on_crash recarrega
            self.motor.reload()

    def show_menu(self):
        menu = QMenu(self)
        menu.addAction("Renomear…", self.rename)
        menu.addAction("Trocar endereço…", self.change_address)
        if self.data.get("url") and self.data["url"] != self.game_url:
            menu.addAction("Voltar ao endereço do jogo", self.reset_address)
        if self.btn_captura.isVisible():
            menu.addSeparator()
            act = menu.addAction("Usar Ultra Ball nos shiny", self.toggle_ultra_shiny)
            act.setCheckable(True)
            act.setChecked(self.data.get("ultra_shiny", False))
            act.setToolTip("Com a auto-captura ligada, troca para a Ultra Ball quando aparece "
                           "um shiny e volta para a bola de antes depois")
        menu.addSeparator()
        menu.addAction("Abrir outro quadro com este login", lambda: self.clone_requested.emit(self))
        menu.exec(self.name_btn.mapToGlobal(self.name_btn.rect().bottomLeft()))

    def rename(self):
        name, ok = QInputDialog.getText(self, "Renomear", "Nome:", text=self.data["nome"])
        if ok and name.strip():
            self.data["nome"] = name.strip()
            self.update_name()
            self.changed.emit()

    def change_address(self):
        titulo = "Trocar endereço"
        texto, ok = QInputDialog.getText(self, titulo, "Endereço deste quadro:", text=self.url())
        if not ok:
            return
        try:
            url = config.normalizar_url(texto)
        except ValueError as e:
            QMessageBox.warning(self, titulo, str(e))
            return
        self.data["url"] = url
        self.set_url_atual(url)
        self.changed.emit()

    def reset_address(self):
        self.data.pop("url", None)
        self.set_url_atual(self.game_url)
        self.changed.emit()

    def change_zoom(self, delta):
        self.data["zoom"] = round(min(2.0, max(0.25, self.data.get("zoom", 1.0) + delta)), 2)
        self.apply_zoom()
        self.changed.emit()

    def apply_zoom(self):
        z = self.data.get("zoom", 1.0)
        self.motor.set_zoom(z)
        self.zoom_label.setText(f"{int(round(z * 100))}%")

    def toggle_mute(self):
        self.data["mudo"] = not self.data.get("mudo", True)
        self.apply_mute()
        self.changed.emit()

    def set_muted(self, muted):
        self.data["mudo"] = muted
        self.apply_mute()

    def apply_mute(self):
        muted = self.data.get("mudo", True)
        self.motor.set_mudo(muted)
        self.btn_mute.setText("🔇" if muted else "🔊")

    # ---- autoclique de captura (jogos) ----
    def update_captura_visibility(self):
        ok = autocaptura.suportado(self.url())
        self.btn_captura.setVisible(ok)
        self.apply_captura()

    def toggle_captura(self):
        self.set_captura(not self.data.get("autocaptura", False))
        self.changed.emit()

    def set_captura(self, ligado):
        self.data["autocaptura"] = ligado
        if ligado:
            # O ciclo (1 h lançando / 1 h parado) começa agora, lançando
            self.data["autocaptura_inicio"] = int(time.time())
        else:
            self.data.pop("autocaptura_inicio", None)
        self.apply_captura()

    def apply_captura(self):
        ligado = self.data.get("autocaptura", False) and autocaptura.suportado(self.url())
        self.btn_captura.setChecked(ligado)
        if ligado:
            inicio = self.data.setdefault("autocaptura_inicio", int(time.time()))
            self._captura_fase = autocaptura.fase(inicio)
            if not self.timer_captura.isActive():
                self.timer_captura.start()
        else:
            self._captura_fase = None
            self.timer_captura.stop()
        lancando = bool(self._captura_fase and self._captura_fase[0])
        autocaptura.aplicar(self.motor.page, lancando, self.data.get("ultra_shiny", False),
                            self._on_estado_captura)

    def toggle_ultra_shiny(self):
        self.data["ultra_shiny"] = not self.data.get("ultra_shiny", False)
        log.info("Conta %s: Ultra Ball nos shiny %s", self.data["id"],
                 "ligada" if self.data["ultra_shiny"] else "desligada")
        self.apply_captura()
        self.changed.emit()

    def _on_estado_captura(self, estado):
        """Mostra no cabeçalho/tooltip o turno atual e registra no log o que o script vê."""
        if sip.isdeleted(self):
            return
        f = self._captura_fase
        if isinstance(estado, dict):
            self.lancadas = int(estado.get("lancadas") or 0)
        self._log_captura(f, estado)
        if f is None:
            curto, linha = "", "desligado"
        elif f[0]:
            curto, linha = "", f"LANÇANDO — pausa em {autocaptura.minutos(f[1])}"
        else:
            curto = f"🎯 pausa · volta em {autocaptura.minutos(f[1])}"
            linha = f"EM PAUSA — volta a lançar em {autocaptura.minutos(f[1])}"
        corpos = ""
        if isinstance(estado, dict) and f is not None:
            corpos = (f"Corpos no painel “Captura” agora: {int(estado.get('corpos') or 0)} "
                      f"({int(estado.get('habilitados') or 0)} com botão “Lançar” ativo)\n")
            if estado.get("bola"):
                corpos += f"Bola na mão: {estado['bola']}\n"
        shiny = "Ultra Ball nos shiny: desligada (ligue no menu do nome da conta)\n"
        if self.data.get("ultra_shiny", False):
            shiny = "Ultra Ball nos shiny: ligada"
            if isinstance(estado, dict):
                shiny += (f" · shiny no painel agora: {int(estado.get('shinies') or 0)}"
                          f" · Ultras lançadas em shiny: {int(estado.get('shiny_lancadas') or 0)}")
                if estado.get("sem_ultra"):
                    shiny += "\n  ⚠ sem Ultra Ball que valha aqui — lançando a bola de sempre"
            shiny += "\n"
        self.btn_captura.setToolTip(
            f"Autoclique de captura: {linha}\n"
            "Lança pokébola sozinho em cada pokémon abatido (painel “Captura”).\n"
            "Trabalha em turnos: 1 hora lançando, 1 hora parado, e assim por diante.\n"
            f"{corpos}{shiny}"
            f"Bolas lançadas desde que a página abriu: {self.lancadas}"
        )
        # Mostra a pausa sem apagar o "carregando NN%"
        if curto or self.status.text().startswith("🎯"):
            self.status.setText(curto)

    def _log_captura(self, f, estado):
        """Log da troca de turno e, a cada 5 min lançando, do que o script está vendo."""
        turno = None if f is None else ("lançando" if f[0] else "pausa")
        agora = time.monotonic()
        mudou = turno != self._captura_turno
        self._captura_turno = turno
        if turno is None:
            if mudou:
                log.info("Conta %s: autoclique desligado", self.data["id"])
            return
        if mudou:
            log.info("Conta %s: autoclique entrou em %s (troca em %s)",
                     self.data["id"], turno.upper(), autocaptura.minutos(f[1]))
        if turno == "lançando" and (mudou or agora - self._captura_ultimo_log >= 300):
            if not isinstance(estado, dict) and not self._pagina_pronta:
                return  # página ainda carregando: registra no próximo ciclo
            self._captura_ultimo_log = agora
            if isinstance(estado, dict):
                log.info("Conta %s: lançando · corpos=%s habilitados=%s lançadas=%s "
                         "script_ligado=%s visibilidade_real=%s bola=%s shiny=%s "
                         "ultras_em_shiny=%s trocas_de_bola=%s",
                         self.data["id"], estado.get("corpos"), estado.get("habilitados"),
                         estado.get("lancadas"), estado.get("ligado"), estado.get("visibilidade"),
                         estado.get("bola"), estado.get("shinies"), estado.get("shiny_lancadas"),
                         estado.get("trocas"))
            else:
                log.warning("Conta %s: script do autoclique não respondeu na página (%s)",
                            self.data["id"], self.motor.url())

    def set_focused(self, focused):
        self.btn_focus.setText("▣" if focused else "⛶")

    def shutdown(self):
        self.timer_captura.stop()
        self.timer_vigia.stop()
        self.motor.shutdown()
