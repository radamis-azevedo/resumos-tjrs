#!/usr/bin/env python3
"""
Gera o HTML de resumos de conteúdo (matéria → assunto) a partir dos arquivos
JSON em resumos/dados/.

Divisão de trabalho:
  - resumos/dados/*.json  -> CONTEÚDO (escrito à mão a partir das notas do vault)
  - este script           -> APRESENTAÇÃO (o HTML é regenerável; não editar à mão)

Arquivos de dados:
  00-meta.json  -> {titulo, subtitulo, prova, fonte, rodape}
  NN-<id>.json  -> {materia: {...}, abas: [{id, nome, tipo?, intro?, grupos: [...]}]}

  Matérias com o mesmo "materia.id" em arquivos diferentes são fundidas
  (as abas são concatenadas na ordem dos arquivos) — é assim que uma rodada
  nova acrescenta TN/RCPN/TP/RTD ao bloco de DNR sem mexer no que já existe.
  "materia.cor" (hex) define a cor daquela disciplina na página.

Dois tipos de ficha:
  assunto  {id, titulo, edital, fontes[], regra, blocos[], exemplo{}, citacoes[],
            pegadinhas[], ponte{}}
  crítico  {id, titulo, armadilha, porque, regra, citacoes[], gatilho, ficha}
            — aba com "tipo": "criticos", o ponto em que o estudo falhou

  blocos[]: {tipo: tabela|lista|timeline, titulo, colunas[], linhas[][], itens[]}

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
    "/Users/radamisazevedo/Obsidian/Obsidian Henrique/04 Estudos"
)
IGNORAR_NO_VAULT = {"Provas Anteriores e Simulados"}
COR_PADRAO = "#7a5230"


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


def sem_acento(texto):
    return "".join(
        c for c in unicodedata.normalize("NFD", str(texto)) if not unicodedata.combining(c)
    )


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


def cards_da(materia):
    for aba in materia["abas"]:
        for grupo in aba.get("grupos", []):
            for card in grupo.get("cards", []):
                yield aba, card


def contar_cards(materia, tipo=None):
    total = 0
    for aba, _card in cards_da(materia):
        if tipo is None or aba.get("tipo", "assuntos") == tipo:
            total += 1
    return total


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
        for _aba, card in cards_da(m):
            citadas.update(card.get("fontes", []))

    pendentes = {}
    for arq in sorted(vault.rglob("*.md")):
        rel = arq.relative_to(vault)
        if rel.parts[0] in IGNORAR_NO_VAULT or arq.stem in citadas:
            continue
        pendentes.setdefault(str(rel.parent), []).append(arq.stem)
    return pendentes


# -------------------------------------------------------------- render (HTML)

def render_blocos(blocos):
    out = []
    for b in blocos or []:
        tipo = b.get("tipo", "lista")
        titulo = f'<h4 class="rot">{inline(b["titulo"])}</h4>' if b.get("titulo") else ""

        if tipo == "tabela":
            cabec = "".join(f"<th>{inline(c)}</th>" for c in b.get("colunas", []))
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


def render_citacoes(citacoes):
    if not citacoes:
        return ""
    itens = []
    for c in citacoes:
        literal = c.get("literal", False)
        marca = (
            '<span class="sel sel-lit" title="Texto literal do dispositivo">literal</span>'
            if literal
            else '<span class="sel sel-sin" title="Paráfrase — conferir na fonte">síntese</span>'
        )
        corpo = inline(c.get("texto", ""))
        corpo = f"“{corpo}”" if literal else corpo
        itens.append(
            f'<li><span class="disp">{inline(c["ref"])}</span>{marca}'
            f'<span class="txt">{corpo}</span></li>'
        )
    return (
        '<div class="bloco leg"><h4 class="rot">Base legal</h4>'
        f'<ul class="cit">{"".join(itens)}</ul></div>'
    )


def texto_busca(card):
    """Texto achatado do card (sem acento), para o filtro de busca no HTML."""
    partes = [card.get(k, "") for k in
              ("titulo", "regra", "edital", "armadilha", "porque", "gatilho")]
    partes += card.get("fontes", [])
    for b in card.get("blocos", []):
        partes += [b.get("titulo", "")] + b.get("itens", []) + b.get("colunas", [])
        for lin in b.get("linhas", []):
            partes += list(lin)
    ex = card.get("exemplo") or {}
    partes += [ex.get("titulo", ""), ex.get("caso", ""), ex.get("solucao", "")]
    for c in card.get("citacoes", []):
        partes += [c.get("ref", ""), c.get("texto", "")]
    for p in card.get("pegadinhas", []):
        partes += [p.get("errado", ""), p.get("certo", "")]
    partes += (card.get("ponte") or {}).get("itens", [])
    bruto = re.sub(r"[*`\"']", " ", " ".join(str(p) for p in partes))
    return sem_acento(re.sub(r"\s+", " ", bruto).strip().lower())


def cabecalho_card(card, cid, num, extra_tag=""):
    edital = (
        f'<span class="tag" title="Bloco do edital TJRS">{inline(card["edital"])}</span>'
        if card.get("edital") else ""
    )
    return (
        '<header class="card-h">'
        f'<div class="card-id"><span class="prot">{num:03d}</span></div>'
        f'<div class="card-t"><h3>{inline(card["titulo"])}</h3>'
        f'<div class="card-meta">{extra_tag}{edital}</div></div>'
        f'<button class="st" type="button" data-card="{cid}" '
        'aria-label="Marcar status de revisão">·</button>'
        "</header>"
    )


def render_card(card, num, i):
    """Ficha de assunto."""
    cid = card.get("id") or slug(card["titulo"])
    partes = [
        f'<section class="card" id="{cid}" style="--i:{i}" '
        f'data-busca="{html.escape(texto_busca(card), quote=True)}">',
        cabecalho_card(card, cid, num),
    ]

    if card.get("fontes"):
        nomes = " · ".join(html.escape(f) for f in card["fontes"])
        partes.append(f'<p class="fonte">{nomes}</p>')

    if card.get("regra"):
        partes.append(
            '<div class="regra"><span class="rot">Regra-chave</span>'
            f'<p>{inline(card["regra"])}</p></div>'
        )

    partes.append(render_blocos(card.get("blocos")))

    ex = card.get("exemplo")
    if ex:
        t = inline(ex["titulo"]) if ex.get("titulo") else "Exemplo prático"
        partes.append(
            f'<div class="bloco ex"><span class="aba-caixa">Caso prático</span>'
            f'<h4 class="ex-t">{t}</h4>'
            f'<p class="caso">{inline(ex.get("caso", ""))}</p>'
            '<div class="sol"><span class="rot rot-ok">Solução</span>'
            f'<p class="resp">{inline(ex.get("solucao", ""))}</p></div></div>'
        )

    partes.append(render_citacoes(card.get("citacoes")))

    if card.get("pegadinhas"):
        linhas = "".join(
            f'<tr><td class="err">{inline(p["errado"])}</td>'
            f'<td class="cer resp">{inline(p["certo"])}</td></tr>'
            for p in card["pegadinhas"]
        )
        partes.append(
            '<div class="bloco peg"><h4 class="rot rot-err">Pegadinhas</h4><div class="tw">'
            "<table><thead><tr><th>O que a banca escreve</th><th>O que é certo</th></tr>"
            f"</thead><tbody>{linhas}</tbody></table></div></div>"
        )

    ponte = card.get("ponte")
    if ponte:
        itens = "".join(f"<li>{inline(i)}</li>" for i in ponte.get("itens", []))
        partes.append(
            f'<div class="bloco ponte"><h4 class="rot">{inline(ponte.get("titulo", "Ponte"))}</h4>'
            f"<ul>{itens}</ul></div>"
        )

    partes.append("</section>")
    return "".join(partes)


def render_critico(card, num, i):
    """Ficha de ponto crítico: armadilha → por que erra → regra → gatilho."""
    cid = card.get("id") or slug(card["titulo"])
    selo = '<span class="selo">ponto crítico</span>'
    partes = [
        f'<section class="card crit" id="{cid}" style="--i:{i}" '
        f'data-busca="{html.escape(texto_busca(card), quote=True)}">',
        cabecalho_card(card, cid, num, selo),
    ]

    if card.get("armadilha"):
        partes.append(
            '<div class="bloco arm"><h4 class="rot rot-err">A armadilha</h4>'
            f'<p>{inline(card["armadilha"])}</p></div>'
        )
    if card.get("porque"):
        partes.append(
            '<div class="bloco"><h4 class="rot">Por que se erra</h4>'
            f'<p>{inline(card["porque"])}</p></div>'
        )
    if card.get("regra"):
        partes.append(
            '<div class="regra regra-ok"><span class="rot rot-ok">A regra</span>'
            f'<p class="resp">{inline(card["regra"])}</p></div>'
        )

    partes.append(render_blocos(card.get("blocos")))
    partes.append(render_citacoes(card.get("citacoes")))

    if card.get("gatilho"):
        partes.append(
            f'<p class="gatilho"><span>Gatilho</span> {inline(card["gatilho"])}</p>'
        )
    if card.get("ficha"):
        partes.append(
            f'<p class="verficha"><a href="#{html.escape(card["ficha"])}" '
            'data-ficha="1">Ver a ficha completa do assunto →</a></p>'
        )

    partes.append("</section>")
    return "".join(partes)


def render_materia(materia, ativa):
    abas = materia["abas"]
    cor = materia.get("cor", COR_PADRAO)

    bot_abas = "".join(
        f'<button class="aba{" on" if i == 0 else ""}{" aba-crit" if a.get("tipo") == "criticos" else ""}" '
        f'type="button" data-aba="{a["id"]}">{inline(a["nome"])}'
        f'<span class="qtd">{sum(len(g.get("cards", [])) for g in a.get("grupos", []))}</span>'
        "</button>"
        for i, a in enumerate(abas)
    )

    paineis = []
    num = 0
    for i, a in enumerate(abas):
        critico = a.get("tipo") == "criticos"
        grupos = []
        for g in a.get("grupos", []):
            cards = []
            for j, c in enumerate(g.get("cards", [])):
                num += 1
                cards.append(
                    render_critico(c, num, j) if critico else render_card(c, num, j)
                )
            nome = f'<h2 class="grupo">{inline(g["nome"])}</h2>' if g.get("nome") else ""
            grupos.append(f'<section class="grupo-bloco">{nome}{"".join(cards)}</section>')
        intro = f'<p class="intro">{inline(a["intro"])}</p>' if a.get("intro") else ""
        paineis.append(
            f'<div class="painel-aba{" on" if i == 0 else ""}{" is-crit" if critico else ""}" '
            f'data-painel="{a["id"]}">{intro}{"".join(grupos)}</div>'
        )

    nota = f'<p class="nota-mat">{inline(materia["nota"])}</p>' if materia.get("nota") else ""
    return (
        f'<div class="painel{" on" if ativa else ""}" data-materia="{materia["id"]}" '
        f'style="--m:{cor}">'
        f'{nota}<nav class="abas">{bot_abas}</nav>{"".join(paineis)}</div>'
    )


def render_cobertura(pendentes):
    if not pendentes:
        return ""
    blocos, total = [], 0
    for pasta, notas in sorted(pendentes.items()):
        total += len(notas)
        itens = "".join(f"<li>{html.escape(n)}</li>" for n in notas)
        blocos.append(f"<div><h4>{html.escape(pasta)}</h4><ul>{itens}</ul></div>")
    return (
        '<details class="cobertura"><summary>Notas do vault ainda sem ficha '
        f'({total})</summary><div class="cob-grid">{"".join(blocos)}</div></details>'
    )


CSS = """
/* ------------------------------------------------------------------ tokens */
:root{
  --papel:#f2ede3; --papel-2:#e8e1d3; --carta:#fbf8f2; --linha:#ddd3bf;
  --tinta:#1f1b16; --tinta-2:#5c5347; --tinta-3:#8c8272;
  --m:#7a5230;                      /* cor da matéria (definida no painel) */
  --selo:#9d2b20; --selo-bg:#f7e6e2;
  --ok:#2f6b42; --ok-bg:#e6f0e6;
  --lei:#324a86; --lei-bg:#e9ecf7;
  --serif:"Fraunces",Georgia,"Times New Roman",serif;
  --sans:"Archivo","Helvetica Neue",Helvetica,sans-serif;
  --mono:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
  --sh:0 1px 1px rgba(31,27,22,.04),0 6px 18px -8px rgba(31,27,22,.18);
  --grao:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='3'/%3E%3C/filter%3E%3Crect width='120' height='120' filter='url(%23n)' opacity='.35'/%3E%3C/svg%3E");
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --papel:#15141a; --papel-2:#1d1b23; --carta:#201e28; --linha:#35313f;
    --tinta:#f0ece4; --tinta-2:#b8b1a6; --tinta-3:#857d73;
    --selo:#f0917f; --selo-bg:#33211e;
    --ok:#8fcfa1; --ok-bg:#1b2c21;
    --lei:#a9b8ee; --lei-bg:#20243a;
    --sh:0 1px 1px rgba(0,0,0,.3),0 8px 24px -10px rgba(0,0,0,.6);
  }
}
:root[data-theme="dark"]{
  --papel:#15141a; --papel-2:#1d1b23; --carta:#201e28; --linha:#35313f;
  --tinta:#f0ece4; --tinta-2:#b8b1a6; --tinta-3:#857d73;
  --selo:#f0917f; --selo-bg:#33211e;
  --ok:#8fcfa1; --ok-bg:#1b2c21;
  --lei:#a9b8ee; --lei-bg:#20243a;
  --sh:0 1px 1px rgba(0,0,0,.3),0 8px 24px -10px rgba(0,0,0,.6);
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%; scroll-behavior:smooth}
body{
  margin:0; background:var(--papel); color:var(--tinta);
  font:16px/1.62 var(--sans); padding-bottom:5rem; position:relative;
  font-feature-settings:"ss01";
}
body::before{
  content:""; position:fixed; inset:0; background-image:var(--grao);
  opacity:.28; pointer-events:none; z-index:0; mix-blend-mode:multiply;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) body::before{mix-blend-mode:screen; opacity:.12}}
