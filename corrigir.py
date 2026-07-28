# -*- coding: utf-8 -*-
"""
Correção interativa de acidentes plotados no MEIO DA RUA que na verdade são
CRUZAMENTOS (o texto da matéria menciona "esquina com" / "cruzamento com").

Rode:  python corrigir.py

Para cada caso, mostra o trecho da matéria (com a menção de esquina destacada)
e o local atual. Você responde:

  <nome da rua>   → vira cruzamento e re-geocodifica na esquina exata (OSM)
  ok              → o ponto está correto, não mexe (marca como revisado)
  rua             → é rua mesmo, sem esquina (marca como revisado, não move)
  coord -28.2,-52.4  → fixa essa coordenada exata (quando o OSM não tem a esquina)
  pula            → deixa pra depois (reaparece na próxima vez)
  sair            → salva o progresso e encerra

Os corrigidos/revisados NÃO reaparecem — ficam marcados no banco.
"""
import os
import re
import sys

if os.name == "nt":
    os.system("")  # habilita cores ANSI no Windows 10+

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import duckdb
from pipeline.storage import DB_PATH
from pipeline.geocoder import _overpass_cruzamento

# ── cores ──────────────────────────────────────────────────────────────────
B, DIM, YEL, GRN, RED, CIA, RST = (
    "\033[1m", "\033[2m", "\033[33m", "\033[32m", "\033[31m", "\033[36m", "\033[0m"
)

_PREFIXO = re.compile(r"^(rua|avenida|av|alameda|estrada|travessa|rodovia)\s+", re.IGNORECASE)
_TAIL = re.compile(r"\s+(e|em|no|na|de|da|do|esquina|com)\s*$", re.IGNORECASE)
_KEYS = re.compile(
    r"(esquina(?:\s+com(?:\s+a)?)?|cruzamento(?:\s+d[eo]| com)?|com a rua|com a av(?:enida)?)",
    re.IGNORECASE,
)


def _tira_prefixo(nome: str) -> str:
    nome = _PREFIXO.sub("", nome).strip()
    prev = None
    while prev != nome:  # remove conectores/resíduos grudados no fim ("... E", "... esquina")
        prev = nome
        nome = _TAIL.sub("", nome).strip()
    return nome


def _destaca(texto: str) -> str:
    return _KEYS.sub(lambda m: f"{YEL}{B}{m.group(0)}{RST}", texto or "")


def _garantir_coluna(con):
    try:
        con.execute("ALTER TABLE acidentes ADD COLUMN corrigido_manual BOOLEAN DEFAULT FALSE")
    except Exception:
        pass


def _carregar_pendentes():
    con = duckdb.connect(str(DB_PATH))
    _garantir_coluna(con)
    rows = con.execute("""
        SELECT id, titulo, loc_endereco, latitude, longitude, teaser, url, municipio
        FROM acidentes
        WHERE loc_tipo = 'logradouro' AND latitude IS NOT NULL
          AND (corrigido_manual IS NULL OR corrigido_manual = FALSE)
          AND (lower(titulo)  LIKE '%esquina%' OR lower(titulo)  LIKE '%cruzamento%'
            OR lower(teaser)  LIKE '%esquina%' OR lower(teaser)  LIKE '%cruzamento%'
            OR lower(teaser)  LIKE '% com a rua%' OR lower(teaser) LIKE '% com a av%')
        ORDER BY data_publicacao DESC
    """).fetchall()
    con.close()
    return rows


def _atualizar(id_, campos: dict):
    sets = ", ".join(f"{k} = ?" for k in campos)
    vals = list(campos.values()) + [id_]
    con = duckdb.connect(str(DB_PATH))
    _garantir_coluna(con)
    con.execute(f"UPDATE acidentes SET {sets} WHERE id = ?", vals)
    con.close()


