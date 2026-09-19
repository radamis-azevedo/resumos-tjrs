#!/usr/bin/env python3
"""
Gera o HTML de resumos de conteúdo (matéria → assunto) a partir dos arquivos
JSON em resumos/dados/.

Divisão de trabalho:
  - resumos/dados/*.json  -> CONTEÚDO (escrito à mão a partir das notas do vault)
  - este script           -> APRESENTAÇÃO (o HTML é regenerável; não editar à mão)

Arquivos de dados:
  00-meta.json  -> {titulo, subtitulo, prova, fonte, rodape}
  NN-<id>.json  -> {materia: {...}, abas: [{id, nome, grupos: [{nome, cards: [...]}]}]}

  Matérias com o mesmo "materia.id" em arquivos diferentes são fundidas
  (as abas são concatenadas na ordem dos arquivos) — é assim que uma rodada
  nova acrescenta TN/RCPN/TP/RTD ao bloco de DNR sem mexer no que já existe.

Estrutura de um card:
  {id, titulo, edital, fontes: [], regra,
   blocos: [{tipo: tabela|lista|timeline, titulo, ...}],
   exemplo: {titulo, caso, solucao},
   citacoes: [{ref, texto, literal}],
   pegadinhas: [{errado, certo}],
   ponte: {titulo, itens: []}}

Texto aceita marcação inline: **negrito**, *itálico*, `código`.

Uso:
  python3 gerar_resumos.py
  python3 gerar_resumos.py --dados <dir> --saida <arquivo.html> --vault <dir>
  python3 gerar_resumos.py --sem-cobertura
"""
import argparse
import html
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DADOS_PADRAO = RAIZ / "resumos" / "dados"
# docs/ é a pasta publicada pelo GitHub Pages (Settings → Pages → branch main, /docs)
SAIDA_PADRAO = RAIZ / "docs" / "index.html"
VAULT_PADRAO = Path(
    "/Users/radamisazevedo/Library/Mobile Documents/iCloud~md~obsidian/"
    "Documents/Obsidian Henrique/04 Estudos"
)
# pastas do vault que não são conteúdo de estudo
IGNORAR_NO_VAULT = {"Provas Anteriores e Simulados"}


# ---------------------------------------------------------------- utilidades

def inline(texto):
    """Escapa HTML e aplica **negrito**, *itálico* e `código`."""
    t = html.escape(str(texto), quote=False)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", t)
    return t


def slug(texto):
    base = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-zA-Z0-9]+", "-", base).strip("-").lower()
    return base or "item"


