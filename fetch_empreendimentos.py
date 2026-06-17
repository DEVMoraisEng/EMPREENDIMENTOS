"""
fetch_empreendimentos.py
Morais Engenharia · Site de Empreendimentos
Busca dados do banco Notion "Empreendimentos" e gera data_emp.json
"""
import os
import json
import requests
from datetime import datetime

NOTION_TOKEN = os.environ.get("NOTION_TOKEN_EMP", "")
NOTION_DB    = os.environ.get("NOTION_DB_EMP", "")

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}


def get_texto(prop):
    """Extrai texto de propriedade rich_text ou title."""
    if not prop:
        return ""
    t = prop.get("type", "")
    if t == "title":
        items = prop.get("title", [])
    elif t == "rich_text":
        items = prop.get("rich_text", [])
    else:
        return ""
    return "".join(i.get("plain_text", "") for i in items).strip()


def get_select(prop):
    """Extrai valor de propriedade select."""
    if not prop:
        return ""
    s = prop.get("select")
    return s.get("name", "") if s else ""


def get_numero(prop):
    """Extrai número de propriedade number."""
    if not prop:
        return None
    return prop.get("number")


def get_data(prop):
    """Extrai data de propriedade date."""
    if not prop:
        return ""
    d = prop.get("date")
    if not d:
        return ""
    return d.get("start", "")


def buscar_paginas():
    """Busca todas as páginas do banco Empreendimentos."""
    # ── Diagnóstico ──────────────────────────────────────────────────────────
    print(f"NOTION_TOKEN_EMP: {'OK (' + str(len(NOTION_TOKEN)) + ' chars)' if NOTION_TOKEN else 'NAO DEFINIDO <- ERRO'}")
    print(f"NOTION_DB_EMP:    {NOTION_DB if NOTION_DB else 'NAO DEFINIDO <- ERRO'}")

    # Remove prefixo ntn_ caso venha errado no secret
    db_id = NOTION_DB
    if db_id.startswith("ntn_"):
        db_id = db_id[4:]
        print(f"AVISO: ID tinha prefixo ntn_ removido automaticamente. Usando: {db_id}")

    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    print(f"URL: {url}")

    resultados = []
    has_more = True
    cursor = None

    while has_more:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        resp = requests.post(url, headers=HEADERS, json=body, timeout=30)
        print(f"  HTTP {resp.status_code}")
        if resp.status_code != 200:
            print(f"  ERRO: {resp.text[:500]}")
            break
        data = resp.json()
        lote = data.get("results", [])
        resultados.extend(lote)
        print(f"  Paginas neste lote: {len(lote)}")
        has_more = data.get("has_more", False)
        cursor = data.get("next_cursor")

    print(f"Total de paginas brutas: {len(resultados)}")

    # Diagnóstico: mostra propriedades da 1ª página para conferir nomes
    if resultados:
        print("\nPropriedades da 1a pagina (para conferir nomes):")
        for k, v in resultados[0].get("properties", {}).items():
            print(f"  '{k}' -> tipo: {v.get('type','?')}")
    else:
        print("AVISO: Nenhuma pagina retornada.")
        print("Verifique: 1) integração tem acesso ao banco  2) ID do banco correto (sem prefixo ntn_)")

    return resultados


