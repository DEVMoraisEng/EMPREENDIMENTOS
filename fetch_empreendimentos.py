"""
fetch_empreendimentos.py
Morais Engenharia · Site de Empreendimentos
Busca dados do Notion e gera data_emp.json + FREs preenchidas por empreendimento
"""
import os, json, requests, shutil
from datetime import datetime, date

NOTION_TOKEN = os.environ.get("NOTION_TOKEN_EMP", "")
NOTION_DB    = os.environ.get("NOTION_DB_EMP", "")

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

# ── Helpers de propriedades Notion ───────────────────────────────────────────

def get_texto(prop):
    if not prop: return ""
    t = prop.get("type", "")
    if t == "title":   items = prop.get("title", [])
    elif t == "rich_text": items = prop.get("rich_text", [])
    else: return ""
    return "".join(i.get("plain_text", "") for i in items).strip()

def get_select(prop):
    if not prop: return ""
    s = prop.get("select")
    return s.get("name", "").strip() if s else ""

def get_numero(prop):
    if not prop: return None
    return prop.get("number")

def get_data(prop):
    if not prop: return ""
    d = prop.get("date")
    return d.get("start", "") if d else ""

def sim_nao(props, *nomes):
    """Testa campo select SIM/NÃO com múltiplos nomes alternativos."""
    for n in nomes:
        v = get_select(props.get(n) or {})
        if v.upper() in ("SIM", "S", "YES", "TRUE"): return True
        if v.upper() in ("NÃO", "NAO", "N", "NO", "FALSE"): return False
    return False

def get_prop(props, *nomes):
    """Retorna primeira propriedade encontrada dentre os nomes."""
    for n in nomes:
        v = props.get(n)
        if v is not None: return v
    return {}

# ── Busca Notion ─────────────────────────────────────────────────────────────

def buscar_paginas():
    print(f"TOKEN: {'OK (' + str(len(NOTION_TOKEN)) + ' chars)' if NOTION_TOKEN else 'AUSENTE'}")

    db_id = NOTION_DB.replace("ntn_", "", 1) if NOTION_DB.startswith("ntn_") else NOTION_DB
    print(f"DB_ID: {db_id}")

    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    resultados, has_more, cursor = [], True, None

    while has_more:
        body = {"page_size": 100}
        if cursor: body["start_cursor"] = cursor
        resp = requests.post(url, headers=HEADERS, json=body, timeout=30)
        print(f"  HTTP {resp.status_code}")
        if resp.status_code != 200:
            print(f"  ERRO: {resp.text[:500]}")
            break
        data = resp.json()
        lote = data.get("results", [])
        resultados.extend(lote)
        has_more = data.get("has_more", False)
        cursor   = data.get("next_cursor")

    print(f"Total: {len(resultados)} páginas")

    # Mostra nomes e valores dos campos de status da 1ª página
    if resultados:
        print("\n=== Propriedades da 1ª página ===")
        for k, v in resultados[0].get("properties", {}).items():
            tipo = v.get("type", "?")
            if tipo == "select":
                val = get_select(v)
                print(f"  SELECT  '{k}' = '{val}'")
            elif tipo == "title":
                print(f"  TITLE   '{k}' = '{get_texto(v)}'")
            elif tipo == "rich_text":
                print(f"  TEXT    '{k}' = '{get_texto(v)}'")
            elif tipo == "number":
                print(f"  NUMBER  '{k}' = {get_numero(v)}")
            elif tipo == "date":
                print(f"  DATE    '{k}' = {get_data(v)}")
            else:
                print(f"  {tipo.upper():8} '{k}'")

    return resultados

# ── Processar página ─────────────────────────────────────────────────────────

