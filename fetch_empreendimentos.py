"""
fetch_empreendimentos.py
Morais Engenharia · Site de Empreendimentos
v3 — Junho 2026

Gera:
  data_emp.json                      — dados para o site
  FRE__<NOME>__RV<N>.xlsx            — Ficha Resumo do Empreendimento
  CARTA_PROPOSTA__<NOME>__RV<N>.docx — Carta Proposta CEF
  MEMORIAL_HABITACAO__<NOME>__RV<N>.docx
  MEMORIAL_INFRAESTRUTURA__<NOME>__RV<N>.docx
  QUADROS_ABNT__<NOME>__RV<N>.xlsx   — Quadros NBR 12.721

Segredos necessários (GitHub Actions Secrets):
  NOTION_TOKEN_EMP  — token do BD EMPREENDIMENTOS
  NOTION_DB_EMP     — ID do BD EMPREENDIMENTOS
  NOTION_TOKEN_UH   — token do BD UNIDADES DO EMPREENDIMENTO
  NOTION_DB_UH      — ID do BD UNIDADES DO EMPREENDIMENTO
"""

import os, json, requests, shutil, re, copy
from datetime import datetime, date

# ── Credenciais ───────────────────────────────────────────────────────────────
NOTION_TOKEN = os.environ.get("NOTION_TOKEN_EMP", "")
NOTION_DB    = os.environ.get("NOTION_DB_EMP", "")

# BD de Unidades — token e DB separados
NOTION_TOKEN_UH = os.environ.get("NOTION_TOKEN_UH",
                  "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")
NOTION_DB_UH    = os.environ.get("NOTION_DB_UH",
                  "384c5ab532d3807193fbde7e1432bdba")

def _headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
        "Notion-Version": "2022-06-28",
    }

HEADERS    = _headers(NOTION_TOKEN)
HEADERS_UH = _headers(NOTION_TOKEN_UH)

# ── Helpers de propriedades Notion ───────────────────────────────────────────

def get_texto(prop):
    if not prop: return ""
    t = prop.get("type", "")
    if t == "title":     items = prop.get("title", [])
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

def get_texto_ou_select(prop):
    """Lê campo que pode ser rich_text OU select (migração Notion)."""
    if not prop: return ""
    t = prop.get("type", "")
    if t == "select":    return get_select(prop)
    if t == "rich_text": return get_texto(prop)
    if t == "title":     return get_texto(prop)
    return ""

def sim_nao(props, *nomes):
    for n in nomes:
        v = get_select(props.get(n) or {})
        if v.upper() in ("SIM", "S", "YES", "TRUE"): return True
        if v.upper() in ("NÃO", "NAO", "N", "NO", "FALSE"): return False
    return False

def get_prop(props, *nomes):
    for n in nomes:
        v = props.get(n)
        if v is not None: return v
    return {}

# ── Busca genérica de páginas ─────────────────────────────────────────────────

def buscar_paginas(db_id, headers, label=""):
    db_id = db_id.replace("ntn_", "", 1) if db_id.startswith("ntn_") else db_id
    print(f"Buscando {label} — DB: {db_id}")

    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    resultados, has_more, cursor = [], True, None

    while has_more:
        body = {"page_size": 100}
        if cursor: body["start_cursor"] = cursor
        resp = requests.post(url, headers=headers, json=body, timeout=30)
        print(f"  HTTP {resp.status_code}")
        if resp.status_code != 200:
            print(f"  ERRO: {resp.text[:500]}"); break
        data = resp.json()
        resultados.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        cursor   = data.get("next_cursor")

    print(f"  → {len(resultados)} registros")

    # Debug: mostra campos da 1ª página
    if resultados:
        print(f"  Campos ({label}):")
        for k, v in resultados[0].get("properties", {}).items():
            t = v.get("type", "?")
            if   t == "select":    val = get_select(v)
            elif t == "title":     val = get_texto(v)
            elif t == "rich_text": val = get_texto(v)
            elif t == "number":    val = str(get_numero(v))
            else:                  val = ""
            print(f"    {t:12} | {k:40} | {val}")

    return resultados

# ── Processar página EMPREENDIMENTOS ─────────────────────────────────────────

