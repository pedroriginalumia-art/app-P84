import streamlit as st
import pandas as pd
from PIL import Image
import base64
from io import BytesIO
from datetime import timedelta
import re
import requests
import io

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
# HELPERS
# =========================
def safe_rerun():
    """Usa st.rerun() nas versões novas; cai para st.experimental_rerun() nas antigas."""
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()

def carregar_logo_base64(path: str) -> str:
    """Carrega a imagem e retorna base64 para data:image/png;base64,..."""
    logo = Image.open(path)
    buf = BytesIO()
    logo.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

def render_logo_titulo(titulo: str, subtitulo: str | None = None):
    """
    Cabeçalho com logo e título usando HTML REAL sem indentação (evita virar code block).
    """
    try:
        logo_b64 = carregar_logo_base64("SEATRIUM.png")
        st.markdown(
f"""<div style="display:flex;align-items:center;gap:16px;margin-bottom:20px;">
data:image/png;base64,{logo_b64}
<div>
<h1 style="margin:0;">{titulo}</h1>
{f'<div style="font-size:13px;color:#bbb;margin-top:2px;">{subtitulo}</div>' if subtitulo else ''}
</div>
</div>""",
            unsafe_allow_html=True
        )
    except Exception:
        # fallback sem logo
        st.header(titulo)
        if subtitulo:
            st.caption(subtitulo)

def get_theme_palette():
    """
    Detecta o tema do Streamlit e retorna uma paleta de alto contraste.
    """
    base = st.get_option("theme.base") or "dark"  # 'light' ou 'dark'
    if base == "light":
        return {
            "bg": "#EAF4FF",      # fundo claro com leve azul
            "border": "#1E40AF",  # azul escuro
            "text": "#0F172A",    # quase preto
            "muted": "#334155",   # cinza para subtítulos
            "accent": "#2563EB",  # azul médio
            "panel_dark": "#EAF4FF",
            "shadow": "0 2px 8px rgba(30,64,175,0.12)",
        }
    else:
        return {
            "bg": "#0B1220",      # fundo escuro (alto contraste)
            "border": "#3B82F6",  # azul vivo
            "text": "#F8FAFC",    # quase branco
            "muted": "#CBD5E1",   # cinza claro
            "accent": "#60A5FA",  # azul claro
            "panel_dark": "#0B1220",
            "shadow": "0 2px 12px rgba(0,0,0,0.35)",
        }

def render_welcome_card(nome: str, funcao: str):
    """
    Saudação com alto contraste, adaptada ao tema claro/escuro.
    """
    p = get_theme_palette()
    st.markdown(
f"""<div style="
background:{p['panel_dark']};
border: 1px solid {p['border']};
padding: 16px;
border-radius: 12px;
margin-top: 12px;
box-shadow: {p['shadow']};
">
<div style="font-weight:700; font-size:16px; color:{p['text']}; letter-spacing:0.2px;">
Seja bem-vindo, <span style="color:{p['accent']};">{nome}</span>!
</div>
<div style="font-size:13px; color:{p['muted']}; margin-top:4px;">
{funcao}
</div>
</div>""",
        unsafe_allow_html=True
    )

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
    # baixa conteúdo do RAW (compatível com repositórios públicos)
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
            # Boas-vindas de alto contraste
            render_welcome_card(st.session_state["nome"], st.session_state["funcao"])
            safe_rerun()
        else:
            st.error("Matrícula não encontrada na whitelist. Verifique e tente novamente.")

def top_bar():
    render_logo_titulo("Desenhos P84")

    p = get_theme_palette()
    col1, col2 = st.columns([1, 1])
    with col1:
        nome = st.session_state.get("nome", "—")
        funcao = st.session_state.get("funcao", "")
        st.markdown(
f"""<div style="font-size:13px; color:{p['muted']};">
Usuário: <span style="font-weight:600; color:{p['text']};">{nome}</span>
{f"&nbsp;•&nbsp;<span style='color:{p['muted']};'>{funcao}</span>" if funcao else ""}
</div>""",
            unsafe_allow_html=True
        )
    with col2:
        if st.button("Sair"):
            for k in ["authenticated", "matricula", "nome", "funcao", "login_time"]:
                st.session_state.pop(k, None)
            st.success("Você saiu da sessão.")
            safe_rerun()

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
f"""<div style='{destaque}padding:6px;border-radius:6px;text-align:center;font-weight:bold;'>{rev}</div>""",
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