:root[data-theme="dark"] body::before{mix-blend-mode:screen; opacity:.12}
.wrap{max-width:1080px; margin:0 auto; padding:0 18px; position:relative; z-index:1}

/* ----------------------------------------------------------------- cabeçalho */
header.top{padding:2.8rem 0 1.4rem; position:relative}
.kicker{
  font:600 .7rem/1 var(--mono); letter-spacing:.22em; text-transform:uppercase;
  color:var(--tinta-3); margin:0 0 .9rem;
}
h1{
  font:600 clamp(2rem,6vw,3.2rem)/1.04 var(--serif); margin:0 0 .5rem;
  letter-spacing:-.02em; font-variation-settings:"SOFT" 30,"WONK" 1;
}
.sub{color:var(--tinta-2); margin:0 0 1.3rem; max-width:56ch; font-size:1.02rem}
.regua{border:0; border-top:3px double var(--linha); margin:0 0 1.1rem}
.chips{display:flex; flex-wrap:wrap; gap:.4rem; align-items:center}
.chip{
  font:500 .74rem/1.5 var(--mono); padding:.22rem .6rem; border:1px solid var(--linha);
  color:var(--tinta-2); background:var(--carta);
}
.chip b{color:var(--tinta); font-weight:600}
.contador{
  border-color:var(--selo); color:var(--selo); background:var(--selo-bg); font-weight:600;
}