def processar_pagina(page):
    props = page.get("properties", {})

    nome = ""
    for v in props.values():
        if v.get("type") == "title":
            nome = get_texto(v); break

    setor       = get_texto_ou_select(get_prop(props, "SETOR", "Setor", "setor"))
    cidade      = get_texto_ou_select(get_prop(props, "CIDADE", "Cidade", "cidade"))
    proponente  = get_texto_ou_select(get_prop(props, "PROPONENTE", "Proponente"))
    doc_prop    = get_texto_ou_select(get_prop(props, "DOC. PROPONENTE", "DOC PROPONENTE", "CNPJ PROPONENTE"))
    construtora = get_texto_ou_select(get_prop(props, "CONSTRUTORA", "Construtora"))
    doc_const   = get_texto_ou_select(get_prop(props, "DOC. CONSTRUTORA", "DOC CONSTRUTORA", "CNPJ CONSTRUTORA"))
    resp_tec    = get_texto_ou_select(get_prop(props, "RESPONSÁVEL TÉCNICO", "RESPONSAVEL TECNICO", "Responsável Técnico"))
    doc_resp    = get_texto_ou_select(get_prop(props, "DOC. RESPONSÁVEL", "DOC RESPONSAVEL", "CPF RESPONSÁVEL"))

    rua         = get_texto(get_prop(props, "RUA", "Rua", "rua", "ENDEREÇO", "Endereço"))
    complemento = get_texto(get_prop(props, "COMPLEMENTO", "Complemento"))
    cep         = get_texto(get_prop(props, "CEP", "Cep", "cep"))
    crea        = get_texto(get_prop(props, "CREA", "CAU/CREA", "CAU"))
    incorporador  = get_texto(get_prop(props, "INCORPORADOR", "Incorporador"))
    doc_incorp    = get_texto(get_prop(props, "DOC. INCORPORADOR", "DOC INCORPORADOR"))
    tel           = get_texto(get_prop(props, "TEL. CONTATO", "TEL CONTATO", "TELEFONE", "Telefone"))
    email         = get_texto(get_prop(props, "EMAIL", "E-MAIL", "Email"))
    agencia       = get_texto(get_prop(props, "AGÊNCIA", "AGENCIA", "Agência"))

    n_un_v = get_numero(get_prop(props, "Nº DE UNIDADES", "N DE UNIDADES", "N° DE UNIDADES", "UNIDADES", "Nº UNIDADES"))
    n_un   = int(n_un_v) if n_un_v is not None else ""

    prazo_v = get_numero(get_prop(props, "PRAZO PREVISTO", "PRAZO", "Prazo Previsto"))
    prazo   = int(prazo_v) if prazo_v is not None else ""

    area_lote_v  = get_numero(get_prop(props, "ÁREA LOTE", "ÁREA DO LOTE", "AREA LOTE", "AREA DO LOTE", "Área do Lote"))
    area_lote    = area_lote_v if area_lote_v is not None else ""

    area_equiv_v = get_numero(get_prop(props, "ÁREA EQUIVALENTE TOTAL", "ÁREA EQUIVALENTE", "AREA EQUIVALENTE TOTAL", "AREA EQUIVALENTE", "Área Equivalente"))
    area_equiv   = area_equiv_v if area_equiv_v is not None else ""

    valor_terreno_v = get_numero(get_prop(props, "VALOR DO TERRENO", "Valor do Terreno", "VALOR TERRENO"))
    valor_terreno   = valor_terreno_v if valor_terreno_v is not None else ""

    revisao_v = get_numero(get_prop(props, "REVISÃO", "REVISAO", "Revisão", "Revisao"))
    revisao   = int(revisao_v) if revisao_v is not None else 0

    proc  = sim_nao(props, "PROCESSO INICIADO", "PROCESSO INCIADO", "Processo Iniciado")
    apri  = sim_nao(props, "APROVAÇÃO INICIADA", "APROVAÇÃO INCIADA", "APROVACAO INICIADA", "APROVACAO INCIADA", "Aprovação Iniciada")
    aprc  = sim_nao(props, "APROVAÇÃO CONCLUÍDA", "APROVACAO CONCLUIDA", "Aprovação Concluída")
    obra  = sim_nao(props, "OBRA INICIADA", "OBRA INCIADA", "Obra Iniciada")
    obraf = sim_nao(props, "OBRA FINALIZADA", "OBRA FINALZIADA", "Obra Finalizada")

    ini_proc = get_data(get_prop(props, "INÍCIO DO PROCESSO", "INICIO DO PROCESSO", "Início do Processo"))
    ini_apro = get_data(get_prop(props, "INÍCIO DA APROVAÇÃO", "INICIO DA APROVACAO", "Início da Aprovação"))
    ter_apro = get_data(get_prop(props, "TÉRMINO DA APROVAÇÃO", "TERMINO DA APROVACAO"))
    ini_obra = get_data(get_prop(props, "INÍCIO DAS OBRAS", "INICIO DAS OBRAS", "Início das Obras"))
    ter_obra = get_data(get_prop(props, "TÉRMINO DAS OBRAS", "TERMINO DAS OBRAS"))

    if   obraf: sl, sc = "OBRA FINALIZADA",    "finalizada"
    elif obra:  sl, sc = "OBRA INICIADA",       "obra"
    elif aprc:  sl, sc = "APROVAÇÃO CONCLUÍDA", "aprovada"
    elif apri:  sl, sc = "APROVAÇÃO INICIADA",  "aprovando"
    elif proc:  sl, sc = "PROCESSO INICIADO",   "processo"
    else:       sl, sc = "NÃO INICIADO",        "pendente"

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
        "tel_contato": tel, "email": email, "agencia": agencia,
        "n_unidades": n_un, "prazo_previsto": prazo,
        "area_lote": area_lote, "area_equivalente": area_equiv,
        "valor_terreno": valor_terreno, "revisao": revisao,
    }