def processar_pagina(page):
    """Converte uma página Notion para dict do data_emp.json."""
    props = page.get("properties", {})

    # Nome do empreendimento (título da página — fallback automático)
    nome = get_texto(props.get("Nome") or props.get("Name") or props.get("NOME") or {})
    if not nome:
        for v in props.values():
            if v.get("type") == "title":
                nome = get_texto(v)
                break

    # Localização
    setor       = get_texto(props.get("SETOR") or props.get("Setor") or {})
    cidade      = get_texto(props.get("CIDADE") or props.get("Cidade") or {})
    rua         = get_texto(props.get("RUA") or props.get("Rua") or {})
    complemento = get_texto(props.get("COMPLEMENTO") or props.get("Complemento") or {})
    cep         = get_texto(props.get("CEP") or {})

    # Status da obra (select SIM/NÃO)
    def sim_nao(campo):
        v = get_select(props.get(campo) or {})
        return v.upper() == "SIM"

    processo_iniciado   = sim_nao("PROCESSO INICIADO")
    aprovacao_iniciada  = sim_nao("APROVACAO INICIADA") or sim_nao("APROVAÇÃO INICIADA")
    aprovacao_concluida = sim_nao("APROVACAO CONCLUIDA") or sim_nao("APROVAÇÃO CONCLUÍDA")
    obra_iniciada       = sim_nao("OBRA INICIADA")
    obra_finalizada     = sim_nao("OBRA FINALIZADA") or sim_nao("OBRA FINALZIADA")

    # Datas
    inicio_processo   = get_data(props.get("INICIO DO PROCESSO")  or props.get("INÍCIO DO PROCESSO")  or {})
    inicio_aprovacao  = get_data(props.get("INICIO DA APROVACAO") or props.get("INÍCIO DA APROVAÇÃO") or {})
    termino_aprovacao = get_data(props.get("TERMINO DA APROVACAO")or props.get("TÉRMINO DA APROVAÇÃO") or {})
    inicio_obras      = get_data(props.get("INICIO DAS OBRAS")    or props.get("INÍCIO DAS OBRAS")    or {})
    termino_obras     = get_data(props.get("TERMINO DAS OBRAS")   or props.get("TÉRMINO DAS OBRAS")   or {})

    # Campos para preencher FRE
    proponente          = get_texto(props.get("PROPONENTE") or {})
    doc_proponente      = get_texto(props.get("DOC. PROPONENTE") or {})
    construtora         = get_texto(props.get("CONSTRUTORA") or {})
    doc_construtora     = get_texto(props.get("DOC. CONSTRUTORA") or {})
    responsavel_tecnico = get_texto(props.get("RESPONSAVEL TECNICO") or props.get("RESPONSÁVEL TÉCNICO") or {})
    crea                = get_texto(props.get("CREA") or {})
    doc_responsavel     = get_texto(props.get("DOC. RESPONSAVEL") or props.get("DOC. RESPONSÁVEL") or {})
    incorporador        = get_texto(props.get("INCORPORADOR") or {})
    doc_incorporador    = get_texto(props.get("DOC. INCORPORADOR") or {})
    tel_contato         = get_texto(props.get("TEL. CONTATO") or props.get("TEL CONTATO") or {})
    email               = get_texto(props.get("EMAIL") or {})

    n_unidades_v     = get_numero(props.get("N DE UNIDADES") or props.get("Nº DE UNIDADES") or props.get("N° DE UNIDADES") or {})
    n_unidades       = int(n_unidades_v) if n_unidades_v is not None else ""
    prazo_v          = get_numero(props.get("PRAZO PREVISTO") or {})
    prazo_previsto   = int(prazo_v) if prazo_v is not None else ""
    area_lote_v      = get_numero(props.get("AREA DO LOTE") or props.get("ÁREA DO LOTE") or {})
    area_lote        = area_lote_v if area_lote_v is not None else ""
    area_equiv_v     = get_numero(props.get("AREA EQUIVALENTE") or props.get("ÁREA EQUIVALENTE") or {})
    area_equivalente = area_equiv_v if area_equiv_v is not None else ""

    # Status calculado para o card
    if obra_finalizada:
        status_label = "OBRA FINALIZADA";  status_cor = "finalizada"
    elif obra_iniciada:
        status_label = "OBRA INICIADA";    status_cor = "obra"
    elif aprovacao_concluida:
        status_label = "APROVAÇÃO CONCLUÍDA"; status_cor = "aprovada"
    elif aprovacao_iniciada:
        status_label = "APROVAÇÃO INICIADA";  status_cor = "aprovando"
    elif processo_iniciado:
        status_label = "PROCESSO INICIADO";   status_cor = "processo"
    else:
        status_label = "NÃO INICIADO";     status_cor = "pendente"

    return {
        "id":                    page["id"],
        "nome":                  nome,
        "setor":                 setor,
        "cidade":                cidade,
        "rua":                   rua,
        "complemento":           complemento,
        "cep":                   cep,
        "status_label":          status_label,
        "status_cor":            status_cor,
        "processo_iniciado":     processo_iniciado,
        "aprovacao_iniciada":    aprovacao_iniciada,
        "aprovacao_concluida":   aprovacao_concluida,
        "obra_iniciada":         obra_iniciada,
        "obra_finalizada":       obra_finalizada,
        "inicio_processo":       inicio_processo,
        "inicio_aprovacao":      inicio_aprovacao,
        "termino_aprovacao":     termino_aprovacao,
        "inicio_obras":          inicio_obras,
        "termino_obras":         termino_obras,
        "proponente":            proponente,
        "doc_proponente":        doc_proponente,
        "construtora":           construtora,
        "doc_construtora":       doc_construtora,
        "responsavel_tecnico":   responsavel_tecnico,
        "crea":                  crea,
        "doc_responsavel":       doc_responsavel,
        "incorporador":          incorporador,
        "doc_incorporador":      doc_incorporador,
        "tel_contato":           tel_contato,
        "email":                 email,
        "n_unidades":            n_unidades,
        "prazo_previsto":        prazo_previsto,
        "area_lote":             area_lote,
        "area_equivalente":      area_equivalente,
    }


def main():
    print("=" * 60)
    print("fetch_empreendimentos.py — Morais Engenharia")
    print("=" * 60)

    paginas = buscar_paginas()

    empreendimentos = []
    for p in paginas:
        try:
            emp = processar_pagina(p)
            if emp["nome"]:
                empreendimentos.append(emp)
                print(f"  OK: {emp['nome']} — {emp['status_label']}")
            else:
                print(f"  IGNORADO: página sem nome (id={p.get('id','?')})")
        except Exception as ex:
            print(f"  ERRO ao processar {p.get('id','?')}: {ex}")

    empreendimentos.sort(key=lambda x: x["nome"].lower())

    saida = {
        "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "empreendimentos": empreendimentos,
    }

    with open("data_emp.json", "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"data_emp.json gerado: {len(empreendimentos)} empreendimento(s)")
    print("=" * 60)


if __name__ == "__main__":
    main()