def main():
    try:
        pendentes = _carregar_pendentes()
    except duckdb.IOException:
        print(f"{RED}O banco está em uso (provavelmente o diário rodando). "
              f"Tente de novo em alguns minutos.{RST}")
        return

    total = len(pendentes)
    if total == 0:
        print(f"{GRN}Nada pendente — todos os casos já foram revisados. 🎉{RST}")
        return

    print(f"\n{B}Correção de esquinas — {total} casos pendentes{RST}")
    print(f"{DIM}respostas: <rua que cruza> | ok | rua | coord -28.2,-52.4 | pula | sair{RST}\n")

    stats = {"cruz": 0, "ok": 0, "rua": 0, "coord": 0, "pula": 0}

    for i, (id_, titulo, loc, lat, lon, teaser, url, muni) in enumerate(pendentes, 1):
        rua1 = _tira_prefixo(str(loc).split(",")[0].strip())
        print(f"{CIA}{'─'*70}{RST}")
        print(f"{DIM}[{i}/{total}]  #{id_}{RST}")
        print(f"{B}{titulo}{RST}")
        print(f"  {DIM}texto:{RST} …{_destaca((teaser or '')[:280])}…")
        print(f"  {DIM}ponto atual:{RST} {loc}  {DIM}({lat:.5f},{lon:.5f}){RST}")
        print(f"  {DIM}mapa:{RST} https://www.google.com/maps?q={lat},{lon}")
        print(f"  {DIM}notícia:{RST} {url}")

        resp = input(f"{B}> cruza com qual rua?{RST} ").strip()
        low = resp.lower()

        if low in ("sair", "quit", "q", "exit"):
            print(f"\n{YEL}Progresso salvo. Até a próxima.{RST}")
            break
        if low in ("", "pula", "skip", "p"):
            stats["pula"] += 1
            continue
        if low == "ok":
            _atualizar(id_, {"corrigido_manual": True})
            print(f"  {GRN}✓ marcado como correto{RST}")
            stats["ok"] += 1
            continue
        if low == "rua":
            _atualizar(id_, {"corrigido_manual": True})
            print(f"  {GRN}✓ marcado como rua (sem esquina){RST}")
            stats["rua"] += 1
            continue

        # coordenada manual: "coord -28.26,-52.40" ou "-28.26,-52.40"
        m = re.search(r"(-?\d+[.,]\d+)\s*[, ]\s*(-?\d+[.,]\d+)", resp)
        if low.startswith("coord") or (m and low.replace("coord", "").strip().startswith("-")):
            if not m:
                print(f"  {RED}coordenada não reconhecida — pulei{RST}")
                stats["pula"] += 1
                continue
            nlat = float(m.group(1).replace(",", "."))
            nlon = float(m.group(2).replace(",", "."))
            _atualizar(id_, {"latitude": nlat, "longitude": nlon,
                             "loc_tipo": "cruzamento", "corrigido_manual": True})
            print(f"  {GRN}✓ fixado em ({nlat:.5f},{nlon:.5f}){RST}")
            stats["coord"] += 1
            continue

        # caso geral: resposta é o nome da rua que cruza → geocodifica a esquina
        rua2 = _tira_prefixo(resp).title()
        print(f"  {DIM}procurando esquina {rua1} × {rua2} no OpenStreetMap…{RST}")
        coords = _overpass_cruzamento(rua1, rua2, muni or "Passo Fundo")
        if coords:
            endereco = f"{rua1.title()} e {rua2}, {muni}, RS, Brasil"
            _atualizar(id_, {
                "loc_tipo": "cruzamento", "loc_rua1": rua1.title(), "loc_rua2": rua2,
                "loc_endereco": endereco, "latitude": coords[0], "longitude": coords[1],
                "corrigido_manual": True,
            })
            print(f"  {GRN}✓ movido para a esquina exata ({coords[0]:.5f},{coords[1]:.5f}){RST}")
            stats["cruz"] += 1
        else:
            print(f"  {YEL}O OpenStreetMap não tem essa esquina mapeada.{RST}")
            alt = input(f"    {DIM}cole a coord do Google Maps (-28.2,-52.4) ou enter p/ pular:{RST} ").strip()
            m2 = re.search(r"(-?\d+[.,]\d+)\s*[, ]\s*(-?\d+[.,]\d+)", alt)
            if m2:
                nlat = float(m2.group(1).replace(",", "."))
                nlon = float(m2.group(2).replace(",", "."))
                _atualizar(id_, {
                    "loc_tipo": "cruzamento", "loc_rua1": rua1.title(), "loc_rua2": rua2,
                    "loc_endereco": f"{rua1.title()} e {rua2}, {muni}, RS, Brasil",
                    "latitude": nlat, "longitude": nlon, "corrigido_manual": True,
                })
                print(f"  {GRN}✓ fixado em ({nlat:.5f},{nlon:.5f}){RST}")
                stats["coord"] += 1
            else:
                stats["pula"] += 1

    print(f"\n{B}Resumo:{RST} {GRN}{stats['cruz']} esquinas{RST}, "
          f"{stats['coord']} por coordenada, {stats['ok']} confirmados, "
          f"{stats['rua']} viraram rua, {stats['pula']} pulados.")
    corrigidos = stats["cruz"] + stats["coord"] + stats["ok"] + stats["rua"]
    if corrigidos:
        print(f"{DIM}Não esqueça de commitar: git add data/acidentes.duckdb && "
              f"git commit -m \"Correcoes manuais de esquinas\" && git push{RST}")


if __name__ == "__main__":
    main()