# ── Processar página UNIDADES DO EMPREENDIMENTO ───────────────────────────────

def processar_unidade(page):
    """
    Retorna dict com os dados de uma unidade.
    - uh_num: número da UH (nome da página, ex: "1", "2"...)
    - nome_emp: campo NOME DO EMPREENDIMENTO (texto) — chave de ligação
    - area_const_priv, area_const_com: áreas construídas
    - area_desc_priv, area_desc_com: áreas descobertas
    - tipologia: campo TIPOLOGIA (select ou texto)
    """
    props = page.get("properties", {})

    # Nome da página = número da UH
    uh_num = ""
    for v in props.values():
        if v.get("type") == "title":
            uh_num = get_texto(v); break

    nome_emp = get_texto(get_prop(props,
        "NOME DO EMPREENDIMENTO", "NOME DO EMPREENDI...", "nome_empreendimento"))

    tipologia = get_texto_ou_select(get_prop(props, "TIPOLOGIA", "Tipologia"))

    area_const_priv = get_numero(get_prop(props,
        "ÁREA CONSTRUÍDA PRIVATIVA", "AREA CONSTRUIDA PRIVATIVA",
        "Área Construída Privativa")) or 0.0

    area_const_com = get_numero(get_prop(props,
        "ÁREA CONSTRUÍDA COMUM", "AREA CONSTRUIDA COMUM",
        "Área Construída Comum")) or 0.0

    area_desc_priv = get_numero(get_prop(props,
        "ÁREA DESCOBERTA PRIVATIVA", "AREA DESCOBERTA PRIVATIVA",
        "Área Descoberta Privativa")) or 0.0

    area_desc_com = get_numero(get_prop(props,
        "ÁREA DESCOBERTA COMUM", "AREA DESCOBERTA COMUM",
        "Área Descoberta Comum")) or 0.0

    return {
        "uh_num":         uh_num,
        "nome_emp":       nome_emp,
        "tipologia":      tipologia,
        "area_const_priv": area_const_priv,
        "area_const_com":  area_const_com,
        "area_desc_priv":  area_desc_priv,
        "area_desc_com":   area_desc_com,
    }

# ── Helpers de formatação ─────────────────────────────────────────────────────

def nome_arquivo(emp, prefixo, ext):
    """FRE__VALE_DAS_BRISAS__RV0.xlsx"""
    rv   = emp.get("revisao", 0)
    safe = "".join(c for c in emp["nome"] if c.isalnum() or c in " _-")
    safe = safe.strip().replace(" ", "_")
    return f"{prefixo}__{safe}__RV{rv}.{ext}"

def brl_fmt(v):
    if v == "" or v is None: return ""
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def data_extenso():
    meses = ["janeiro","fevereiro","março","abril","maio","junho",
             "julho","agosto","setembro","outubro","novembro","dezembro"]
    h = date.today()
    return str(h.day), meses[h.month - 1], str(h.year)

def data_hoje_fmt():
    return date.today().strftime("%d/%m/%Y")

