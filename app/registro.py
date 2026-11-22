"""Log em arquivo (logs/easy4idle.log) e captura de erros não tratados.

O programa roda com pythonw.exe (sem console), então sem isto um erro
fecharia a janela sem deixar rastro.
"""
import logging
import sys
import threading
from logging.handlers import RotatingFileHandler

from .caminhos import LOG_DIR

log = logging.getLogger("easy4idle")
LOG_FILE = LOG_DIR / "easy4idle.log"


def configurar():
    LOG_DIR.mkdir(exist_ok=True)
    handlers = [RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8")]
    if sys.stderr is not None:  # com python.exe também mostra no console
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )
    sys.excepthook = _erro_nao_tratado
    threading.excepthook = lambda a: _erro_nao_tratado(a.exc_type, a.exc_value, a.exc_traceback)
    _capturar_mensagens_qt()


def _erro_nao_tratado(tipo, valor, tb):
    """Registra o erro e avisa o usuário, sem derrubar o programa.

    (Com o excepthook padrão, o PyQt6 aborta o processo em erros dentro de slots.)
    """
    log.critical("Erro não tratado", exc_info=(tipo, valor, tb))
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        if QApplication.instance() is not None:
            QMessageBox.critical(
                None, "easy4idle — erro",
                f"Ocorreu um erro inesperado:\n{valor}\n\nDetalhes em {LOG_FILE}",
            )
    except Exception:  # nunca deixar o próprio aviso gerar outro erro
        pass


def _capturar_mensagens_qt():
    """Encaminha avisos internos do Qt para o log."""
    from PyQt6.QtCore import QtMsgType, qInstallMessageHandler

    niveis = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }
    qt_log = logging.getLogger("qt")

    def handler(tipo, ctx, msg):
        # Mensagens de console (JS) dos sites são muito numerosas: só em DEBUG.
        if ctx.category == "js":
            qt_log.debug(msg)
        else:
            qt_log.log(niveis.get(tipo, logging.INFO), msg)

    qInstallMessageHandler(handler)
