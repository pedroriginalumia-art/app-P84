import streamlit as st
import pandas as pd
from PIL import Image
import base64
from io import BytesIO
from datetime import timedelta
import re
import requests
import io
from streamlit.components.v1 import html  # para renderizar HTML sem problemas de indentação

# =========================
# CONFIGURAÇÕES
# =========================
st.set_page_config(page_title="Desenhos P84", page_icon="📄", layout="centered")

# --- URLs no GitHub (sempre usar RAW nos downloads) ---
URL_PLANILHA_DESENHOS = "https://raw.githubusercontent.com/pedroriginalumia-art/app-P84/main/DESENHOS%20P84%20REV.xlsx"

WHITELIST_FORMAT = "xlsx"  # "xlsx" (atual) ou "csv"
URL_WHITELIST_XLSX = "https://raw.githubusercontent.com/pedroriginalumia-art/app-P84/main/whitelist_matriculas.xlsx"
URL_WHITELIST_CSV  = "https://raw.githubusercontent.com/pedroriginalumia-art/app-P84/main/whitelist_matriculas.csv"

# Sessão expira depois de X horas (opcional)
SESSION_TTL_HOURS = 8

# =========================
# UTILITÁRIOS
# =========================
def carregar_logo_base64(path: str) -> str:
    """Carrega a imagem e retorna base64 para data:image/png;base64,..."""
    logo = Image.open(path)
    buf = BytesIO()
    logo.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

def render_logo_titulo(titulo: str, subtitulo: str | None = None):
    """Cabeçalho com HTML puro (iframe), evitando o parser de Markdown."""
    try:
        logo_b64 = carregar_logo_base64("SEATRIUM.png")
        content = (
            f'<div style="display:flex;align-items:center;gap:16px;margin-bottom:20px;">'
            f'  data:image/png;base64,{logo_b64}'
            f'  <div>'
            f'    <h1 style="margin:0;">{titulo}</h1>'
            f'    {f"<div style=\'font-size:13px;color:#bbb;margin-top:2px;\'>{subtitulo}</div>" if subtitulo else ""}'
            f'  </div>'
            f'</div>'
        )
        html(content, height=150)  # altura suficiente para mostrar tudo
    except Exception:
        # fallback sem logo
        st.header(titulo)
        if subtitulo:
            st.caption(subtitulo)

def normaliza_matricula(valor: str) -> str:
    """
    Mantém somente dígitos; valida 1 a 5 dígitos.
    Não preenche com zeros; não trunca.
    """
    if valor is None:
        return ""
    s = re.sub(r"\D", "", str(valor))
    if len(s) == 0 or len(s) > 5:
        return ""
    return s

# =========================
# CARGA WHITELIST (CACHE)
# =========================
@st.cache_data(ttl=600)
def carregar_whitelist_xlsx(url: str) -> pd.DataFrame:
    # valida primeiro a URL e baixa conteúdo (compatível com Raw em repositório público)
    resp = requests.get(url, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"Whitelist XLSX não encontrada ({resp.status_code}). Verifique a URL: {url}")
    content = io.BytesIO(resp.content)
    df = pd.read_excel(content, dtype=str, engine="openpyxl")
    df.columns = [c.strip().lower() for c in df.columns]
    required = {"matricula", "nome", "funcao"}
    if not required.issubset(df.columns):
        raise ValueError("A whitelist XLSX deve conter: 'matricula', 'nome', 'funcao'.")
    df["matricula"] = df["matricula"].apply(normaliza_matricula)
    df = df[df["matricula"] != ""].copy()
    for c in ["nome", "funcao"]:
        df[c] = df[c].astype(str).str.strip()
    return df

@st.cache_data(ttl=600)
def carregar_whitelist_csv(url: str) -> pd.DataFrame:
    resp = requests.get(url, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"Whitelist CSV não encontrada ({resp.status_code}). Verifique a URL: {url}")
    df = pd.read_csv(io.BytesIO(resp.content), dtype=str)
    df.columns = [c.strip().lower() for c in df.columns]
    required = {"matricula", "nome", "funcao"}
    if not required.issubset(df.columns):
        raise ValueError("A whitelist CSV deve conter: 'matricula', 'nome', 'funcao'.")
    df["matricula"] = df["matricula"].apply(normaliza_matricula)
    df = df[df["matricula"] != ""].copy()
    for c in ["nome", "funcao"]:
        df[c] = df[c].astype(str).str.strip()
    return df

def obter_whitelist() -> pd.DataFrame:
    if WHITELIST_FORMAT == "xlsx":
        return carregar_whitelist_xlsx(URL_WHITELIST_XLSX)
    elif WHITELIST_FORMAT == "csv":
        return carregar_whitelist_csv(URL_WHITELIST_CSV)
    else:
        raise ValueError("Formato de whitelist inválido. Use 'xlsx' ou 'csv'.")

# =========================
# CARGA PLANILHA DE DESENHOS (CACHE)
# =========================
@st.cache_data(ttl=600)
def carregar_dados_desenhos(url: str) -> pd.DataFrame:
    # Para arquivos RAW públicos, pd.read_excel com engine openpyxl funciona bem
    return pd.read_excel(url, engine="openpyxl")

# =========================
# AUTENTICAÇÃO
# =========================
def buscar_usuario_por_matricula(m_input: str, wl: pd.DataFrame) -> dict | None:
    m = normaliza_matricula(m_input)
    if m == "":
        return None
    row = wl.loc[wl["matricula"] == m]
    if row.empty:
        return None
    r = row.iloc[0]
    return {"matricula": r["matricula"], "nome": r["nome"], "funcao": r["funcao"]}