# ── Substituição genérica em Word (.docx) ─────────────────────────────────────

def substituir_docx(doc, mapa):
    """
    Substitui todos os placeholders em parágrafos e tabelas do Word.
    Reconstrói runs do parágrafo inteiro para tratar fragmentação do Word.
    """
    def sub_para(paragraph):
        texto = "".join(r.text for r in paragraph.runs)
        for k, v in mapa.items():
            texto = texto.replace(k, str(v) if v else "")
        if paragraph.runs:
            paragraph.runs[0].text = texto
            for r in paragraph.runs[1:]:
                r.text = ""

    for para in doc.paragraphs:
        sub_para(para)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    sub_para(para)

# ── Gerar FRE (.xlsx) ─────────────────────────────────────────────────────────

def gerar_fre(emp):
    from openpyxl import load_workbook

    src = None
    for f in sorted(os.listdir("."), reverse=True):
        if f.upper().startswith("FRE") and f.endswith(".xlsx"):
            src = f; break
    if not src:
        print("  AVISO: FRE_v*.xlsx não encontrado"); return None

    hoje = data_hoje_fmt()
    n_un = emp["n_unidades"]
    vt_fmt = brl_fmt(emp.get("valor_terreno", ""))

    mapa_cel = {
        "B7":  emp["nome"],       "B10": emp["rua"],
        "M10": emp["complemento"], "B13": emp["setor"],
        "I13": emp["cidade"],     "N13": emp["cep"],
        "B16": emp["proponente"], "M16": emp["doc_proponente"],
        "B19": emp["construtora"],"M19": emp["doc_construtora"],
        "B22": emp["responsavel_tecnico"], "J22": emp["crea"],
        "M22": emp["doc_responsavel"],
        "B25": emp["incorporador"],"M25": emp["doc_incorporador"],
        "B28": emp["responsavel_tecnico"],"J28": emp["tel_contato"],
        "M28": emp["email"],
        "E36": n_un if n_un != "" else None,
        "N59": emp["prazo_previsto"] if emp["prazo_previsto"] != "" else None,
        "I66": emp["area_lote"] if emp["area_lote"] != "" else None,
        "I67": emp["area_equivalente"] if emp["area_equivalente"] != "" else None,
        "C227": hoje,
    }

    out = nome_arquivo(emp, "FRE", "xlsx")
    shutil.copy2(src, out)
    wb = load_workbook(out)
    ws = wb["FRE"]

    for cel, val in mapa_cel.items():
        if val is None or val == "": continue
        ws[cel].value = val

    # Substitui placeholders de texto em toda a planilha
    for row in ws.iter_rows():
        for cell in row:
            if isinstance(cell.value, str):
                v = cell.value
                v = v.replace("{VALOR DO TERRENO}", vt_fmt)
                v = v.replace("{Nº UNIDADES}", str(n_un) if n_un != "" else "")
                if v != cell.value:
                    cell.value = v

    wb.save(out)
    print(f"  FRE: {out}")
    return out

# ── Gerar Carta Proposta (.docx) ──────────────────────────────────────────────

