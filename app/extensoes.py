"""Extensões do Chrome (descompactadas em ./extensoes) injetadas nas contas.

O suporte nativo do Qt a extensões (QWebEngineExtensionManager) carrega a
extensão mas a deixa desativada, e ativá-la derruba o processo. Como a /hunt
é só content scripts (sem APIs chrome.*), injetamos os scripts direto, com o
mesmo filtro de URL (@match), momento e "world" declarados no manifest.json.
Assim cada extensão só roda nos sites para os quais foi feita.
"""
import io
import json
import logging
import shutil
import struct
import urllib.request
import zipfile

from PyQt6.QtCore import Qt
from PyQt6.QtWebEngineCore import QWebEngineScript
from PyQt6.QtWidgets import QApplication, QMessageBox

from .caminhos import EXT_DIR

log = logging.getLogger("easy4idle.extensoes")

# "/hunt for PokeIdle" (pokeidleguide.io/#hunt): mostra onde caçar, por XP/h e ouro/h.
HUNT_EXT_ID = "mhnplloljgchpfpcpbhmcokmnefodjnh"
HUNT_EXT_DIR = EXT_DIR / "hunt"


def download_extension(ext_id, dest):
    """Baixa uma extensão da Chrome Web Store e a descompacta em `dest`."""
    url = (
        "https://clients2.google.com/service/update2/crx?response=redirect"
        "&prodversion=140.0&acceptformat=crx2,crx3"
        f"&x=id%3D{ext_id}%26uc"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    if data[:4] != b"Cr24":
        raise ValueError("resposta não é um arquivo .crx")
    version = struct.unpack("<I", data[4:8])[0]
    if version == 3:
        header_len = struct.unpack("<I", data[8:12])[0]
        offset = 12 + header_len
    elif version == 2:
        key_len, sig_len = struct.unpack("<II", data[8:16])
        offset = 16 + key_len + sig_len
    else:
        raise ValueError(f"formato .crx v{version} desconhecido")

    tmp = dest.with_name(dest.name + ".novo")
    shutil.rmtree(tmp, ignore_errors=True)
    with zipfile.ZipFile(io.BytesIO(data[offset:])) as z:
        z.extractall(tmp)
    if not (tmp / "manifest.json").exists():
        shutil.rmtree(tmp, ignore_errors=True)
        raise ValueError("extensão sem manifest.json")
    shutil.rmtree(dest, ignore_errors=True)
    tmp.rename(dest)
    manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8-sig"))
    return manifest.get("version", "?")


def extension_dirs():
    if not EXT_DIR.is_dir():
        return []
    return sorted(p for p in EXT_DIR.iterdir() if (p / "manifest.json").is_file())


_RUN_AT = {
    "document_start": QWebEngineScript.InjectionPoint.DocumentCreation,
    "document_end": QWebEngineScript.InjectionPoint.DocumentReady,
    "document_idle": QWebEngineScript.InjectionPoint.Deferred,
}

# Aplica o CSS via CSSOM (adoptedStyleSheets), que a CSP da página não bloqueia.
_CSS_LOADER = """(function (css) {
  var sheet = new CSSStyleSheet();
  sheet.replaceSync(css);
  document.adoptedStyleSheets = document.adoptedStyleSheets.concat([sheet]);
})(%s);"""


def install_extension_scripts(profile):
    """Injeta os content scripts das extensões no perfil. Devolve a lista de erros."""
    errors = []
    for ext in extension_dirs():
        try:
            manifest = json.loads((ext / "manifest.json").read_text(encoding="utf-8-sig"))
            for i, cs in enumerate(manifest.get("content_scripts", [])):
                header = "// ==UserScript==\n" + "".join(
                    f"// @match {m}\n" for m in cs.get("matches", [])
                ) + "// ==/UserScript==\n"
                point = _RUN_AT.get(cs.get("run_at", "document_idle"),
                                    QWebEngineScript.InjectionPoint.Deferred)
                main_world = cs.get("world") == "MAIN"
                sources = [
                    (f, (ext / f).read_text(encoding="utf-8-sig")) for f in cs.get("js", [])
                ]
                for f in cs.get("css", []):
                    css = (ext / f).read_text(encoding="utf-8-sig")
                    sources.append((f, _CSS_LOADER % json.dumps(css)))
                    # CSS é aplicado quando o documento já existe.
                    point = QWebEngineScript.InjectionPoint.DocumentReady
                    main_world = True
                for f, code in sources:
                    script = QWebEngineScript()
                    script.setName(f"{ext.name}/{i}/{f}")
                    script.setSourceCode(header + code)
                    script.setInjectionPoint(point)
                    script.setWorldId(
                        QWebEngineScript.ScriptWorldId.MainWorld if main_world
                        else QWebEngineScript.ScriptWorldId.ApplicationWorld
                    )
                    script.setRunsOnSubFrames(bool(cs.get("all_frames")))
                    profile.scripts().insert(script)
        except (OSError, ValueError) as e:
            log.warning("Falha ao carregar a extensão %s: %s", ext.name, e)
            errors.append(f"{ext.name}: {e}")
    return errors


def hunt_instalada():
    return (HUNT_EXT_DIR / "manifest.json").exists()


def ensure_hunt_extension(parent=None):
    """Baixa a extensão /hunt se ainda não existir (só chamado se há jogo pokeidle)."""
    if hunt_instalada():
        return
    EXT_DIR.mkdir(exist_ok=True)
    try:
        version = download_extension(HUNT_EXT_ID, HUNT_EXT_DIR)
        log.info("Extensão /hunt v%s baixada", version)
    except Exception as e:  # sem internet etc.: segue sem a extensão
        log.warning("Não foi possível baixar a extensão /hunt: %s", e)
        QMessageBox.warning(
            parent, "Extensão /hunt",
            f"Não foi possível baixar a extensão /hunt:\n{e}\n\n"
            "As contas vão abrir sem ela. Tente “🧩 Atualizar /hunt” depois.",
        )


def atualizar_hunt(parent=None):
    """Ação do botão “🧩 Atualizar /hunt”."""
    EXT_DIR.mkdir(exist_ok=True)
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        version = download_extension(HUNT_EXT_ID, HUNT_EXT_DIR)
    except Exception as e:
        QApplication.restoreOverrideCursor()
        log.warning("Falha ao atualizar a /hunt: %s", e)
        QMessageBox.warning(parent, "Extensão /hunt", f"Falha ao atualizar:\n{e}")
        return
    QApplication.restoreOverrideCursor()
    log.info("Extensão /hunt atualizada para v%s", version)
    QMessageBox.information(
        parent, "Extensão /hunt",
        f"Extensão /hunt v{version} baixada.\n\n"
        "Feche e abra o easy4idle para as contas usarem a versão nova.",
    )