def processar_pagina(page):
    props = page.get("properties", {})

    # Nome (título — fallback automático)
    nome = ""
    for v in props.values():
        if v.get("type") == "title":
            nome = get_texto(v); break

    setor       = get_texto(get_prop(props, "SETOR", "Setor", "setor"))
    cidade      = get_texto(get_prop(props, "CIDADE", "Cidade", "cidade"))
    rua         = get_texto(get_prop(props, "RUA", "Rua", "rua", "ENDEREÇO", "Endereço"))
    complemento = get_texto(get_prop(props, "COMPLEMENTO", "Complemento"))
    cep         = get_texto(get_prop(props, "CEP", "Cep", "cep"))

    # Status — aceita variações de nome e acento
    proc  = sim_nao(props, "PROCESSO INICIADO", "PROCESSO INCIADO", "Processo Iniciado")
    apri  = sim_nao(props, "APROVAÇÃO INICIADA", "APROVACAO INICIADA", "Aprovação Iniciada")
    aprc  = sim_nao(props, "APROVAÇÃO CONCLUÍDA", "APROVACAO CONCLUIDA", "Aprovação Concluída")
    obra  = sim_nao(props, "OBRA INICIADA", "OBRA INCIADA", "Obra Iniciada")
    obraf = sim_nao(props, "OBRA FINALIZADA", "OBRA FINALZIADA", "Obra Finalizada")

    # Datas
    ini_proc  = get_data(get_prop(props, "INÍCIO DO PROCESSO", "INICIO DO PROCESSO", "Início do Processo"))
    ini_apro  = get_data(get_prop(props, "INÍCIO DA APROVAÇÃO", "INICIO DA APROVACAO", "Início da Aprovação"))
    ter_apro  = get_data(get_prop(props, "TÉRMINO DA APROVAÇÃO", "TERMINO DA APROVACAO"))
    ini_obra  = get_data(get_prop(props, "INÍCIO DAS OBRAS", "INICIO DAS OBRAS", "Início das Obras"))
    ter_obra  = get_data(get_prop(props, "TÉRMINO DAS OBRAS", "TERMINO DAS OBRAS"))

    # Campos FRE
    proponente     = get_texto(get_prop(props, "PROPONENTE", "Proponente"))
    doc_prop       = get_texto(get_prop(props, "DOC. PROPONENTE", "DOC PROPONENTE", "CNPJ PROPONENTE"))
    construtora    = get_texto(get_prop(props, "CONSTRUTORA", "Construtora"))
    doc_const      = get_texto(get_prop(props, "DOC. CONSTRUTORA", "DOC CONSTRUTORA", "CNPJ CONSTRUTORA"))
    resp_tec       = get_texto(get_prop(props, "RESPONSÁVEL TÉCNICO", "RESPONSAVEL TECNICO", "Responsável Técnico"))
    crea           = get_texto(get_prop(props, "CREA", "CAU/CREA", "CAU"))
    doc_resp       = get_texto(get_prop(props, "DOC. RESPONSÁVEL", "DOC RESPONSAVEL", "CPF RESPONSÁVEL"))
    incorporador   = get_texto(get_prop(props, "INCORPORADOR", "Incorporador"))
    doc_incorp     = get_texto(get_prop(props, "DOC. INCORPORADOR", "DOC INCORPORADOR"))
    tel            = get_texto(get_prop(props, "TEL. CONTATO", "TEL CONTATO", "TELEFONE", "Telefone"))
    email          = get_texto(get_prop(props, "EMAIL", "E-MAIL", "Email"))
    n_un_v         = get_numero(get_prop(props, "Nº DE UNIDADES", "N DE UNIDADES", "N° DE UNIDADES", "UNIDADES", "Nº UNIDADES"))
    n_un           = int(n_un_v) if n_un_v is not None else ""
    prazo_v        = get_numero(get_prop(props, "PRAZO PREVISTO", "PRAZO", "Prazo Previsto"))
    prazo          = int(prazo_v) if prazo_v is not None else ""
    area_lote_v    = get_numero(get_prop(props, "ÁREA DO LOTE", "AREA DO LOTE", "Área do Lote"))
    area_lote      = area_lote_v if area_lote_v is not None else ""
    area_equiv_v   = get_numero(get_prop(props, "ÁREA EQUIVALENTE", "AREA EQUIVALENTE", "Área Equivalente"))
    area_equiv     = area_equiv_v if area_equiv_v is not None else ""

    # Status calculado
    if obraf:   sl, sc = "OBRA FINALIZADA",     "finalizada"
    elif obra:  sl, sc = "OBRA INICIADA",        "obra"
    elif aprc:  sl, sc = "APROVAÇÃO CONCLUÍDA",  "aprovada"
    elif apri:  sl, sc = "APROVAÇÃO INICIADA",   "aprovando"
    elif proc:  sl, sc = "PROCESSO INICIADO",    "processo"
    else:       sl, sc = "NÃO INICIADO",         "pendente"

    return {
        "id": page["id"], "nome": nome,
        "setor": setor, "cidade": cidade, "rua": rua,
        "complemento": complemento, "cep": cep,
        "status_label": sl, "status_cor": sc,
        "processo_iniciado": proc, "aprovacao_iniciada": apri,
        "aprovacao_concluida": aprc, "obra_iniciada": obra, "obra_finalizada": obraf,
        "inicio_processo": ini_proc, "inicio_aprovacao": ini_apro,
        "termino_aprovacao": ter_apro, "inicio_obras": ini_obra, "termino_obras": ter_obra,
        "proponente": proponente, "doc_proponente": doc_prop,
        "construtora": construtora, "doc_construtora": doc_const,
        "responsavel_tecnico": resp_tec, "crea": crea, "doc_responsavel": doc_resp,
        "incorporador": incorporador, "doc_incorporador": doc_incorp,
        "tel_contato": tel, "email": email,
        "n_unidades": n_un, "prazo_previsto": prazo,
        "area_lote": area_lote, "area_equivalente": area_equiv,
    }

