"""Caminhos usados pelo programa (todos relativos à pasta do projeto)."""
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE / "contas.json"
PROFILES_DIR = BASE / "perfis"   # um perfil de navegador por conta
EXT_DIR = BASE / "extensoes"     # extensões do Chrome descompactadas
LOG_DIR = BASE / "logs"