def carregar(dados_dir):
    """Lê 00-meta.json e os arquivos de matéria, fundindo por materia.id."""
    dados_dir = Path(dados_dir)
    if not dados_dir.is_dir():
        sys.exit(f"erro: diretório de dados não encontrado: {dados_dir}")

    meta = {}
    materias = []
    por_id = {}

    for arq in sorted(dados_dir.glob("*.json")):
        try:
            conteudo = json.loads(arq.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            sys.exit(f"erro: JSON inválido em {arq.name}: {e}")

        if arq.name.startswith("00-") or "materia" not in conteudo:
            meta.update(conteudo)
            continue

        m = conteudo["materia"]
        mid = m["id"]
        if mid in por_id:
            por_id[mid]["abas"].extend(conteudo.get("abas", []))
        else:
            registro = dict(m)
            registro["abas"] = list(conteudo.get("abas", []))
            por_id[mid] = registro
            materias.append(registro)

    materias.sort(key=lambda m: m.get("ordem", 99))
    if not materias:
        sys.exit(f"erro: nenhum arquivo de matéria encontrado em {dados_dir}")
    return meta, materias


def contar_cards(materia):
    return sum(len(g.get("cards", [])) for a in materia["abas"] for g in a.get("grupos", []))


def dias_para(iso):
    try:
        alvo = date.fromisoformat(iso)
    except (TypeError, ValueError):
        return None
    return (alvo - date.today()).days


# ------------------------------------------------------------------ cobertura

def cobertura(materias, vault):
    """Notas .md do vault que ainda não foram citadas em nenhuma ficha."""
    vault = Path(vault)
    if not vault.is_dir():
        return None

    citadas = set()
    for m in materias:
        for a in m["abas"]:
            for g in a.get("grupos", []):
                for c in g.get("cards", []):
                    citadas.update(c.get("fontes", []))

    pendentes = {}
    for arq in sorted(vault.rglob("*.md")):
        rel = arq.relative_to(vault)
        if rel.parts[0] in IGNORAR_NO_VAULT:
            continue
        if arq.stem in citadas:
            continue
        pendentes.setdefault(str(rel.parent), []).append(arq.stem)
    return pendentes


# -------------------------------------------------------------- render (HTML)

def render_blocos(blocos):
    out = []
    for b in blocos or []:
        tipo = b.get("tipo", "lista")
        titulo = f'<h4 class="bloco-t">{inline(b["titulo"])}</h4>' if b.get("titulo") else ""

        if tipo == "tabela":
            cols = b.get("colunas", [])
            cabec = "".join(f"<th>{inline(c)}</th>" for c in cols)
            linhas = "".join(
                "<tr>" + "".join(f"<td>{inline(cel)}</td>" for cel in lin) + "</tr>"
                for lin in b.get("linhas", [])
            )
            out.append(
                f'<div class="bloco">{titulo}<div class="tw">'
                f"<table><thead><tr>{cabec}</tr></thead><tbody>{linhas}</tbody></table>"
                "</div></div>"
            )
        elif tipo == "timeline":
            itens = "".join(f"<li>{inline(i)}</li>" for i in b.get("itens", []))
            out.append(f'<div class="bloco">{titulo}<ol class="tl">{itens}</ol></div>')
        else:
            itens = "".join(f"<li>{inline(i)}</li>" for i in b.get("itens", []))
            out.append(f'<div class="bloco">{titulo}<ul class="lst">{itens}</ul></div>')
    return "".join(out)


def texto_busca(card):
    """Texto achatado do card, para o filtro de busca no HTML."""
    partes = [card.get("titulo", ""), card.get("regra", ""), card.get("edital", "")]
    partes += card.get("fontes", [])
    for b in card.get("blocos", []):
        partes.append(b.get("titulo", ""))
        partes += b.get("itens", [])
        partes += b.get("colunas", [])
        for lin in b.get("linhas", []):
            partes += list(lin)
    ex = card.get("exemplo") or {}
    partes += [ex.get("titulo", ""), ex.get("caso", ""), ex.get("solucao", "")]
    for c in card.get("citacoes", []):
        partes += [c.get("ref", ""), c.get("texto", "")]
    for p in card.get("pegadinhas", []):
        partes += [p.get("errado", ""), p.get("certo", "")]
    partes += (card.get("ponte") or {}).get("itens", [])
    bruto = " ".join(str(p) for p in partes)
    bruto = re.sub(r"[*`\"']", " ", bruto)
    bruto = re.sub(r"\s+", " ", bruto).strip().lower()
    # sem acento: a busca no HTML dobra a consulta da mesma forma
    return "".join(
        c for c in unicodedata.normalize("NFD", bruto) if not unicodedata.combining(c)
    )


def render_card(card):
    cid = card.get("id") or slug(card["titulo"])
    edital = (
        f'<span class="tag tag-edital" title="Bloco do edital TJRS">📜 {inline(card["edital"])}</span>'
        if card.get("edital")
        else ""
    )
    fontes = ""
    if card.get("fontes"):
        nomes = " · ".join(html.escape(f) for f in card["fontes"])
        fontes = f'<p class="fonte" title="Notas de origem no vault">📓 {nomes}</p>'

    partes = [
        f'<section class="card" id="{cid}" data-busca="{html.escape(texto_busca(card), quote=True)}">',
        '<header class="card-h">',
        f'<h3>{inline(card["titulo"])}</h3>',
        f'<div class="card-meta">{edital}'
        f'<button class="st" type="button" data-card="{cid}" aria-label="Marcar status de revisão">•</button>'
        "</div>",
        "</header>",
        fontes,
    ]

    if card.get("regra"):
        partes.append(
            '<div class="regra"><span class="rot">🎯 Regra-chave</span>'
            f'<p>{inline(card["regra"])}</p></div>'
        )

    partes.append(render_blocos(card.get("blocos")))

    ex = card.get("exemplo")
    if ex:
        t = f' — {inline(ex["titulo"])}' if ex.get("titulo") else ""
        partes.append(
            f'<div class="bloco ex"><h4 class="bloco-t">⚖️ Exemplo prático{t}</h4>'
            f'<p class="caso">{inline(ex.get("caso", ""))}</p>'
            '<details class="sol" open><summary>Solução</summary>'
            f'<p>{inline(ex.get("solucao", ""))}</p></details></div>'
        )

    if card.get("citacoes"):
        itens = []
        for c in card["citacoes"]:
            literal = c.get("literal", False)
            marca = (
                '<span class="sel sel-lit">literal</span>'
                if literal
                else '<span class="sel sel-sin">síntese</span>'
            )
            corpo = inline(c.get("texto", ""))
            corpo = f"“{corpo}”" if literal else corpo
            itens.append(
                f'<li><span class="disp">{inline(c["ref"])}</span> {marca}'
                f'<span class="txt">{corpo}</span></li>'
            )
        partes.append(
            '<div class="bloco leg"><h4 class="bloco-t">📌 Base legal</h4>'
            f'<ul class="cit">{"".join(itens)}</ul></div>'
        )

    if card.get("pegadinhas"):
        linhas = "".join(
            f'<tr><td class="err">{inline(p["errado"])}</td>'
            f'<td class="cer">{inline(p["certo"])}</td></tr>'
            for p in card["pegadinhas"]
        )
        partes.append(
            '<div class="bloco peg"><h4 class="bloco-t">🪤 Pegadinhas</h4><div class="tw">'
            "<table><thead><tr><th>O que a banca escreve</th><th>O que é certo</th></tr></thead>"
            f"<tbody>{linhas}</tbody></table></div></div>"
        )

    ponte = card.get("ponte")
    if ponte:
        itens = "".join(f"<li>{inline(i)}</li>" for i in ponte.get("itens", []))
        titulo = inline(ponte.get("titulo", "🏛️ Ponte para o DNR"))
        partes.append(f'<div class="bloco ponte"><h4 class="bloco-t">{titulo}</h4><ul>{itens}</ul></div>')

    partes.append("</section>")
    return "".join(partes)


def render_materia(materia, ativa):
    abas = materia["abas"]
    bot_abas = "".join(
        f'<button class="aba{" on" if i == 0 else ""}" type="button" '
        f'data-aba="{a["id"]}">{inline(a["nome"])}</button>'
        for i, a in enumerate(abas)
    )
    paineis = []
    for i, a in enumerate(abas):
        grupos = []
        for g in a.get("grupos", []):
            cards = "".join(render_card(c) for c in g.get("cards", []))
            nome = f'<h2 class="grupo">{inline(g["nome"])}</h2>' if g.get("nome") else ""
            grupos.append(f'<div class="grupo-bloco">{nome}{cards}</div>')
        paineis.append(
            f'<div class="painel-aba{" on" if i == 0 else ""}" data-painel="{a["id"]}">'
            f'{"".join(grupos)}</div>'
        )

    nota = f'<p class="nota-mat">{inline(materia["nota"])}</p>' if materia.get("nota") else ""
    return (
        f'<div class="painel{" on" if ativa else ""}" data-materia="{materia["id"]}">'
        f"{nota}"
        f'<nav class="abas">{bot_abas}</nav>'
        f'{"".join(paineis)}</div>'
    )


def render_cobertura(pendentes):
    if not pendentes:
        return ""
    blocos = []
    total = 0
    for pasta, notas in sorted(pendentes.items()):
        total += len(notas)
        itens = "".join(f"<li>{html.escape(n)}</li>" for n in notas)
        blocos.append(f"<div><h4>{html.escape(pasta)}</h4><ul>{itens}</ul></div>")
    return (
        '<details class="cobertura"><summary>📋 Notas do vault ainda sem ficha '
        f"({total})</summary><div class='cob-grid'>{''.join(blocos)}</div></details>"
    )


CSS = """
:root{
  --bg:#f6f4ef; --surface:#fffdf9; --surface-2:#f1ede4; --line:#e2dccf;
  --ink:#231f1a; --ink-2:#5d564c; --ink-3:#8b8376;
  --accent:#9a3b1f; --accent-soft:#f6e7e0;
  --dnr:#1f6b52; --dnr-soft:#e2f0ea;
  --warn:#a8331f; --warn-soft:#fbe8e4;
  --ok:#2c6a3f; --ok-soft:#e4f1e6;
  --law:#3b4a86; --law-soft:#e7eaf6;
  --radius:12px; --sh:0 1px 2px rgba(35,31,26,.06),0 4px 16px rgba(35,31,26,.05);
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --bg:#16141f; --surface:#1e1b28; --surface-2:#262232; --line:#332e42;
    --ink:#ece8f5; --ink-2:#b4adc4; --ink-3:#847d96;
    --accent:#f0a58a; --accent-soft:#3a2620;
    --dnr:#7fd8b4; --dnr-soft:#17302a;
    --warn:#f2a094; --warn-soft:#3a2321;
    --ok:#95d6a4; --ok-soft:#1c3125;
    --law:#a9b6f0; --law-soft:#232742;
    --sh:0 1px 2px rgba(0,0,0,.4),0 4px 18px rgba(0,0,0,.3);
  }
}
:root[data-theme="dark"]{
  --bg:#16141f; --surface:#1e1b28; --surface-2:#262232; --line:#332e42;
  --ink:#ece8f5; --ink-2:#b4adc4; --ink-3:#847d96;
  --accent:#f0a58a; --accent-soft:#3a2620;
  --dnr:#7fd8b4; --dnr-soft:#17302a;
  --warn:#f2a094; --warn-soft:#3a2321;
  --ok:#95d6a4; --ok-soft:#1c3125;
  --law:#a9b6f0; --law-soft:#232742;
  --sh:0 1px 2px rgba(0,0,0,.4),0 4px 18px rgba(0,0,0,.3);
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0; background:var(--bg); color:var(--ink);
  font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif;
  padding-bottom:4rem;
}
.wrap{max-width:1040px; margin:0 auto; padding:0 16px}

/* cabeçalho */
header.top{padding:2.4rem 0 1.2rem}
h1{font-size:clamp(1.6rem,4.4vw,2.3rem); line-height:1.18; margin:0 0 .35rem; letter-spacing:-.02em}
.sub{color:var(--ink-2); margin:0 0 1rem; max-width:62ch}
.chips{display:flex; flex-wrap:wrap; gap:.45rem; align-items:center}
.chip{
  font-size:.78rem; padding:.2rem .6rem; border-radius:999px;
  background:var(--surface-2); color:var(--ink-2); border:1px solid var(--line);
}
.chip.forte{background:var(--accent-soft); color:var(--accent); border-color:transparent; font-weight:600}

/* barra fixa */
.barra{position:sticky; top:0; z-index:20; background:var(--bg); padding-top:.5rem;
  border-bottom:1px solid var(--line); margin-bottom:1.2rem}
.mats{display:flex; flex-wrap:wrap; gap:.5rem; margin-bottom:.6rem}
.mat{
  display:flex; align-items:center; gap:.45rem; cursor:pointer;
  border:1px solid var(--line); background:var(--surface); color:var(--ink);
  padding:.5rem .9rem; border-radius:999px; font-size:.95rem; font-weight:600;
  font-family:inherit; transition:.15s;
}
.mat:hover{border-color:var(--ink-3)}
.mat.on{background:var(--ink); color:var(--bg); border-color:var(--ink)}
.mat .n{font-weight:500; opacity:.7; font-size:.82rem}
.ferramentas{display:flex; flex-wrap:wrap; gap:.5rem; align-items:center; padding-bottom:.6rem}
#busca{
  flex:1 1 220px; min-width:0; padding:.5rem .75rem; border-radius:8px;
  border:1px solid var(--line); background:var(--surface); color:var(--ink); font:inherit; font-size:.9rem;
}
#busca:focus{outline:2px solid var(--accent); outline-offset:1px}
.tgl{
  cursor:pointer; border:1px solid var(--line); background:var(--surface); color:var(--ink-2);
  padding:.5rem .8rem; border-radius:8px; font:inherit; font-size:.85rem; white-space:nowrap;
}
.tgl.on{background:var(--accent-soft); color:var(--accent); border-color:transparent; font-weight:600}
.contagem{font-size:.8rem; color:var(--ink-3); margin-left:auto}

/* abas */
.painel{display:none} .painel.on{display:block}
.nota-mat{font-size:.88rem; color:var(--ink-2); margin:.2rem 0 1rem; max-width:70ch}
.abas{display:flex; flex-wrap:wrap; gap:.4rem; margin-bottom:1.4rem}
.aba{
  cursor:pointer; border:1px solid var(--line); background:transparent; color:var(--ink-2);
  padding:.35rem .8rem; border-radius:8px; font:inherit; font-size:.86rem;
}
.aba.on{background:var(--surface); color:var(--ink); border-color:var(--ink-3); font-weight:600}
.painel-aba{display:none} .painel-aba.on{display:block}

/* grupos e cards */
.grupo{
  font-size:.76rem; text-transform:uppercase; letter-spacing:.1em; color:var(--ink-3);
  margin:2rem 0 .8rem; padding-bottom:.4rem; border-bottom:1px solid var(--line); font-weight:700;
}
.grupo-bloco:first-child .grupo{margin-top:.4rem}
.card{
  background:var(--surface); border:1px solid var(--line); border-radius:var(--radius);
  box-shadow:var(--sh); padding:1.25rem 1.3rem 1.35rem; margin-bottom:1rem; scroll-margin-top:7.5rem;
}
.card.oculto{display:none}
.card-h{display:flex; gap:.8rem; align-items:flex-start; justify-content:space-between}
.card-h h3{margin:0; font-size:1.12rem; line-height:1.3; letter-spacing:-.01em}
.card-meta{display:flex; align-items:center; gap:.4rem; flex-shrink:0}
.tag{font-size:.7rem; padding:.15rem .45rem; border-radius:6px; white-space:nowrap}
.tag-edital{background:var(--surface-2); color:var(--ink-2); border:1px solid var(--line)}
.st{
  width:26px; height:26px; border-radius:50%; cursor:pointer; font-size:.8rem; line-height:1;
  border:1px solid var(--line); background:var(--surface-2); color:var(--ink-3); font-family:inherit;
}
.st[data-v="ok"]{background:var(--ok-soft); color:var(--ok); border-color:transparent}
.st[data-v="rev"]{background:var(--warn-soft); color:var(--warn); border-color:transparent}
.fonte{font-size:.74rem; color:var(--ink-3); margin:.45rem 0 0}

.regra{
  margin:.9rem 0 0; padding:.75rem .9rem; border-radius:10px;
  background:var(--accent-soft); border-left:3px solid var(--accent);
}
.regra .rot{
  display:block; font-size:.7rem; font-weight:700; text-transform:uppercase;
  letter-spacing:.08em; color:var(--accent); margin-bottom:.25rem;
}
.regra p{margin:0}

.bloco{margin-top:1.1rem}
.bloco-t{
  font-size:.82rem; font-weight:700; margin:0 0 .5rem; color:var(--ink-2);
  letter-spacing:.01em;
}
.tw{overflow-x:auto; -webkit-overflow-scrolling:touch; border:1px solid var(--line); border-radius:10px}
table{border-collapse:collapse; width:100%; font-size:.87rem; min-width:420px}
th,td{padding:.5rem .65rem; text-align:left; vertical-align:top; border-bottom:1px solid var(--line)}
th{background:var(--surface-2); font-size:.76rem; text-transform:uppercase; letter-spacing:.05em; color:var(--ink-2)}
tr:last-child td{border-bottom:none}
.lst{margin:0; padding-left:1.1rem} .lst li{margin-bottom:.35rem}
.tl{margin:0; padding-left:0; list-style:none; counter-reset:t}
.tl li{
  counter-increment:t; position:relative; padding:.1rem 0 .7rem 1.9rem;
  border-left:2px solid var(--line); margin-left:.7rem;
}
.tl li:last-child{border-left-color:transparent; padding-bottom:0}
.tl li::before{
  content:counter(t); position:absolute; left:-.72rem; top:0; width:1.35rem; height:1.35rem;
  border-radius:50%; background:var(--accent); color:#fff; font-size:.7rem; font-weight:700;
  display:flex; align-items:center; justify-content:center;
}

.ex{background:var(--surface-2); border-radius:10px; padding:.85rem .95rem}
.ex .caso{margin:0}
.sol{margin-top:.6rem; border-top:1px dashed var(--line); padding-top:.5rem}
.sol summary{
  cursor:pointer; font-size:.78rem; font-weight:700; color:var(--ok);
  text-transform:uppercase; letter-spacing:.06em;
}
.sol p{margin:.5rem 0 0}

.cit{list-style:none; margin:0; padding:0}
.cit li{
  padding:.55rem .7rem; border-left:3px solid var(--law); background:var(--law-soft);
  border-radius:0 8px 8px 0; margin-bottom:.4rem; font-size:.87rem;
}
.disp{font-weight:700; color:var(--law); margin-right:.4rem}
.sel{font-size:.63rem; padding:.05rem .3rem; border-radius:4px; text-transform:uppercase;
  letter-spacing:.05em; vertical-align:middle; margin-right:.35rem}
.sel-lit{background:var(--law); color:#fff}
.sel-sin{background:transparent; color:var(--ink-3); border:1px solid var(--ink-3)}
.cit .txt{color:var(--ink-2)}

.peg td.err{color:var(--warn); width:46%}
.peg td.cer{color:var(--ok)}
.peg tbody tr td.err::before{content:"✗ "; font-weight:700}
.peg tbody tr td.cer::before{content:"✓ "; font-weight:700}

.ponte{
  background:var(--dnr-soft); border-radius:10px; padding:.85rem .95rem;
  border-left:3px solid var(--dnr);
}
.ponte .bloco-t{color:var(--dnr)}
.ponte ul{margin:0; padding-left:1.1rem} .ponte li{margin-bottom:.4rem}
.ponte li:last-child{margin-bottom:0}

/* modo revisão: as soluções ficam fechadas (o próprio <details> esconde) */
body.revisao .sol:not([open]) summary::after{content:" — clique para revelar"; font-weight:400; text-transform:none; letter-spacing:0; color:var(--ink-3)}
body.revisao .peg td.cer{color:transparent; background:var(--surface-2); border-radius:6px; cursor:pointer}
body.revisao .peg td.cer::before{content:"?"; color:var(--ink-3)}
body.revisao .peg td.cer.rev{color:var(--ok); background:transparent}
body.revisao .peg td.cer.rev::before{content:"✓ "; color:var(--ok)}

.vazio{padding:2rem 0; color:var(--ink-3); text-align:center; display:none}
.vazio.on{display:block}

.cobertura{margin:2.5rem 0 1rem; font-size:.85rem; color:var(--ink-2)}
.cobertura summary{cursor:pointer; font-weight:600}
.cob-grid{display:grid; gap:1rem; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); margin-top:.8rem}
.cob-grid h4{margin:0 0 .3rem; font-size:.78rem; color:var(--ink-3); text-transform:uppercase; letter-spacing:.06em}
.cob-grid ul{margin:0; padding-left:1.1rem} .cob-grid li{margin-bottom:.15rem}

footer{margin-top:2.5rem; padding-top:1.2rem; border-top:1px solid var(--line);
  font-size:.78rem; color:var(--ink-3)}
footer p{margin:.3rem 0}

@media (max-width:640px){
  body{font-size:15px}
  .card{padding:1rem .95rem 1.1rem}
  .card-h{flex-direction:column; gap:.5rem}
  .card-meta{align-self:flex-start}
  .contagem{margin-left:0; width:100%}
}
@media print{
  .barra,.st,.cobertura{display:none!important}
  .painel,.painel-aba{display:block!important}
  .card{break-inside:avoid; box-shadow:none; border-color:#ccc}
  body{background:#fff}
}
"""

JS = """
(function(){
  var d=document, b=d.body;
  function q(s,r){return Array.prototype.slice.call((r||d).querySelectorAll(s));}
  function ls(fn,alt){try{return fn();}catch(e){return alt;}}

  // matérias
  q('.mat').forEach(function(bt){
    bt.addEventListener('click',function(){
      q('.mat').forEach(function(x){x.classList.toggle('on',x===bt);});
      q('.painel').forEach(function(p){p.classList.toggle('on',p.dataset.materia===bt.dataset.mat);});
      filtrar();
      window.scrollTo({top:0,behavior:'smooth'});
    });
  });

  // abas
  q('.aba').forEach(function(bt){
    bt.addEventListener('click',function(){
      var painel=bt.closest('.painel');
      q('.aba',painel).forEach(function(x){x.classList.toggle('on',x===bt);});
      q('.painel-aba',painel).forEach(function(p){p.classList.toggle('on',p.dataset.painel===bt.dataset.aba);});
      filtrar();
    });
  });

  // busca
  var busca=d.getElementById('busca'), vazio=d.getElementById('vazio'), cont=d.getElementById('contagem');
  function dobrar(s){
    return (s||'').trim().toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'');
  }
  function filtrar(){
    var t=dobrar(busca.value), n=0;
    q('.card').forEach(function(c){
      var bate=!t || c.dataset.busca.indexOf(t)>-1;
      c.classList.toggle('oculto',!bate);
    });
    if(t){
      // busca global: abre todas as matérias e abas, conta o que sobrou
      q('.painel, .painel-aba').forEach(function(p){p.classList.add('on');});
      n=q('.card:not(.oculto)').length;
    } else {
      var mat=d.querySelector('.mat.on').dataset.mat;
      q('.painel').forEach(function(p){
        p.classList.toggle('on',p.dataset.materia===mat);
        var abaOn=p.querySelector('.aba.on');
        q('.painel-aba',p).forEach(function(x){
          x.classList.toggle('on',!!abaOn && x.dataset.painel===abaOn.dataset.aba);
        });
      });
      n=q('.painel.on .painel-aba.on .card:not(.oculto)').length;
    }
    vazio.classList.toggle('on',n===0);
    cont.textContent=n+(n===1?' ficha':' fichas');
  }
  busca.addEventListener('input',filtrar);
  d.addEventListener('keydown',function(e){
    if(e.key==='/'&&d.activeElement!==busca){e.preventDefault();busca.focus();}
    if(e.key==='Escape'&&d.activeElement===busca){busca.value='';filtrar();busca.blur();}
  });

  // modo revisão
  var mr=d.getElementById('mrev');
  function aplicarRevisao(on){
    b.classList.toggle('revisao',on);
    mr.classList.toggle('on',on);
    mr.setAttribute('aria-pressed',on?'true':'false');
    q('.sol').forEach(function(s){s.open=!on;});
    q('.peg td.cer').forEach(function(c){c.classList.remove('rev');});
    ls(function(){localStorage.setItem('tjrs-revisao',on?'1':'0');});
  }
  mr.addEventListener('click',function(){aplicarRevisao(!b.classList.contains('revisao'));});
  d.addEventListener('click',function(e){
    if(!b.classList.contains('revisao')) return;
    var cel=e.target.closest ? e.target.closest('.cer') : null;   // pode clicar num <strong> dentro do td
    if(cel) cel.classList.add('rev');
  });

  // tema
  var tt=d.getElementById('tema');
  tt.addEventListener('click',function(){
    var escuro=d.documentElement.getAttribute('data-theme')==='dark'
      || (!d.documentElement.getAttribute('data-theme') && matchMedia('(prefers-color-scheme:dark)').matches);
    var novo=escuro?'light':'dark';
    d.documentElement.setAttribute('data-theme',novo);
    ls(function(){localStorage.setItem('tjrs-tema',novo);});
  });

  // status por ficha
  var ciclo={'':'ok','ok':'rev','rev':''}, rot={'':'•','ok':'✓','rev':'↻'};
  var estado=ls(function(){return JSON.parse(localStorage.getItem('tjrs-status')||'{}');},{})||{};
  function pintar(bt){
    var v=estado[bt.dataset.card]||'';
    bt.dataset.v=v; bt.textContent=rot[v];
    bt.title=v==='ok'?'Sei este assunto':(v==='rev'?'Revisar':'Sem marcação');
  }
  q('.st').forEach(function(bt){
    pintar(bt);
    bt.addEventListener('click',function(){
      estado[bt.dataset.card]=ciclo[estado[bt.dataset.card]||''];
      if(!estado[bt.dataset.card]) delete estado[bt.dataset.card];
      pintar(bt);
      ls(function(){localStorage.setItem('tjrs-status',JSON.stringify(estado));});
    });
  });

  // restaurar preferências
  var tema=ls(function(){return localStorage.getItem('tjrs-tema');},null);
  if(tema) d.documentElement.setAttribute('data-theme',tema);
  if(ls(function(){return localStorage.getItem('tjrs-revisao');},null)==='1') aplicarRevisao(true);
  filtrar();
})();
"""


def render(meta, materias, pendentes):
    total = sum(contar_cards(m) for m in materias)
    dias = dias_para(meta.get("prova"))

    chips = [f'<span class="chip">{total} fichas</span>']
    if dias is not None:
        chips.append(f'<span class="chip forte">faltam {dias} dias para a objetiva</span>')
    for m in materias:
        chips.append(
            f'<span class="chip">{m.get("icone","")} {html.escape(m["nome"])} · '
            f'{contar_cards(m)} · {html.escape(m.get("peso",""))}</span>'
        )

    bot_mats = "".join(
        f'<button class="mat{" on" if i == 0 else ""}" type="button" data-mat="{m["id"]}">'
        f'<span>{m.get("icone","")}</span> {inline(m["nome"])} '
        f'<span class="n">{contar_cards(m)}</span></button>'
        for i, m in enumerate(materias)
    )
    paineis = "".join(render_materia(m, i == 0) for i, m in enumerate(materias))

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(meta.get("titulo", "Resumos"))}</title>
<meta name="description" content="{html.escape(meta.get("subtitulo", ""))}">
<meta name="robots" content="noindex, nofollow">
<meta name="color-scheme" content="light dark">
<meta name="apple-mobile-web-app-title" content="Resumos TJRS">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E%F0%9F%93%9A%3C/text%3E%3C/svg%3E">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header class="top">
  <h1>{inline(meta.get("titulo", "Resumos"))}</h1>
  <p class="sub">{inline(meta.get("subtitulo", ""))}</p>
  <div class="chips">{"".join(chips)}</div>
