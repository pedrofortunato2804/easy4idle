"""Leitura, migração e gravação do contas.json.

Formato:
{
  "jogo_atual": "pokeidle",
  "jogos": [
    {"id": "pokeidle", "nome": "PokeIdle", "url": "https://pokeidle.io/app", "colunas": 2,
     "contas": [{"id": "conta1", "nome": "Conta 1", "zoom": 0.75, "mudo": true}]}
  ]
}

O "id" de cada conta é único entre todos os jogos e, normalmente, é também o
nome da pasta do perfil (login) em ./perfis. Campos opcionais:
  "url"    endereço próprio do quadro (sobrepõe o do jogo)
  "perfil" id de outra conta cujo login este quadro usa — vários quadros num login só

Sites de streaming (Twitch/Kick) não são mais suportados: pesavam demais em
CPU e memória. Jogos e quadros com esses endereços são descartados ao carregar.
"""
import json
import logging
import re
import shutil
import unicodedata
from urllib.parse import urlparse

from .caminhos import CONFIG_FILE

log = logging.getLogger("easy4idle.config")

POKEIDLE_URL = "https://pokeidle.io/app"
STREAMS = ("twitch.tv", "kick.com")  # não suportados (ver docstring)


# --------------------------------------------------------------------------- #
# Estruturas
# --------------------------------------------------------------------------- #
def novo_jogo(jogo_id, nome, url):
    return {"id": jogo_id, "nome": nome, "url": url, "colunas": 2, "contas": []}


def nova_conta(conta_id, nome, perfil=None, url=None):
    """`perfil`: id de outra conta cujo login este quadro usa (vários quadros num login)."""
    conta = {"id": conta_id, "nome": nome, "zoom": 0.75, "mudo": True}
    if perfil and perfil != conta_id:
        conta["perfil"] = perfil
    if url:
        conta["url"] = url
    return conta


def config_padrao():
    jogo = novo_jogo("pokeidle", "PokeIdle", POKEIDLE_URL)
    jogo["contas"] = [nova_conta(f"conta{i}", f"Conta {i}") for i in range(1, 5)]
    return {"jogo_atual": "pokeidle", "jogos": [jogo]}


# --------------------------------------------------------------------------- #
# Leitura / gravação
# --------------------------------------------------------------------------- #
def _migrar(cfg):
    """Converte o formato antigo (só pokeidle) no formato com vários jogos.

    As contas mantêm o mesmo "id", então continuam usando as mesmas pastas
    de perfil e os logins não se perdem.
    """
    if "jogos" in cfg:
        return cfg, False
    jogo = novo_jogo("pokeidle", "PokeIdle", POKEIDLE_URL)
    jogo["colunas"] = cfg.get("colunas", 2)
    jogo["contas"] = cfg.get("contas", [])
    return {"jogo_atual": "pokeidle", "jogos": [jogo]}, True


def _completar(cfg):
    """Preenche campos ausentes, para tolerar um contas.json editado à mão."""
    cfg.setdefault("jogos", [])
    for i, jogo in enumerate(cfg["jogos"]):
        jogo.setdefault("id", f"jogo{i + 1}")
        jogo.setdefault("nome", jogo["id"])
        jogo.setdefault("url", POKEIDLE_URL)
        jogo.setdefault("colunas", 2)
        jogo.setdefault("contas", [])
    cfg.setdefault("jogo_atual", cfg["jogos"][0]["id"] if cfg["jogos"] else None)
    return cfg


def carregar():
    if not CONFIG_FILE.exists():
        return config_padrao()
    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.exception("contas.json ilegível; usando configuração padrão")
        shutil.copy2(CONFIG_FILE, CONFIG_FILE.with_name("contas.corrompido.json"))
        return config_padrao()
    cfg, migrado = _migrar(cfg)
    if migrado:
        backup = CONFIG_FILE.with_name("contas.antigo.json")
        shutil.copy2(CONFIG_FILE, backup)
        log.info("contas.json migrado para o formato com vários jogos (backup em %s)", backup.name)
    cfg = _completar(cfg)
    if _tirar_streams(cfg):
        backup = CONFIG_FILE.with_name("contas.com-streams.json")
        shutil.copy2(CONFIG_FILE, backup)
        log.info("Quadros de Twitch/Kick descartados do contas.json (backup em %s)", backup.name)
    return cfg


def _tirar_streams(cfg):
    """Remove jogos e quadros de Twitch/Kick. True se removeu algum."""
    removeu = False
    jogos = []
    for jogo in cfg["jogos"]:
        if eh_stream(jogo["url"]):
            removeu = True
            continue
        contas = [c for c in jogo["contas"] if not eh_stream(c.get("url") or "")]
        removeu = removeu or len(contas) != len(jogo["contas"])
        jogo["contas"] = contas
        jogos.append(jogo)
    cfg["jogos"] = jogos
    if cfg.get("jogo_atual") not in {j["id"] for j in jogos}:
        cfg["jogo_atual"] = jogos[0]["id"] if jogos else None
    return removeu


def salvar(cfg):
    """Grava num arquivo temporário e troca, para não corromper se o PC desligar."""
    tmp = CONFIG_FILE.with_name(CONFIG_FILE.name + ".tmp")
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CONFIG_FILE)


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def slug(texto):
    """'Meu Jogo Ação' -> 'meujogoacao' (seguro para nome de pasta)."""
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", t.lower())


def id_unico(base, existentes):
    novo, k = base, 1
    while novo in existentes:
        k += 1
        novo = f"{base}_{k}"
    return novo


def normalizar_url(texto):
    """Aceita 'exemplo.com/jogo' e devolve 'https://exemplo.com/jogo'."""
    t = texto.strip()
    if not t:
        raise ValueError("Informe a URL do jogo.")
    if not re.match(r"^[a-z][a-z0-9+.-]*://", t, re.I):
        t = "https://" + t
    p = urlparse(t)
    if p.scheme not in ("http", "https") or not p.hostname or "." not in p.hostname:
        raise ValueError(f"“{texto.strip()}” não parece um endereço de site válido.")
    if eh_stream(t):
        raise ValueError("Twitch e Kick não são suportados no easy4idle "
                         "(as lives pesavam demais em CPU e memória).")
    return t


def nome_pelo_host(url):
    host = urlparse(url).hostname or url
    return host[4:] if host.startswith("www.") else host


def eh_stream(url):
    host = urlparse(url).hostname or ""
    return any(host == d or host.endswith("." + d) for d in STREAMS)


def eh_pokeidle(url):
    host = urlparse(url).hostname or ""
    return host == "pokeidle.io" or host.endswith(".pokeidle.io")
