"""
easy4idle - várias contas de jogos de navegador em uma única janela.

Cada jogo é uma aba no menu lateral; cada conta usa um perfil de navegador
isolado (cookies/localStorage próprios), salvo em ./perfis/<id>, então o login
permanece entre execuções. O código fica no pacote ./app.
"""
import logging
import os
import sys

# Impede o Chromium de "congelar" as contas quando a janela está minimizada,
# escondida ou atrás de outras janelas (essencial para jogo idle).
# Precisa ser definido antes de importar o Qt WebEngine.
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--disable-background-timer-throttling "
    "--disable-renderer-backgrounding "
    "--disable-backgrounding-occluded-windows "
    "--disable-features=CalculateNativeWinOcclusion,IntensiveWakeUpThrottling",
)

from app import registro  # noqa: E402

log = logging.getLogger("easy4idle")


def main():
    registro.configurar()
    log.info("Iniciando easy4idle (Python %s)", sys.version.split()[0])

    from PyQt6.QtWidgets import QApplication, QMessageBox

    from app.caminhos import PROFILES_DIR
    from app.janela import STYLE, MainWindow

    PROFILES_DIR.mkdir(exist_ok=True)
    app = QApplication(sys.argv)
    app.setApplicationName("easy4idle")
    app.setStyleSheet(STYLE)
    try:
        win = MainWindow()
    except Exception as e:
        log.exception("Falha ao abrir a janela principal")
        QMessageBox.critical(None, "easy4idle",
                             f"Não foi possível iniciar:\n{e}\n\nDetalhes em {registro.LOG_FILE}")
        return 1
    win.showMaximized()
    code = app.exec()
    log.info("easy4idle encerrado (código %s)", code)
    return code


if __name__ == "__main__":
    sys.exit(main())