# ── Gerar FRE preenchida (Python puro, sem SheetJS) ─────────────────────────

def gerar_fre(emp):
    """
    Gera FRE preenchida usando openpyxl + xlsx.
    Preserva formatação, mesclagens e fórmulas de todas as abas.
    """
    from openpyxl import load_workbook

    src = "FRE_v015.xlsx"
    if not os.path.exists(src):
        print(f"  AVISO: {src} não encontrado no repositório")
        return None

    hoje = date.today().strftime("%d/%m/%Y")
    n_un = emp["n_unidades"]

    mapa = {
        "B7":  emp["nome"],
        "B10": emp["rua"],
        "M10": emp["complemento"],
        "B13": emp["setor"],
        "I13": emp["cidade"],
        "N13": emp["cep"],
        "B16": emp["proponente"],
        "M16": emp["doc_proponente"],
        "B19": emp["construtora"],
        "M19": emp["doc_construtora"],
        "B22": emp["responsavel_tecnico"],
        "J22": emp["crea"],
        "M22": emp["doc_responsavel"],
        "B25": emp["incorporador"],
        "M25": emp["doc_incorporador"],
        "B28": emp["responsavel_tecnico"],
        "J28": emp["tel_contato"],
        "M28": emp["email"],
        "E36": n_un if n_un != "" else None,
        "N59": emp["prazo_previsto"] if emp["prazo_previsto"] != "" else None,
        "I66": emp["area_lote"] if emp["area_lote"] != "" else None,
        "I67": emp["area_equivalente"] if emp["area_equivalente"] != "" else None,
        "C227": hoje,
        # C223 e C224 sao formulas =B16 e =M16 — nao sobrescrever
    }

    nome_safe = "".join(c for c in emp["nome"] if c.isalnum() or c in " _-").strip().replace(" ", "_")
    out_path  = f"fre_{nome_safe}.xlsx"
    shutil.copy2(src, out_path)

    wb = load_workbook(out_path)
    ws = wb["FRE"]

    for cel, val in mapa.items():
        if val is None or val == "":
            continue
        ws[cel].value = val

    desc = ws["B41"].value or ""
    if n_un != "" and "{Nº UNIDADES}" in str(desc):
        ws["B41"].value = str(desc).replace("{Nº UNIDADES}", str(n_un))

    wb.save(out_path)
    print(f"  FRE gerada: {out_path}")
    return out_path

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("fetch_empreendimentos.py — Morais Engenharia")
    print("=" * 60)

    paginas = buscar_paginas()
    empreendimentos = []
    fres_geradas = []

    for p in paginas:
        try:
            emp = processar_pagina(p)
            if not emp["nome"]:
                print(f"  IGNORADO: sem nome (id={p.get('id','?')})")
                continue
            empreendimentos.append(emp)
            print(f"  OK: {emp['nome']} — {emp['status_label']}")

            # Gera FRE preenchida para cada empreendimento
            fre = gerar_fre(emp)
            if fre:
                fres_geradas.append(fre)
        except Exception as ex:
            print(f"  ERRO {p.get('id','?')}: {ex}")

    empreendimentos.sort(key=lambda x: x["nome"].lower())

    saida = {
        "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "empreendimentos": empreendimentos,
    }
    with open("data_emp.json", "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"data_emp.json: {len(empreendimentos)} empreendimento(s)")
    print(f"FREs geradas:  {len(fres_geradas)}")
    print("=" * 60)

if __name__ == "__main__":
    main()