def require_auth() -> bool:
    authenticated = st.session_state.get("authenticated", False)
    login_time = st.session_state.get("login_time", None)
    if authenticated and login_time:
        age = pd.Timestamp.utcnow() - login_time
        if age > timedelta(hours=SESSION_TTL_HOURS):
            for k in ["authenticated", "login_time", "matricula", "nome", "funcao"]:
                st.session_state.pop(k, None)
            st.warning("Sua sessão expirou. Faça login novamente.")
            return False
        return True
    return authenticated

def login_view():
    render_logo_titulo("Acesso restrito — Desenhos P84")
    st.write("Informe sua **matrícula (apenas números, até 5 dígitos)** para continuar.")

    with st.form("login_form", clear_on_submit=False):
        matricula_input = st.text_input("Matrícula", placeholder="Ex.: 12345", max_chars=5)
        submitted = st.form_submit_button("Entrar")

    if submitted:
        if not re.fullmatch(r"\d{1,5}", matricula_input or ""):
            st.error("Matrícula inválida. Use apenas números (1 a 5 dígitos).")
            return
        try:
            wl = obter_whitelist()
        except Exception as e:
            st.error(f"Erro ao carregar a whitelist: {e}")
            return

        user = buscar_usuario_por_matricula(matricula_input, wl)
        if user:
            st.session_state.update({
                "authenticated": True,
                "matricula": user["matricula"],
                "nome": user["nome"],
                "funcao": user["funcao"],
                "login_time": pd.Timestamp.utcnow(),
            })
            # Boas-vindas (nome em destaque; função menor)
            st.markdown(
                f"""
                <div style="background:#e7f3ff;border:1px solid #b3d7ff;padding:12px;border-radius:8px;margin-top:8px;">
                    <div style="font-weight:600;font-size:16px;">Seja bem-vindo, {user['nome']}!</div>
                    <div style="font-size:13px;color:#555;margin-top:2px;">{user['funcao']}</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            st.experimental_rerun()
        else:
            st.error("Matrícula não encontrada na whitelist. Verifique e tente novamente.")

def top_bar():
    render_logo_titulo("Desenhos P84")
    col1, col2 = st.columns([1, 1])
    with col1:
        nome = st.session_state.get("nome", "—")
        funcao = st.session_state.get("funcao", "")
        st.caption(f"Usuário: **{nome}**" + (f" • {funcao}" if funcao else ""))
    with col2:
        if st.button("Sair"):
            for k in ["authenticated", "matricula", "nome", "funcao", "login_time"]:
                st.session_state.pop(k, None)
            st.success("Você saiu da sessão.")
            st.experimental_rerun()

# =========================
# LÓGICA DO APP (PROTEGIDA)
# =========================
def buscar_desenho(df, termo):
    filtro = df['DESENHO'].astype(str).str.contains(termo, case=False, na=False)
    return df[filtro]

def ordenar_revisoes(revisoes):
    numericas = [r for r in revisoes if str(r).isdigit()]
    letras = [r for r in revisoes if str(r).isalpha()]
    return sorted(numericas, key=int) + sorted(letras)

def main_app():
    top_bar()
    try:
        df = carregar_dados_desenhos(URL_PLANILHA_DESENHOS)
    except Exception as e:
        st.error(f"Não foi possível carregar a planilha de desenhos: {e}")
        return

    termo_input = st.text_input("Digite parte do nome do desenho (ex: M05B-391):")
    if termo_input:
        resultados = buscar_desenho(df, termo_input)
        desenhos_encontrados = resultados['DESENHO'].unique()

        if len(desenhos_encontrados) > 0:
            st.markdown("### 🔍 Desenhos Encontrados:")
            for desenho in desenhos_encontrados:
                st.subheader(f"📄 {desenho}")
                revisoes = resultados[resultados['DESENHO'] == desenho]['REVISÃO'].drop_duplicates().tolist()
                revisoes_ordenadas = ordenar_revisoes(revisoes)

                st.markdown("**Revisões disponíveis:**")
                if len(revisoes_ordenadas) > 0:
                    cols = st.columns(len(revisoes_ordenadas))
                    ultima_revisao = revisoes_ordenadas[-1]
                    for i, rev in enumerate(revisoes_ordenadas):
                        destaque = (
                            "background-color:#ffd966;color:#000000;" if rev == ultima_revisao
                            else "background-color:#e0e0e0;color:#000000;"
                        )
                        cols[i].markdown(
                            f"<div style='{destaque}padding:6px;border-radius:6px;text-align:center;font-weight:bold;'>{rev}</div>",
                            unsafe_allow_html=True
                        )
                    for i, rev in enumerate(revisoes_ordenadas):
                        if rev == ultima_revisao:
                            cols[i].markdown(
                                "<div style='margin-top:6px;color:#ffd966;font-weight:bold;'>⬆ Esta é a última revisão disponível</div>",
                                unsafe_allow_html=True
                            )
                else:
                    st.info("Nenhuma revisão encontrada para este desenho.")
                st.markdown("---")
        else:
            st.info("Nenhum desenho encontrado com esse trecho.")

# =========================
# ROTEAMENTO
# =========================
def run():
    if require_auth():
        main_app()
    else:
        login_view()

if __name__ == "__main__":
    run()