</header>

<div class="barra">
  <nav class="mats">{bot_mats}</nav>
  <div class="ferramentas">
    <input id="busca" type="search" placeholder="Buscar assunto, artigo, pegadinha…  ( / )" autocomplete="off">
    <button id="mrev" class="tgl" type="button" aria-pressed="false" title="Esconde soluções e respostas das pegadinhas">🧠 Modo revisão</button>
    <button id="tema" class="tgl" type="button" title="Alternar tema">◐</button>
    <span id="contagem" class="contagem"></span>
  </div>
</div>

<main>
{paineis}
<p id="vazio" class="vazio">Nenhuma ficha encontrada para essa busca.</p>
</main>

{render_cobertura(pendentes)}

<footer>
  <p><strong>Fonte:</strong> {inline(meta.get("fonte", ""))}</p>
  <p>{inline(meta.get("rodape", ""))}</p>
  <p>Gerado em {date.today().strftime("%d/%m/%Y")} por <code>.claude/scripts/gerar_resumos.py</code> —
     o HTML é regenerável; editar o conteúdo em <code>resumos/dados/*.json</code>.</p>
</footer>
</div>
<script>{JS}</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description="Gera o HTML de resumos de conteúdo do TJRS.")
    ap.add_argument("--dados", default=str(DADOS_PADRAO), help="diretório dos JSON de conteúdo")
    ap.add_argument("--saida", default=str(SAIDA_PADRAO), help="arquivo HTML de saída")
    ap.add_argument("--vault", default=str(VAULT_PADRAO), help="pasta 04 Estudos do vault")
    ap.add_argument("--sem-cobertura", action="store_true", help="não checar notas sem ficha")
    args = ap.parse_args()

    meta, materias = carregar(args.dados)
    pendentes = None if args.sem_cobertura else cobertura(materias, args.vault)

    saida = Path(args.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(render(meta, materias, pendentes), encoding="utf-8")

    total = sum(contar_cards(m) for m in materias)
    print(f"✔ {saida}  —  {total} fichas em {len(materias)} matérias")
    for m in materias:
        abas = ", ".join(a["nome"] for a in m["abas"])
        print(f"   {m.get('icone','')} {m['nome']}: {contar_cards(m)} fichas ({abas})")
    if pendentes:
        n = sum(len(v) for v in pendentes.values())
        print(f"   ⚠ {n} notas do vault ainda sem ficha (listadas no rodapé do HTML)")
    elif pendentes == {}:
        print("   ✔ todas as notas do vault têm ficha")
    elif pendentes is None and not args.sem_cobertura:
        print("   ⚠ vault não encontrado — cobertura não verificada")


if __name__ == "__main__":
    main()