def gerar_carta_proposta(emp):
    try:
        from docx import Document
    except ImportError:
        print("  AVISO: python-docx não instalado"); return None

    src = "CARTA_PROPOSTA.docx"
    if not os.path.exists(src):
        print(f"  AVISO: {src} não encontrado"); return None

    dia, mes, ano = data_extenso()
    n_un  = str(emp["n_unidades"]) if emp["n_unidades"] != "" else ""
    prazo = str(emp["prazo_previsto"]) if emp["prazo_previsto"] != "" else ""
    vt_fmt = brl_fmt(emp.get("valor_terreno", ""))

    mapa = {
        "{AGÊNCIA}":                 emp.get("agencia", ""),
        "{NOME DO EMPRRENDIMENTO}":  emp["nome"],
        "{NOME DO EMPREENDIMENTO}":  emp["nome"],
        "{CONSTRUTORA}":             emp["construtora"],
        "{DOC. CONSTRUTORA}":        emp["doc_construtora"],
        "{RESPONSÁVEL TÉCNICO}":     emp["responsavel_tecnico"],
        "{TEL. CONTATO}":            emp["tel_contato"],
        "{RUA}":                     emp["rua"],
        "{COMPLEMENTO}":             emp["complemento"],
        "{SETOR}":                   emp["setor"],
        "{CIDADE}":                  emp["cidade"],
        "{CEP}":                     emp["cep"],
        "{Nº DE UNIDADES}":          n_un,
        "{VALOR DO TERRENO}":        vt_fmt,
        # datas fracionadas que o Word cortou
        "HJ":  dia,
        "MES": mes,
        "ANO": ano,
    }

    doc = Document(src)

    # Tratamento especial: {PRAZO} cortado como {PRA pelo Word
    def sub_para_carta(paragraph):
        texto = "".join(r.text for r in paragraph.runs)
        # Normaliza qualquer fragmento de {PRAZO}
        texto = re.sub(r'\{PRA[ZO]*\}?', prazo, texto)
        texto = re.sub(r'\{PRAZO\}', prazo, texto)
        for k, v in mapa.items():
            texto = texto.replace(k, str(v) if v else "")
        if paragraph.runs:
            paragraph.runs[0].text = texto
            for r in paragraph.runs[1:]:
                r.text = ""

    for para in doc.paragraphs:
        sub_para_carta(para)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    sub_para_carta(para)

    out = nome_arquivo(emp, "CARTA_PROPOSTA", "docx")
    doc.save(out)
    print(f"  Carta Proposta: {out}")
    return out

# ── Gerar Memoriais (.docx) ───────────────────────────────────────────────────

def gerar_memorial(emp, tipo):
    try:
        from docx import Document
    except ImportError:
        print("  AVISO: python-docx não instalado"); return None

    srcs = {
        "HABITACAO":      ["MEMORIAL_DESCRITIVO_DE_HABITACAO.docx",
                           "MEMORIAL_DESCRITIVO_DE_HABITACAO.doc"],
        "INFRAESTRUTURA": ["MEMORIAL_DESCRITIVO_INFRAESTRUTURA.docx",
                           "MEMORIAL_DESCRITIVO_INFRAESTRUTURA.doc"],
    }
    src = next((n for n in srcs.get(tipo, []) if os.path.exists(n)), None)
    if not src:
        print(f"  AVISO: memorial {tipo} não encontrado"); return None

    dia, mes, ano = data_extenso()
    data_hoje_ext = f"{dia} de {mes} de {ano}"

    mapa = {
        "{PROPORNENTE}":            emp["proponente"],  # typo original
        "{PROPONENTE}":             emp["proponente"],
        "{CONSTRUTORA}":            emp["construtora"],
        "{NOME DO EMPREENDIMENTO}": emp["nome"],
        "{RUA}":                    emp["rua"],
        "{COMPLEMENTO}":            emp["complemento"],
        "{SETOR}":                  emp["setor"],
        "{CIDADE}":                 emp["cidade"],
        "{DATA HOJE}":              data_hoje_ext,
        "{DOC. CONSTRUTORA}":       emp["doc_construtora"],
        "{DOC. PROPONENTE}":        emp["doc_proponente"],
        "{RESPONSÁVEL TÉCNICO}":    emp["responsavel_tecnico"],
        "{CREA}":                   emp["crea"],
    }

    doc = Document(src)
    substituir_docx(doc, mapa)

    prefixo = "MEMORIAL_HABITACAO" if tipo == "HABITACAO" else "MEMORIAL_INFRAESTRUTURA"
    out = nome_arquivo(emp, prefixo, "docx")
    doc.save(out)
    print(f"  Memorial {tipo}: {out}")
    return out

# ── Gerar Quadros ABNT (.xlsx) ────────────────────────────────────────────────