/* --------------------------------------------------------------- barra fixa */
.barra{
  position:sticky; top:0; z-index:20; background:var(--papel);
  border-bottom:1px solid var(--linha); margin-bottom:1.6rem; padding-top:.6rem;
}
.barra::after{
  content:""; position:absolute; left:0; right:0; bottom:-6px; height:6px;
  background:linear-gradient(var(--papel),transparent); pointer-events:none;
}
.mats{display:flex; flex-wrap:wrap; gap:.4rem; margin-bottom:.55rem}
.mat{
  --m:var(--tinta-3);
  display:inline-flex; align-items:baseline; gap:.45rem; cursor:pointer;
  border:1px solid var(--linha); border-bottom:3px solid var(--m);
  background:var(--carta); color:var(--tinta-2);
  padding:.5rem .9rem .42rem; font:600 .95rem/1 var(--sans); font-family:var(--serif);
  transition:background .15s,color .15s,transform .15s;
}
.mat:hover{transform:translateY(-1px)}
.mat.on{background:var(--m); color:#fff; border-color:var(--m)}
:root[data-theme="dark"] .mat.on{color:#16151c}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) .mat.on{color:#16151c}}
.mat .n{font:500 .72rem/1 var(--mono); opacity:.75}
.ferramentas{display:flex; flex-wrap:wrap; gap:.45rem; align-items:center; padding-bottom:.6rem}
#busca{
  flex:1 1 230px; min-width:0; padding:.52rem .8rem; border:1px solid var(--linha);
  background:var(--carta); color:var(--tinta); font:400 .9rem/1.3 var(--sans);
}
#busca:focus{outline:2px solid var(--m); outline-offset:1px}
.tgl{
  cursor:pointer; border:1px solid var(--linha); background:var(--carta); color:var(--tinta-2);
  padding:.52rem .75rem; font:500 .8rem/1.3 var(--mono); white-space:nowrap;
}
.tgl.on{background:var(--selo); color:#fff; border-color:var(--selo)}
.contagem{font:.74rem/1 var(--mono); color:var(--tinta-3); margin-left:auto}

/* -------------------------------------------------------------------- abas */
.painel{display:none} .painel.on{display:block; animation:surge .35s ease both}
.nota-mat{font-size:.9rem; color:var(--tinta-2); margin:0 0 1.1rem; max-width:68ch}
.abas{display:flex; flex-wrap:wrap; gap:.35rem; margin-bottom:1.6rem; border-bottom:1px solid var(--linha)}
.aba{
  cursor:pointer; border:1px solid transparent; border-bottom:none; background:transparent;
  color:var(--tinta-3); padding:.45rem .7rem; font:500 .85rem/1.3 var(--sans);
  display:inline-flex; gap:.4rem; align-items:center; margin-bottom:-1px;
}
.aba:hover{color:var(--tinta)}
.aba.on{
  background:var(--carta); border-color:var(--linha); color:var(--tinta);
  font-weight:600; box-shadow:0 -2px 0 var(--m) inset;
}
.aba .qtd{font:500 .68rem/1 var(--mono); color:var(--tinta-3)}
.aba-crit{color:var(--selo)} .aba-crit.on{box-shadow:0 -2px 0 var(--selo) inset}
.painel-aba{display:none} .painel-aba.on{display:block}
.intro{
  background:var(--selo-bg); border-left:3px solid var(--selo); padding:.85rem 1rem;
  margin:0 0 1.6rem; font-size:.92rem; color:var(--tinta-2);
}

/* ------------------------------------------------------------------- grupos */
.grupo{
  font:600 .74rem/1 var(--mono); letter-spacing:.16em; text-transform:uppercase;
  color:var(--tinta-3); margin:2.4rem 0 1rem; display:flex; align-items:center; gap:.8rem;
}
.grupo::after{content:""; flex:1; height:1px; background:var(--linha)}
.grupo-bloco:first-child .grupo{margin-top:0}

/* -------------------------------------------------------------------- carta */
.card{
  background:var(--carta); border:1px solid var(--linha); border-left:4px solid var(--m);
  box-shadow:var(--sh); padding:1.3rem 1.4rem 1.5rem; margin-bottom:1.1rem;
  scroll-margin-top:8.5rem; position:relative;
  animation:surge .4s ease both; animation-delay:calc(var(--i,0)*45ms);
}
.card.oculto{display:none}
@keyframes surge{from{opacity:0; transform:translateY(8px)} to{opacity:1; transform:none}}
@media (prefers-reduced-motion:reduce){
  .card,.painel.on{animation:none}
  html{scroll-behavior:auto}
}
.card-h{display:grid; grid-template-columns:auto 1fr auto; gap:.85rem; align-items:start}
.card-id{padding-top:.15rem}
.prot{
  font:600 .7rem/1 var(--mono); color:var(--m); border:1px solid var(--m);
  padding:.26rem .32rem; display:inline-block; opacity:.85;
}
.card-t h3{
  margin:0; font:600 1.22rem/1.25 var(--serif); letter-spacing:-.01em;
  font-variation-settings:"SOFT" 20;
}
.card-meta{display:flex; flex-wrap:wrap; gap:.35rem; margin-top:.4rem}
.tag{
  font:500 .68rem/1.4 var(--mono); padding:.1rem .4rem; border:1px solid var(--linha);
  color:var(--tinta-3);
}
.selo{
  font:700 .62rem/1.4 var(--mono); letter-spacing:.14em; text-transform:uppercase;
  padding:.16rem .45rem; color:var(--selo); border:1.5px solid var(--selo);
  background:var(--selo-bg); transform:rotate(-1.4deg);
}
.st{
  width:28px; height:28px; border-radius:50%; cursor:pointer; flex-shrink:0;
  border:1px solid var(--linha); background:transparent; color:var(--tinta-3);
  font:600 .8rem/1 var(--mono);
}
.st[data-v="ok"]{background:var(--ok-bg); color:var(--ok); border-color:var(--ok)}
.st[data-v="rev"]{background:var(--selo-bg); color:var(--selo); border-color:var(--selo)}
.fonte{font:.72rem/1.5 var(--mono); color:var(--tinta-3); margin:.7rem 0 0}

/* --------------------------------------------------------- caixas didáticas */
.rot{
  display:block; font:600 .68rem/1 var(--mono); letter-spacing:.15em;
  text-transform:uppercase; color:var(--tinta-3); margin:0 0 .5rem;
}
.rot-err{color:var(--selo)} .rot-ok{color:var(--ok)}
.regra{
  margin:1.1rem 0 0; padding:.9rem 1rem; background:var(--papel-2);
  border-left:3px double var(--m);
}
.regra .rot{color:var(--m)}
.regra p{margin:0; font:1.02rem/1.55 var(--serif)}
.regra-ok{border-left-color:var(--ok); background:var(--ok-bg)}
.bloco{margin-top:1.3rem}
.tw{overflow-x:auto; -webkit-overflow-scrolling:touch; border:1px solid var(--linha)}
table{border-collapse:collapse; width:100%; font-size:.86rem; min-width:430px; background:var(--carta)}
th,td{padding:.5rem .65rem; text-align:left; vertical-align:top; border-bottom:1px solid var(--linha)}
th{
  background:var(--papel-2); font:600 .68rem/1.3 var(--mono); letter-spacing:.08em;
  text-transform:uppercase; color:var(--tinta-2);
}
tbody tr:nth-child(even) td{background:color-mix(in srgb,var(--papel-2) 45%,transparent)}
tr:last-child td{border-bottom:none}
.lst{margin:0; padding-left:1.15rem} .lst li{margin-bottom:.4rem}
.tl{margin:0; padding:0; list-style:none; counter-reset:t}
.tl li{
  counter-increment:t; position:relative; padding:0 0 .85rem 2rem;
  border-left:1px solid var(--linha); margin-left:.75rem;
}
.tl li:last-child{border-left-color:transparent; padding-bottom:0}
.tl li::before{
  content:counter(t,decimal-leading-zero); position:absolute; left:-.78rem; top:-.1rem;
  width:1.55rem; height:1.55rem; background:var(--m); color:#fff;
  font:600 .62rem/1 var(--mono); display:flex; align-items:center; justify-content:center;
  border-radius:50%;
}
.ex{background:var(--papel-2); padding:1.5rem 1rem 1rem; position:relative; border:1px solid var(--linha)}
.aba-caixa{
  position:absolute; top:-1px; left:-1px; background:var(--m); color:#fff;
  font:600 .62rem/1 var(--mono); letter-spacing:.14em; text-transform:uppercase;
  padding:.3rem .55rem;
}
.ex-t{margin:.2rem 0 .5rem; font:600 .98rem/1.35 var(--serif)}
.caso{margin:0}
.sol{margin-top:.9rem; padding-top:.75rem; border-top:1px dashed var(--linha)}
.sol p{margin:0}
.cit{list-style:none; margin:0; padding:0}
.cit li{
  padding:.55rem .75rem; border-left:2px solid var(--lei); background:var(--lei-bg);
  margin-bottom:.4rem; font-size:.88rem;
}
.disp{font:600 .8rem/1.4 var(--mono); color:var(--lei); margin-right:.5rem}
.sel{
  font:500 .6rem/1.4 var(--mono); padding:.02rem .28rem; text-transform:uppercase;
  letter-spacing:.06em; margin-right:.4rem; vertical-align:1px;
}
.sel-lit{background:var(--lei); color:var(--carta)}
.sel-sin{border:1px solid var(--tinta-3); color:var(--tinta-3)}
.cit .txt{color:var(--tinta-2)}
.peg td.err{color:var(--selo); width:47%}
.peg td.cer{color:var(--ok)}
.peg td.err::before{content:"✗"; font-family:var(--mono); margin-right:.35rem}
.peg td.cer::before{content:"✓"; font-family:var(--mono); margin-right:.35rem}
.ponte{
  background:var(--ok-bg); padding:.95rem 1rem; border:1px dashed var(--ok);
}
.ponte .rot{color:var(--ok)}
.ponte ul{margin:0; padding-left:1.15rem} .ponte li{margin-bottom:.45rem}
.ponte li:last-child{margin-bottom:0}

/* ---------------------------------------------------------- ponto crítico */
.crit{border-left-color:var(--selo)}
.crit .prot{color:var(--selo); border-color:var(--selo)}
.crit .tl li::before,.crit .aba-caixa{background:var(--selo)}
.arm{
  background:var(--selo-bg); border-left:3px solid var(--selo); padding:.85rem 1rem;
}
.arm p{margin:0; font-style:italic}
.gatilho{
  margin:1.3rem 0 0; padding:.7rem .9rem; border:1px solid var(--linha);
  background:var(--papel-2); font:1rem/1.5 var(--serif);
}
.gatilho span{
  font:600 .65rem/1 var(--mono); letter-spacing:.14em; text-transform:uppercase;
  color:var(--tinta-3); display:block; margin-bottom:.3rem;
}
.verficha{margin:1rem 0 0; font-size:.85rem}
.verficha a{color:var(--m); text-decoration:none; border-bottom:1px solid var(--linha)}
.verficha a:hover{border-color:var(--m)}
.card.alvo{outline:2px solid var(--m); outline-offset:3px}

/* ------------------------------------------------------------ modo revisão */
body.revisao .resp{
  filter:blur(6px); cursor:pointer; user-select:none; transition:filter .2s;
}
body.revisao .resp:hover{filter:blur(4px)}
body.revisao .resp.rev{filter:none; user-select:auto}
body.revisao .sol::after{
  content:"toque para revelar"; display:block; margin-top:.4rem;
  font:.68rem/1 var(--mono); color:var(--tinta-3);
}
body.revisao .sol:has(.rev)::after{content:""}

.vazio{padding:3rem 0; color:var(--tinta-3); text-align:center; display:none; font-family:var(--serif)}
.vazio.on{display:block}
.cobertura{margin:3rem 0 1rem; font-size:.85rem; color:var(--tinta-2)}
.cobertura summary{cursor:pointer; font:600 .72rem/1 var(--mono); letter-spacing:.12em; text-transform:uppercase; color:var(--tinta-3)}
.cob-grid{display:grid; gap:1.2rem; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); margin-top:1rem}
.cob-grid h4{margin:0 0 .35rem; font:600 .7rem/1 var(--mono); color:var(--tinta-3); text-transform:uppercase; letter-spacing:.08em}
.cob-grid ul{margin:0; padding-left:1.1rem} .cob-grid li{margin-bottom:.2rem}
footer{
  margin-top:3rem; padding-top:1.4rem; border-top:3px double var(--linha);
  font:.76rem/1.6 var(--mono); color:var(--tinta-3);
}
footer p{margin:.35rem 0}

@media (max-width:640px){
  body{font-size:15.5px}
  .wrap{padding:0 14px}
  .card{padding:1.05rem 1rem 1.2rem}
  .card-h{grid-template-columns:auto 1fr; row-gap:.5rem}
  .st{grid-column:1; justify-self:start}
  .card-t{grid-column:2}
  .contagem{margin-left:0; width:100%}
  .regra p{font-size:.98rem}
}
@media print{
  .barra,.st,.cobertura,body::before{display:none!important}
  .painel,.painel-aba{display:block!important}
  .card{break-inside:avoid; box-shadow:none; animation:none}
  body{background:#fff; color:#000}
}
"""

JS = """
(function(){
  var d=document, b=d.body;
  function q(s,r){return Array.prototype.slice.call((r||d).querySelectorAll(s));}
  function ls(fn,alt){try{return fn();}catch(e){return alt;}}
  function dobrar(s){
    return (s||'').trim().toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'');
  }

  q('.mat').forEach(function(bt){
    bt.addEventListener('click',function(){
      q('.mat').forEach(function(x){x.classList.toggle('on',x===bt);});
      q('.painel').forEach(function(p){p.classList.toggle('on',p.dataset.materia===bt.dataset.mat);});
      filtrar(); window.scrollTo({top:0,behavior:'smooth'});
    });
  });

  q('.aba').forEach(function(bt){
    bt.addEventListener('click',function(){
      var painel=bt.closest('.painel');
      q('.aba',painel).forEach(function(x){x.classList.toggle('on',x===bt);});
      q('.painel-aba',painel).forEach(function(p){p.classList.toggle('on',p.dataset.painel===bt.dataset.aba);});
      filtrar();
    });
  });

  var busca=d.getElementById('busca'), vazio=d.getElementById('vazio'), cont=d.getElementById('contagem');
  function filtrar(){
    var t=dobrar(busca.value), n=0;
    q('.card').forEach(function(c){
      c.classList.toggle('oculto', !!t && c.dataset.busca.indexOf(t)===-1);
    });
    if(t){
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

  // link de ponto crítico → ficha do assunto (abre a matéria e a aba certas)
  d.addEventListener('click',function(e){
    var a=e.target.closest?e.target.closest('a[data-ficha]'):null;
    if(!a) return;
    var alvo=d.querySelector(a.getAttribute('href'));
    if(!alvo) return;
    e.preventDefault();
    var painel=alvo.closest('.painel'), pAba=alvo.closest('.painel-aba');
    var mat=d.querySelector('.mat[data-mat="'+painel.dataset.materia+'"]');
    if(mat&&!mat.classList.contains('on')) mat.click();
    var aba=painel.querySelector('.aba[data-aba="'+pAba.dataset.painel+'"]');
    if(aba&&!aba.classList.contains('on')) aba.click();
    alvo.scrollIntoView({block:'start'});
    alvo.classList.add('alvo');
    setTimeout(function(){alvo.classList.remove('alvo');},1800);
  });

  // modo revisão: respostas embaçadas até o toque
  var mr=d.getElementById('mrev');
  function aplicarRevisao(on){
    b.classList.toggle('revisao',on);
    mr.classList.toggle('on',on);
    mr.setAttribute('aria-pressed',on?'true':'false');
    q('.resp').forEach(function(x){x.classList.remove('rev');});
    ls(function(){localStorage.setItem('tjrs-revisao',on?'1':'0');});
  }
  mr.addEventListener('click',function(){aplicarRevisao(!b.classList.contains('revisao'));});
  d.addEventListener('click',function(e){
    if(!b.classList.contains('revisao')) return;
    var alvo=e.target.closest?e.target.closest('.resp'):null;
    if(alvo) alvo.classList.add('rev');
  });

  var tt=d.getElementById('tema');
  tt.addEventListener('click',function(){
    var escuro=d.documentElement.getAttribute('data-theme')==='dark'
      || (!d.documentElement.getAttribute('data-theme') && matchMedia('(prefers-color-scheme:dark)').matches);
    var novo=escuro?'light':'dark';
    d.documentElement.setAttribute('data-theme',novo);
    ls(function(){localStorage.setItem('tjrs-tema',novo);});
  });

  var ciclo={'':'ok','ok':'rev','rev':''}, rot={'':'·','ok':'✓','rev':'↻'};
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

  var tema=ls(function(){return localStorage.getItem('tjrs-tema');},null);
  if(tema) d.documentElement.setAttribute('data-theme',tema);
  if(ls(function(){return localStorage.getItem('tjrs-revisao');},null)==='1') aplicarRevisao(true);
  filtrar();
})();
"""


def render(meta, materias, pendentes):
    total = sum(contar_cards(m) for m in materias)
    criticos = sum(contar_cards(m, "criticos") for m in materias)
    dias = dias_para(meta.get("prova"))

    chips = [f'<span class="chip"><b>{total}</b> fichas</span>']
    if criticos:
        chips.append(f'<span class="chip"><b>{criticos}</b> pontos críticos</span>')
    if dias is not None:
        chips.append(f'<span class="chip contador">faltam <b>{dias}</b> dias</span>')
    for m in materias:
        chips.append(
            f'<span class="chip">{html.escape(m["nome"])} · <b>{contar_cards(m)}</b>'
            f' · {html.escape(m.get("peso", ""))}</span>'
        )

    bot_mats = "".join(
        f'<button class="mat{" on" if i == 0 else ""}" type="button" data-mat="{m["id"]}" '
        f'style="--m:{m.get("cor", COR_PADRAO)}">{inline(m["nome"])}'
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
<meta name="theme-color" content="#f2ede3">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E%F0%9F%93%9C%3C/text%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700&family=Archivo:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header class="top">
  <p class="kicker">IV Concurso de Cartórios · TJRS · banca FGV</p>
  <h1>{inline(meta.get("titulo", "Resumos"))}</h1>
  <p class="sub">{inline(meta.get("subtitulo", ""))}</p>
  <hr class="regua">
  <div class="chips">{"".join(chips)}</div>
</header>

<div class="barra">
  <nav class="mats">{bot_mats}</nav>
  <div class="ferramentas">
    <input id="busca" type="search" placeholder="Buscar assunto, artigo, pegadinha…  ( / )" autocomplete="off">
    <button id="mrev" class="tgl" type="button" aria-pressed="false" title="Embaça as respostas até o toque">modo revisão</button>
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
  <p>FONTE · {inline(meta.get("fonte", ""))}</p>
  <p>{inline(meta.get("rodape", ""))}</p>
  <p>Gerado em {date.today().strftime("%d/%m/%Y")} por <code>gerar_resumos.py</code> ·
     conteúdo em <code>resumos/dados/*.json</code> · o HTML é regenerável.</p>
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

    # links "ver a ficha completa" que apontam para ficha inexistente: avisa e não gera o link
    ids = {c.get("id") for m in materias for _a, c in cards_da(m)}
    for m in materias:
        for _a, c in cards_da(m):
            if c.get("ficha") and c["ficha"] not in ids:
                print(f"   ⚠ {c['id']}: ficha '{c['ficha']}' não existe — link omitido")
                c.pop("ficha")

    saida = Path(args.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(render(meta, materias, pendentes), encoding="utf-8")

    total = sum(contar_cards(m) for m in materias)
    print(f"✔ {saida}  —  {total} fichas em {len(materias)} matérias")
    for m in materias:
        crit = contar_cards(m, "criticos")
        extra = f" · {crit} pontos críticos" if crit else ""
        print(f"   {m['nome']}: {contar_cards(m)} fichas{extra}")
    if pendentes:
        n = sum(len(v) for v in pendentes.values())
        print(f"   ⚠ {n} notas do vault ainda sem ficha (listadas no rodapé do HTML)")
    elif pendentes == {}:
        print("   ✔ todas as notas do vault têm ficha")
    elif pendentes is None and not args.sem_cobertura:
        print("   ⚠ vault não encontrado — cobertura não verificada")


if __name__ == "__main__":
    main()
