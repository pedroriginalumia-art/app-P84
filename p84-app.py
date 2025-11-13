import streamlit as st
import pandas as pd
from datetime import timedelta
import re
import requests
import io
from streamlit.components.v1 import html  # componente para overlay

# =========================
# CONFIGURAÇÕES
# =========================
st.set_page_config(page_title="Desenhos P84", page_icon="📄", layout="centered")

# --- URLs RAW no GitHub ---
RAW_LOGO_URL = "https://raw.githubusercontent.com/pedroriginalumia-art/app-P84/main/SEATRIUM.png"
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

def get_theme_palette():
    """Paleta de alto contraste para claro/escuro."""
    base = st.get_option("theme.base") or "dark"
    if base == "light":
        return {
            "backdrop": "rgba(15, 23, 42, 0.35)",
            "panel": "#FFFFFF",
            "border": "#1E40AF",
            "text": "#0F172A",
            "muted": "#334155",
            "accent": "#2563EB",
            "shadow": "0 10px 30px rgba(30,64,175,0.20)",
            "button_bg": "#1E40AF",
            "button_text": "#FFFFFF",
        }
    else:
        return {
            "backdrop": "rgba(0, 0, 0, 0.55)",
            "panel": "#0B1220",
            "border": "#3B82F6",
            "text": "#F8FAFC",
            "muted": "#CBD5E1",
            "accent": "#60A5FA",
            "shadow": "0 10px 34px rgba(0,0,0,0.40)",
            "button_bg": "#3B82F6",
            "button_text": "#0B1220",
        }

def render_logo_titulo(titulo: str, subtitulo: str | None = None):
    """
    Cabeçalho alinhado à esquerda usando colunas + st.image/st.markdown.
    """
    col_logo, col_texto = st.columns([0.12, 0.88])  # alinha com widgets
    with col_logo:
        try:
            st.image(RAW_LOGO_URL, width=60)
        except Exception:
            st.empty()
    with col_texto:
        st.markdown(f"<h1 style='margin:0; padding:0;'>{titulo}</h1>", unsafe_allow_html=True)
        if subtitulo:
            st.caption(subtitulo)

def normaliza_matricula(valor: str) -> str:
    """Somente dígitos; valida 1 a 5 dígitos."""
    if valor is None:
        return ""
    s = re.sub(r"\D", "", str(valor))
    if len(s) == 0 or len(s) > 5:
        return ""
    return s

# =========================
# WHITELIST (CACHE)
# =========================
@st.cache_data(ttl=600)
def carregar_whitelist_xlsx(url: str) -> pd.DataFrame:
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
# PLANILHA DE DESENHOS (CACHE)
# =========================
@st.cache_data(ttl=600)
def carregar_dados_desenhos(url: str) -> pd.DataFrame:
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
            for k in ["authenticated", "login_time", "matricula", "nome", "funcao", "welcome_open"]:
                st.session_state.pop(k, None)
            st.warning("Sua sessão expirou. Faça login novamente.")
            return False
        return True
    return authenticated

# =========================
# OVERLAY (botão FECHAR **dentro** da caixa)
# =========================
def render_welcome_overlay(nome: str, funcao: str):
    """
    Renderiza uma sobreposição (overlay) completa com backdrop e uma caixa central.
    O botão FECHAR está DENTRO da caixa e fecha o overlay via query params (?welcome=0).
    """
    p = get_theme_palette()

    # HTML completo do overlay (com botão dentro da caixa)
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8" />
      <style>
        .overlay-backdrop {{
          position: fixed; inset: 0;
          background: {p['backdrop']};
          backdrop-filter: blur(2px);
          z-index: 9998;
        }}
        .overlay-box {{
          position: fixed;
          top: 50%; left: 50%;
          transform: translate(-50%, -50%);
          width: min(640px, 88vw);
          background: {p['panel']};
          border: 1px solid {p['border']};
          border-radius: 12px;
          box-shadow: {p['shadow']};
          z-index: 9999;
          padding: 20px 22px 18px 22px;
        }}
        .overlay-title {{
          font-weight: 800;
          font-size: 18px;
          color: {p['text']};
          letter-spacing: 0.2px;
          margin: 0 0 6px 0;
        }}
        .overlay-sub {{
          font-size: 13px;
          color: {p['muted']};
          margin: 0 0 16px 0;
        }}
        .overlay-actions {{
          display: flex;
          justify-content: flex-end;
          margin-top: 4px;
        }}
        .overlay-button {{
          background: {p['button_bg']};
          color: {p['button_text']};
          border: 0;
          border-radius: 8px;
          padding: 10px 16px;
          font-weight: 800;
          letter-spacing: 0.6px;
          text-transform: uppercase;
          cursor: pointer;
        }}
        .overlay-button:active {{ transform: translateY(1px); }}
      </style>
    </head>
    <body>
      <div class="overlay-backdrop"></div>
      <div class="overlay-box">
        <div class="overlay-title">
          Seja bem-vindo, <span style="color:{p['accent']};">{nome}</span>!
        </div>
        <div class="overlay-sub">{funcao}</div>
        <div class="overlay-actions">
          <button class="overlay-button" id="closeBtn">FECHAR</button>
        </div>
      </div>

      <script>
        // Ao clicar, troca o query param welcome=0 e recarrega
        document.getElementById('closeBtn').addEventListener('click', function() {{
          const url = new URL(window.parent.location.href);
          url.searchParams.set('welcome', '0');
          window.parent.location.href = url.toString();
        }});
      </script>
    </body>
    </html>
    """
    # Altura suficiente para cobrir viewport (o componente ocupa o topo da página)
    html(html_content, height=100, scrolling=False)

# =========================
# VIEWS
# =========================
def login_view():
    # Cabeçalho à esquerda, sem "Acesso restrito —"
    render_logo_titulo("Desenhos P84")
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
                "welcome_open": True,
            })
            # Define query param para abrir overlay
            try:
                st.experimental_set_query_params(welcome="1")
            except Exception:
                pass
            safe_rerun()
        else:
            st.error("Matrícula não encontrada na whitelist. Verifique e tente novamente.")

def top_bar():
    render_logo_titulo("Desenhos P84")

    # Linha de usuário + sair
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
            for k in ["authenticated", "matricula", "nome", "funcao", "login_time", "welcome_open"]:
                st.session_state.pop(k, None)
            # Remove query param de overlay
            try:
                st.experimental_set_query_params()
            except Exception:
                pass
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
    # Sincroniza estado do overlay com query params
    try:
        qp = st.experimental_get_query_params()
        if qp.get("welcome", ["0"])[0] == "0":
            st.session_state["welcome_open"] = False
        elif qp.get("welcome", ["0"])[0] == "1":
            st.session_state["welcome_open"] = True
    except Exception:
        pass

    # Cabeçalho + overlay (se aberto)
    top_bar()
    if st.session_state.get("welcome_open", False):
        render_welcome_overlay(
            st.session_state.get("nome", "—"),
            st.session_state.get("funcao", "")
        )

    # Conteúdo principal
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