def gerar_quadros_abnt(emp, unidades):
    """
    Gera o XLSX dos Quadros NBR 12.721 preenchido com dados do empreendimento
    e das unidades do BD UNIDADES DO EMPREENDIMENTO.

    Lógica da CAPA:
      - Template: linha 9 (1 linha por UH)
      - Total:    linha 10 (ajustada para somar todas as UHs inseridas)
      - Col B = FRAÇÃO N  | Col C = CASA N
      - Col D = área construída (priv + comum)
      - Col E = área descoberta (priv + comum)
      - Col F = =SUM(E_n, D_n)   (Total)
      - Col G = =F_n             (Fração Ideal Total m²)
      - Col H = =SUM(G_n/G_TOTAL)  (Fração Ideal %)

    Lógica do QUADRO II:
      - Template: linha 17 (1 linha por UH)
      - Total:    linha 19
      - Col B  = CASA 01
      - Col C  = =CAPA!D_n  (área construída da CAPA)
      - Col D  = =CAPA!E_n  (área descoberta da CAPA)
      - Col F  = =SUM(C+D)  | Col G = =SUM(C+E)
      - Col K  = =SUM(H+I)  | Col L = =SUM(H+J)
      - Col M  = =SUM(G+L)
      - Col N  = =CAPA!H_n  (coef. proporcionalidade = %)
      - Col O  = =ROUND(N*QI!M39,2)
      - Col P  = =ROUND(N*QI!N39,2)
      - Col Q  = =ROUND(N*QI!O39,2)
      - Col R  = =SUM(O+P)  | Col S = =SUM(O+Q)
      - Col T  = =SUM(F+K+R) | Col U = =SUM(M+S)
      - Col V  = 1 (quantidade sempre 1)
    """
    try:
        from openpyxl import load_workbook
        from openpyxl.utils import get_column_letter
    except ImportError:
        print("  AVISO: openpyxl não instalado"); return None

    src = "QUADROS_ABNT.xlsx"
    if not os.path.exists(src):
        print(f"  AVISO: {src} não encontrado"); return None

    # Filtra unidades deste empreendimento e ordena pelo número (nome da página)
    uhs = [u for u in unidades if u["nome_emp"].strip().upper() == emp["nome"].strip().upper()]

    # Ordena pelo número da UH (conversão para int se possível)
    def sort_key(u):
        try: return int(u["uh_num"])
        except: return u["uh_num"]
    uhs.sort(key=sort_key)

    n = len(uhs)
    if n == 0:
        print(f"  AVISO: nenhuma UH encontrada para '{emp['nome']}'"); return None

    print(f"  Quadros ABNT: {n} UH(s) para '{emp['nome']}'")

    dia, mes, ano = data_extenso()
    data_hoje_ext = f"{dia} de {mes} de {ano}"
    hoje_fmt      = data_hoje_fmt()

    out = nome_arquivo(emp, "QUADROS_ABNT", "xlsx")
    shutil.copy2(src, out)

    wb = load_workbook(out)

    # ── 1. CAPA ───────────────────────────────────────────────────────────────
    ws_capa = wb["CAPA"]

    # Preenche campos de texto/data da CAPA
    loc_str = f"{emp['rua']}, {emp['complemento']}; {emp['setor']} - {emp['cidade']}"
    ws_capa["C3"] = loc_str
    ws_capa["B11"] = f"{emp['cidade']} , {hoje_fmt}"
    ws_capa["B14"] = emp["responsavel_tecnico"]
    ws_capa["B15"] = emp["crea"]

    # Área do terreno: inserida diretamente em G10
    # (D4 = =G10, então D4 ficará correto automaticamente)
    if emp.get("area_lote", "") != "":
        ws_capa["G10"] = emp["area_lote"]

    # Linha de template original = linha 9 (índice 8)
    # Linha de TOTAL original    = linha 10 (índice 9)
    # Se n > 1: insere (n-1) linhas antes da linha 10, copiando o template

    # Para trabalhar corretamente com openpyxl (não tem insert_rows no read):
    # Vamos recarregar sem read_only para poder manipular
    wb.close()
    wb = load_workbook(out)
    ws_capa = wb["CAPA"]

    # Linha base das unidades (1-indexed no Excel)
    CAPA_FIRST_ROW = 9
    CAPA_TOTAL_ROW = 10  # original, antes de inserir

    if n > 1:
        # Insere (n-1) linhas em branco após a linha 9
        ws_capa.insert_rows(CAPA_TOTAL_ROW, amount=n - 1)

    total_row = CAPA_FIRST_ROW + n  # nova linha do TOTAL após inserção

    # Preenche cada linha de UH
    for i, uh in enumerate(uhs):
        row = CAPA_FIRST_ROW + i
        num = i + 1
        area_const = uh["area_const_priv"] + uh["area_const_com"]
        area_desc  = uh["area_desc_priv"]  + uh["area_desc_com"]

        ws_capa.cell(row=row, column=2).value = f"FRAÇÃO {num}"
        ws_capa.cell(row=row, column=3).value = f"CASA {num}"
        ws_capa.cell(row=row, column=4).value = round(area_const, 2)
        ws_capa.cell(row=row, column=5).value = round(area_desc, 2)
        ws_capa.cell(row=row, column=6).value = f"=SUM(E{row},D{row})"
        ws_capa.cell(row=row, column=7).value = f"=F{row}"
        ws_capa.cell(row=row, column=8).value = f"=SUM(G{row}/G{total_row})"

    # Atualiza linha TOTAL com somas dinâmicas
    first = CAPA_FIRST_ROW
    last  = CAPA_FIRST_ROW + n - 1
    ws_capa.cell(row=total_row, column=2).value = "TOTAL"
    ws_capa.cell(row=total_row, column=4).value = f"=SUM(D{first}:D{last})"
    ws_capa.cell(row=total_row, column=5).value = f"=SUM(E{first}:E{last})"
    ws_capa.cell(row=total_row, column=6).value = f"=SUM(F{first}:F{last})"
    ws_capa.cell(row=total_row, column=7).value = f"=SUM(G{first}:G{last})"
    ws_capa.cell(row=total_row, column=8).value = f"=SUM(H{first}:H{last})"

    # Linha de data/assinatura: move para total_row + 1 e + 3/4
    ws_capa.cell(row=total_row + 1, column=2).value = f"{emp['cidade']} , {hoje_fmt}"
    ws_capa.cell(row=total_row + 3, column=2).value = "____________________________________________"
    ws_capa.cell(row=total_row + 4, column=2).value = emp["responsavel_tecnico"]
    ws_capa.cell(row=total_row + 5, column=2).value = emp["crea"]

    # ── 2. INFORMAÇÕES PRELIMINARES ───────────────────────────────────────────
    ws_ip = wb["INFORMAÇÕES PRELIMINARES"]

    # Substitui placeholders de texto nas células
    mapa_ip = {
        "{IMCORPORADOR}":         emp["incorporador"],
        "{DOC. INCORPORADOR}":    emp["doc_incorporador"],
        "{NOME DO EMPREENDIMENTO}": emp["nome"],
        "{Nº DE UNIDADES}":       str(n_un_str := (str(emp["n_unidades"]) if emp["n_unidades"] != "" else str(n))),
        "{Nº UNIDADES}":          n_un_str,
    }
    for row in ws_ip.iter_rows():
        for cell in row:
            if isinstance(cell.value, str):
                v = cell.value
                for k, val in mapa_ip.items():
                    v = v.replace(k, val)
                # Data
                if "=CAPA!B11" in v:
                    cell.value = f"{emp['cidade']} , {hoje_fmt}"
                elif v != cell.value:
                    cell.value = v

    # ── 3. QUADRO I — só preenche DATA HOJE ───────────────────────────────────
    ws_q1 = wb["QUADRO I"]
    ws_q1["C10"] = hoje_fmt

    # Linha TÉRREO (L16) col C = =CAPA!D10 já está como fórmula no template
    # Ajusta para apontar para a nova linha total da CAPA
    ws_q1["C16"] = f"=CAPA!D{total_row}"

    # ── 4. QUADRO II — insere linhas por UH ───────────────────────────────────
    ws_q2 = wb["QUADRO II"]

    # Template na linha 17, TOTAIS na linha 19 (linha 18 vazia no template original)
    Q2_FIRST_ROW  = 17
    Q2_TOTAIS_ROW = 19  # original

    if n > 1:
        ws_q2.insert_rows(Q2_TOTAIS_ROW, amount=n - 1)

    q2_totais_row = Q2_FIRST_ROW + n

    for i, uh in enumerate(uhs):
        r    = Q2_FIRST_ROW + i
        capa_r = CAPA_FIRST_ROW + i   # linha correspondente na CAPA
        num  = i + 1

        ws_q2.cell(row=r, column=2).value  = f"CASA {num:02d}"
        ws_q2.cell(row=r, column=3).value  = f"=CAPA!D{capa_r}"   # col 20: Coberta Padrão
        ws_q2.cell(row=r, column=4).value  = f"=CAPA!E{capa_r}"   # col 21: Descoberta
        ws_q2.cell(row=r, column=6).value  = f"=SUM(C{r}+D{r})"
        ws_q2.cell(row=r, column=7).value  = f"=SUM(C{r}+E{r})"
        ws_q2.cell(row=r, column=11).value = f"=SUM(H{r}+I{r})"
        ws_q2.cell(row=r, column=12).value = f"=SUM(H{r}+J{r})"
        ws_q2.cell(row=r, column=13).value = f"=SUM(G{r}+L{r})"
        ws_q2.cell(row=r, column=14).value = f"=CAPA!H{capa_r}"   # col 31: Coef. %
        ws_q2.cell(row=r, column=15).value = f"=ROUND('QUADRO II'!N{r}*'QUADRO I'!$M$39,2)"
        ws_q2.cell(row=r, column=16).value = f"=ROUND('QUADRO II'!N{r}*'QUADRO I'!$N$39,2)"
        ws_q2.cell(row=r, column=17).value = f"=ROUND('QUADRO II'!N{r}*'QUADRO I'!$O$39,2)"
        ws_q2.cell(row=r, column=18).value = f"=SUM(O{r}+P{r})"
        ws_q2.cell(row=r, column=19).value = f"=SUM(O{r}+Q{r})"
        ws_q2.cell(row=r, column=20).value = f"=SUM(F{r}+K{r}+R{r})"
        ws_q2.cell(row=r, column=21).value = f"=SUM(M{r}+S{r})"
        ws_q2.cell(row=r, column=22).value = 1  # quantidade = sempre 1

    # Linha TOTAIS do Q2
    f_str = f"C{Q2_FIRST_ROW}:C{q2_totais_row - 1}"
    def sumproduct(col_letter, first, last):
        return f"=SUMPRODUCT({col_letter}{first}:{col_letter}{last},$V{first}:$V{last})"

    cols_q2 = list("CDEFGHIJKLMNOPQRSTU")
    ws_q2.cell(row=q2_totais_row, column=2).value = "TOTAIS"
    for idx, c in enumerate(cols_q2, start=3):
        ws_q2.cell(row=q2_totais_row, column=idx).value = \
            sumproduct(c, Q2_FIRST_ROW, q2_totais_row - 1)
    ws_q2.cell(row=q2_totais_row, column=22).value = \
        f"=SUM(V{Q2_FIRST_ROW}:V{q2_totais_row - 1})"

    # Linhas após TOTAIS (ÁREA REAL GLOBAL, OBSERVAÇÕES) — ajusta referências
    ws_q2.cell(row=q2_totais_row + 1, column=6).value  = f"=T{q2_totais_row}"
    ws_q2.cell(row=q2_totais_row + 1, column=18).value = f"=U{q2_totais_row}"

    # Data no Q2
    ws_q2["C10"] = hoje_fmt

    wb.save(out)
    print(f"  Quadros ABNT: {out}")
    return out

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("fetch_empreendimentos.py — Morais Engenharia  v3")
    print("=" * 60)

    # 1. Busca empreendimentos
    paginas_emp = buscar_paginas(NOTION_DB, HEADERS, "EMPREENDIMENTOS")

    # 2. Busca unidades
    paginas_uh = buscar_paginas(NOTION_DB_UH, HEADERS_UH, "UNIDADES DO EMPREENDIMENTO")
    unidades = []
    for p in paginas_uh:
        try:
            unidades.append(processar_unidade(p))
        except Exception as ex:
            print(f"  ERRO UH {p.get('id','?')}: {ex}")

    print(f"\nUnidades processadas: {len(unidades)}")

    # 3. Processa empreendimentos e gera documentos
    empreendimentos = []
    for p in paginas_emp:
        try:
            emp = processar_pagina(p)
            if not emp["nome"]:
                print(f"  IGNORADO: sem nome (id={p.get('id','?')})"); continue

            empreendimentos.append(emp)
            print(f"\n{'─'*50}")
            print(f"  {emp['nome']} — {emp['status_label']}  (RV{emp['revisao']})")

            gerar_fre(emp)
            gerar_carta_proposta(emp)
            gerar_memorial(emp, "HABITACAO")
            gerar_memorial(emp, "INFRAESTRUTURA")
            gerar_quadros_abnt(emp, unidades)

        except Exception as ex:
            import traceback
            print(f"  ERRO {p.get('id','?')}: {ex}")
            traceback.print_exc()

    empreendimentos.sort(key=lambda x: x["nome"].lower())

    saida = {
        "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "empreendimentos": empreendimentos,
    }
    with open("data_emp.json", "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"data_emp.json: {len(empreendimentos)} empreendimento(s)")
    print("=" * 60)

if __name__ == "__main__":
    main()
