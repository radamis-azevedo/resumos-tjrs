# Resumos TJRS 2026

Fichas de estudo para o **IV Concurso de Cartórios do TJRS** (banca FGV) — matéria → assunto,
com regra-chave, exemplo prático, base legal e a ponte para o Direito Notarial e Registral.

**Página:** https://radamis-azevedo.github.io/resumos-tjrs/

## Como funciona

O HTML é **gerado**, não editado à mão. O conteúdo vive em JSON; o script cuida da apresentação.

```
resumos/dados/00-meta.json      título, subtítulo, data da prova, rodapé
resumos/dados/01-civil.json     Direito Civil
resumos/dados/02-dnr-ri.json    DNR → Registro de Imóveis
.claude/scripts/gerar_resumos.py
docs/index.html                 página publicada (não editar)
```

Para regenerar depois de mexer no conteúdo:

```bash
python3 .claude/scripts/gerar_resumos.py
```

Sem dependências — só Python 3 da própria máquina.

## Acrescentar uma matéria ou especialidade

Crie `resumos/dados/NN-<id>.json` no formato:

```json
{
  "materia": { "id": "dnr", "nome": "Direito Notarial e Registral", "icone": "🏛️", "peso": "28 questões (28%)", "ordem": 2 },
  "abas": [ { "id": "tn", "nome": "Tabelionato de Notas", "grupos": [ { "nome": "…", "cards": [ … ] } ] } ]
}
```

Arquivos com o **mesmo `materia.id`** são fundidos e as abas concatenadas na ordem dos nomes de
arquivo — é assim que TN, RCPN, TP e RTD entram no bloco de DNR sem tocar no que já existe.

Campos de uma ficha: `id`, `titulo`, `edital`, `fontes[]`, `regra`, `blocos[]`
(`tabela` | `lista` | `timeline`), `exemplo{titulo,caso,solucao}`,
`citacoes[{ref,texto,literal}]`, `pegadinhas[{errado,certo}]`, `ponte{titulo,itens[]}`.
Os textos aceitam `**negrito**`, `*itálico*` e `` `código` ``.

O script também informa, no terminal e no rodapé da página, quais notas do vault ainda não
viraram ficha. Para pular essa checagem: `--sem-cobertura`.

## Recursos da página

Busca global (tecla `/`, ignora acento) · **modo revisão** que esconde as soluções e as respostas
das pegadinhas · marcador *sei / revisar* por ficha (guardado no navegador) · tema claro/escuro ·
layout de celular · CSS de impressão.

## Aviso

Material de estudo pessoal, montado a partir de notas próprias. As citações marcadas **síntese**
são paráfrase, não texto literal do dispositivo — confira sempre na fonte oficial antes de usar.
Não é orientação jurídica.
