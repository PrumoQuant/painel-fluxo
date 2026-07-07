# ============================================================================
# PAINEL DE FLUXO DE OPÇÕES — VERSÃO 3.6 "CALIBRAÇÃO QUANTICO v2" (ESTUDO)
# PrumoQuant · https://prumoquant.streamlit.app
# ============================================================================
# NOVIDADES v3.6 — calibração com dados pareados Quantico (07/07/2026):
#  D5. MULTI-VENCIMENTO: GEX e Time Pressure somam os 6 vencimentos mais
#      próximos (o hedge do dealer existe em todas as datas abertas, não só
#      no 0DTE), cada opção com seu T e peso 1/(1+dias/5) — 0DTE dominante.
#      É o que fecha a divergência de magnitude vs terminal Quantico e deixa
#      os muros mais estáveis/confiáveis para operar.
#  D1. ESCALA GEX corrigida: Γ·OI·100·S² pleno (removido o fator 1%) →
#      magnitudes em B, mesma ordem do terminal de referência.
#  D2. INSTITUTIONAL FLOW por strike agora em NOTIONAL do subjacente
#      (volume·100·S, sinalizado) — é isso que produz a escala B/T deles.
#      O prêmio agressor (K/M) continua na régua e no Volume Imbalance.
#  D3. FILTRO QUANTICO implementado (documentado no tutorial deles):
#      exclui contratos com último/abertura > 2,0 (já lucraram +100%) ou
#      < 0,05 (já perderam −95%) — é o que gera a leitura "Q" exclusiva.
#  D4. VALIDAÇÃO PAREADA 14h01 NY: nosso Time Pressure = $413,6M vs
#      $437,2M deles (SPY 753, versão não-Q) → precisão ~5%. Nossos
#      strikes-chave batem com os painéis não-Q deles (753/730).
#  +  Barras-chave calculadas em janela ±3% do spot (elimina "última
#      exaustão" absurda tipo 800/675 e alinha ▲/▼ com o gráfico).
#  +  NOVO: Gráfico de Níveis — candlestick 1min em tempo real (Tradier)
#      com as linhas do dealer (WALL, TARGET, 1ª positiva/negativa, SETUP 6,
#      FLIP, VWAP) — substitui a limitação do TradingView gratuito.
#  +  Régua Volume Imbalance agora mostra o TOP STRIKE, como no terminal.
#
# NOVIDADES v3.5:
#  1. SEGURANÇA: o token Tradier agora vem de st.secrets["TRADIER_TOKEN"].
#     NUNCA mais colar a chave no código — o repositório é PÚBLICO.
#     (Streamlit Cloud: app → ⋮ → Settings → Secrets → TRADIER_TOKEN = "...")
#  2. TEMPO REAL DE VERDADE: spot e fechamento anterior via /markets/quotes;
#     intraday 1 min via /markets/timesales com session_filter=open (isso
#     também elimina o velho bug do VWAP contaminado pelo pré-mercado).
#     Fallback automático para yfinance (~15 min) se a Tradier falhar.
#  3. ESCALA QUANTICO: GEX = Γ · OI · 100 · S² · 1% (dollar-gamma por 1% de
#     movimento) → magnitudes em B/M, comparáveis ao terminal Quantico.
#  4. NOVO — TIME PRESSURE por strike (item 1.8, v1): charm (decaimento do
#     delta) por strike; calls contribuem +, puts −; picos ATM no 0DTE.
#     Semântica direcional pendente de validação ao vivo (item 1.9).
#  5. NOVO — VOLUME IMBALANCE FLOW: fluxo por strike separado em componentes
#     bull/bear, barras horizontais verde/vermelho como no Quantico.
#  6. REFORMULAÇÃO VISUAL (2.1): trio de mini-painéis por ativo (Delta
#     Hedging · Institutional Flow · Time Pressure) com cabeçalho ▲/▼,
#     barras azuis + maior positiva verde + maior negativa vermelha, linha
#     tracejada no spot; 7 abas; relógios NY/BR com fuso correto (zoneinfo).
#  REGRAS PRESERVADAS: whitelist SPY/QQQ · SOMENTE LEITURA (nenhum endpoint
#  de ordem) · filtros anti-ruído (1% do pico, spread >25%) · veto SPY×QQQ ·
#  6 barras-chave · 6 setups · mentor de disciplina · modo celular.
# ============================================================================

import os
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
from scipy.stats import norm
from streamlit_autorefresh import st_autorefresh

# ----------------------------------------------------------------------------
# CONFIGURAÇÃO DA PÁGINA + ESTILO (hub escuro estilo Quantico)
# ----------------------------------------------------------------------------
st.set_page_config(page_title="PrumoQuant — Fluxo de Opções (estudo)",
                   layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    .stApp { background-color: #0a0d12; }
    section[data-testid="stSidebar"] { background-color: #0e141b; }
    h1, h2, h3, h4, p, span, label { color: #e6edf3; }
    .block-container { padding-top: 1.0rem; max-width: 1560px; }

    /* ---------- Cabeçalho institucional ---------- */
    .pq-header { display: flex; justify-content: space-between;
        align-items: flex-end; padding: 2px 0 10px 0; margin-bottom: 4px;
        border-bottom: 1px solid #1c2733; }
    .pq-logo { font-size: 1.55rem; font-weight: 800; letter-spacing: 1px;
        color: #e6edf3; }
    .pq-logo .fio { color: #fbbf24; }
    .pq-sub { display: block; font-size: 0.72rem; color: #8b98a5;
        letter-spacing: 2px; text-transform: uppercase; margin-top: 2px; }
    .pq-meta { text-align: right; font-size: 0.72rem; color: #8b98a5;
        line-height: 1.6; }

    .selo { display: inline-block; padding: 3px 10px; border-radius: 999px;
        font-size: 0.7rem; font-weight: 700; letter-spacing: 1px; }
    .selo-aberto  { background: #052e16; color: #22c55e; border: 1px solid #14532d; }
    .selo-fechado { background: #450a0a; color: #f87171; border: 1px solid #7f1d1d; }
    .selo-pre     { background: #422006; color: #fbbf24; border: 1px solid #92400e; }

    /* ---------- Abas ---------- */
    .stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid #1c2733; }
    .stTabs [data-baseweb="tab"] { background: transparent; color: #8b98a5;
        font-size: 0.85rem; padding: 8px 14px; border-radius: 8px 8px 0 0; }
    .stTabs [aria-selected="true"] { color: #e6edf3; background: #131a22;
        border-bottom: 2px solid #fbbf24; }

    /* ---------- Mini-painel estilo Quantico ---------- */
    .qpanel-head { display: flex; justify-content: space-between;
        align-items: baseline; padding: 8px 10px 0 10px;
        background: #10161d; border: 1px solid #1e2936; border-bottom: 0;
        border-radius: 10px 10px 0 0; }
    .qpanel-title { font-size: 0.78rem; font-weight: 700; color: #d7dee6; }
    .qpanel-tk { font-size: 0.74rem; color: #8b98a5;
        font-variant-numeric: tabular-nums; }
    .qpanel-tk b { color: #e6edf3; }
    .qpanel-sub { display: flex; gap: 14px; flex-wrap: wrap;
        padding: 2px 10px 6px 10px; background: #10161d;
        border-left: 1px solid #1e2936; border-right: 1px solid #1e2936;
        font-size: 0.72rem; color: #8b98a5;
        font-variant-numeric: tabular-nums; }
    .verde { color: #22c55e !important; }
    .vermelho { color: #ef4444 !important; }
    .amarelo { color: #eab308 !important; }

    /* ---------- Cartões ---------- */
    .cartao { background: linear-gradient(180deg, #131a22 0%, #10161d 100%);
        border: 1px solid #1e2936; border-radius: 10px;
        padding: 10px 12px 8px 12px; height: 100%; }
    .cartao .rotulo { font-size: 0.64rem; letter-spacing: 1.4px;
        text-transform: uppercase; color: #8b98a5; margin-bottom: 2px; }
    .cartao .valor { font-size: 1.2rem; font-weight: 700; color: #e6edf3;
        font-variant-numeric: tabular-nums; }
    .cartao .sub { font-size: 0.7rem; color: #8b98a5; margin-top: 2px; }

    /* ---------- Linha de disciplina ---------- */
    .disciplina { font-size: 0.78rem; color: #9aa7b4; padding: 4px 0 0 0; }
    .disciplina b { color: #fbbf24; font-weight: 700; }

    /* ---------- Linha discreta de setup ---------- */
    .setup-linha { font-size: 0.8rem; padding: 6px 12px; border-radius: 8px;
        background: #10161d; border: 1px solid #1e2936;
        margin: 2px 0 8px 0; color: #c9d4de; }
    .setup-linha b { font-weight: 700; }

    /* ---------- Régua de fluxo (Volume Imbalance) ---------- */
    .fluxobar-wrap { background: #10161d; border: 1px solid #1e2936;
        border-radius: 10px; padding: 8px 12px 10px 12px; margin: 2px 0 8px 0; }
    .fluxobar-top { display: flex; justify-content: space-between;
        flex-wrap: wrap; gap: 4px; font-size: 0.74rem; color: #8b98a5;
        margin-bottom: 6px; }
    .fluxobar { display: flex; height: 8px; border-radius: 999px;
        overflow: hidden; background: #1e2936; }
    .fluxobar .verde-seg { background: #22c55e; }
    .fluxobar .verm-seg { background: #ef4444; }
    .fluxobar-sub { display: flex; justify-content: space-between;
        flex-wrap: wrap; gap: 4px; font-size: 0.74rem; color: #8b98a5;
        margin-top: 6px; }

    /* ---------- Cartão terminal (setups) ---------- */
    .terminal { background: #05100a; border: 1px solid #14532d;
        border-radius: 10px; padding: 16px 20px;
        font-family: 'Consolas', 'Courier New', monospace;
        font-size: 0.88rem; line-height: 1.7; color: #86efac;
        white-space: pre-wrap; margin-bottom: 12px; }
    .terminal .titulo { color: #22c55e; font-weight: 700; }
    .terminal .aviso { color: #6b7280; font-size: 0.76rem; }
    .terminal .destaque { color: #fbbf24; font-weight: 700; }
    .terminal .neg { color: #f87171; font-weight: 700; }

    .alerta-vermelho { border: 1px solid #7f1d1d !important;
        background: #2d1414 !important; }
</style>
""", unsafe_allow_html=True)

# ----------------------------------------------------------------------------
# TOKEN TRADIER — SOMENTE via Secrets (o repositório é público!)
# ----------------------------------------------------------------------------
def obter_token():
    try:
        t = st.secrets.get("TRADIER_TOKEN", "")
        if t:
            return str(t).strip()
    except Exception:
        pass
    return os.environ.get("TRADIER_TOKEN", "").strip()

TRADIER_TOKEN = obter_token()
API_BASE = "https://api.tradier.com/v1"
WHITELIST = {"SPY", "QQQ"}   # trava de segurança §2.1 — nunca ampliar sem dupla confirmação

# ----------------------------------------------------------------------------
# BARRA LATERAL
# ----------------------------------------------------------------------------
st.sidebar.title("Configurações")
MODO_VISAO = st.sidebar.radio("Modo de visão", ["Um ativo", "SPY + QQQ lado a lado"])
TICKER_UNICO = st.sidebar.selectbox("Ativo (modo um ativo)", ["SPY", "QQQ"])
MODO_CELULAR = st.sidebar.checkbox(
    "📱 Modo celular (layout vertical)", value=False,
    help="Barras horizontais e tudo empilhado — muito mais legível em tela estreita.")
st.sidebar.markdown("---")
USAR_R_AUTO = st.sidebar.checkbox(
    "Taxa de juros automática (^IRX)", value=True,
    help="Busca a taxa real do T-bill de 13 semanas no Yahoo. Se falhar, usa o valor manual.")
TAXA_MANUAL = st.sidebar.number_input("Taxa de juros manual (reserva)",
                                      value=0.05, step=0.005, format="%.3f")
MOSTRAR_FUTUROS = st.sidebar.checkbox(
    "Converter níveis para futuros (ES/NQ)", value=True,
    help="Mostra muros e alvos convertidos para o futuro correspondente.")

with st.sidebar.expander("Preferências de exibição"):
    MOSTRAR_VWAP = st.checkbox("Gráfico Preço × VWAP (com bandas)", value=True)
    MODO_BANDAS = st.selectbox("Modo das bandas VWAP",
                               ["Desvio padrão (σ)", "Porcentagem (%)"], index=0)
    BANDAS_QQQ_TXT = st.text_input("Bandas VWAP QQQ (%)", "0.235, 0.47, 0.705")
    BANDAS_SPY_TXT = st.text_input("Bandas VWAP SPY (%)", "0.14, 0.28, 0.42")
    MOSTRAR_TV = st.checkbox("Aba com gráfico TradingView embutido", value=True)

def parse_bandas(txt):
    out = []
    for p in str(txt).replace(";", ",").split(","):
        try:
            v = float(p.strip().replace("%", ""))
            if 0 < v < 5:
                out.append(v)
        except Exception:
            pass
    return out[:3]

BANDAS_VWAP = {"QQQ": parse_bandas(BANDAS_QQQ_TXT), "SPY": parse_bandas(BANDAS_SPY_TXT)}

if TRADIER_TOKEN:
    st.sidebar.caption("🔐 Token Tradier: carregado via Secrets.")
else:
    st.sidebar.caption("⚠️ Token Tradier AUSENTE — configure em Settings → Secrets.")
st.sidebar.caption("Ferramenta de ESTUDO. Painel SOMENTE LEITURA — nenhuma ordem é enviada.")

# ----------------------------------------------------------------------------
# AUXILIARES MATEMÁTICOS E FORMATADORES
# ----------------------------------------------------------------------------
def num(v):
    try:
        x = float(v)
        return 0.0 if pd.isna(x) else x
    except (TypeError, ValueError):
        return 0.0

def fmt_usd(v):
    v = num(v); s = "-" if v < 0 else ""; a = abs(v)
    if a >= 1e12: return f"{s}${a/1e12:.2f}T"
    if a >= 1e9:  return f"{s}${a/1e9:.1f}B"
    if a >= 1e6:  return f"{s}${a/1e6:.1f}M"
    if a >= 1e3:  return f"{s}${a/1e3:.0f}K"
    return f"{s}${a:.0f}"

def fx(v, pref="$", nd=2):
    """Formata número que pode ser None sem quebrar o f-string."""
    return "—" if v is None else f"{pref}{v:.{nd}f}"

def gamma_bs(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return norm.pdf(d1) / (S * sigma * np.sqrt(T))

def charm_bs(S, K, T, r, sigma):
    """Charm = dDelta/dT (decaimento do delta). Base do Time Pressure (1.8 v1)."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    svt = sigma * np.sqrt(T)
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / svt
    d2 = d1 - svt
    return -norm.pdf(d1) * (2.0 * r * T - d2 * svt) / (2.0 * T * svt)

# ----------------------------------------------------------------------------
# CAMADA TRADIER (blindada: timeout 8 s, erros retornados, nunca trava a UI)
# ----------------------------------------------------------------------------
def tradier_get(caminho, params):
    if not TRADIER_TOKEN:
        return None, "token ausente (Settings → Secrets → TRADIER_TOKEN)"
    try:
        r = requests.get(f"{API_BASE}{caminho}", params=params,
                         headers={"Authorization": f"Bearer {TRADIER_TOKEN}",
                                  "Accept": "application/json"},
                         timeout=8)
        if r.status_code == 401:
            return None, "401 Unauthorized — token inválido/expirado (regenere e atualize os Secrets)"
        if r.status_code != 200:
            return None, f"HTTP {r.status_code} em {caminho}"
        return r.json(), None
    except requests.exceptions.Timeout:
        return None, f"timeout (8 s) em {caminho}"
    except Exception as e:
        return None, f"falha de rede: {e}"

def historico_timesales(ticker):
    """Intraday 1 min em TEMPO REAL, só sessão regular (mata o bug do pré-mercado)."""
    hoje = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    j, e = tradier_get("/markets/timesales",
                       {"symbol": ticker, "interval": "1min",
                        "start": f"{hoje} 09:30", "end": f"{hoje} 16:00",
                        "session_filter": "open"})
    if e or not j:
        return None
    serie = j.get("series") or {}
    dados = serie.get("data") if isinstance(serie, dict) else None
    if not dados:
        return None
    if isinstance(dados, dict):
        dados = [dados]
    df = pd.DataFrame(dados)
    if df.empty or "time" not in df.columns:
        return None
    df["time"] = pd.to_datetime(df["time"])
    df = df.set_index("time").rename(columns={"open": "Open", "high": "High",
                                              "low": "Low", "close": "Close",
                                              "volume": "Volume"})
    if not all(c in df.columns for c in ("High", "Low", "Close", "Volume")):
        return None
    cols = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in df.columns]
    return df[cols]

def historico_yf(ticker):
    """Fallback (~15 min de atraso). prepost=False protege o VWAP."""
    try:
        return yf.Ticker(ticker).history(period="1d", interval="1m", prepost=False)
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=20, show_spinner=False)
def buscar_dados(ticker):
    """Quotes + timesales + cadeia de opções. Retorna dict; erros como texto."""
    if ticker not in WHITELIST:
        return {"erro": f"{ticker} fora da whitelist (SPY/QQQ) — trava §2.1."}
    erros, fonte = [], "Tradier · tempo real"
    spot = prev = None

    # 1) Cotação em tempo real
    j, e = tradier_get("/markets/quotes", {"symbols": ticker})
    if e:
        erros.append(f"quotes: {e}")
    else:
        q = (j.get("quotes") or {}).get("quote")
        if isinstance(q, list):
            q = q[0] if q else None
        if isinstance(q, dict):
            spot = num(q.get("last")) or None
            prev = num(q.get("prevclose")) or None

    # 2) Intraday para VWAP
    hist = historico_timesales(ticker)
    if hist is None or hist.empty:
        hist = historico_yf(ticker)
        if spot is None and hist is not None and not hist.empty:
            spot = float(hist["Close"].iloc[-1])
            fonte = "yfinance · ~15 min"

    # 3) Cadeia de opções — MULTI-VENCIMENTO (D5): soma os próximos vencimentos
    #    para casar a magnitude do dealer com a Quantico (o hedge existe em todas
    #    as datas abertas, não só no 0DTE). Guardamos o venc de cada opção para
    #    calcular o T certo de cada uma. NVENC controla quantos vencimentos entram.
    NVENC = 6
    calls = puts = None
    venc = None          # vencimento mais próximo (0DTE), usado para 0DTE flag e rótulo
    vencs = []
    j, e = tradier_get("/markets/options/expirations", {"symbol": ticker})
    if e:
        erros.append(f"expirations: {e}")
    else:
        exp = (j.get("expirations") or {})
        datas = exp.get("date") if isinstance(exp, dict) else None
        if datas:
            if isinstance(datas, str):
                datas = [datas]
            vencs = list(datas)[:NVENC]
            venc = vencs[0] if vencs else None

    frames = []
    for vc in vencs:
        j, e = tradier_get("/markets/options/chains",
                           {"symbol": ticker, "expiration": vc, "greeks": "true"})
        if e:
            erros.append(f"chains {vc}: {e}")
            continue
        ops = ((j.get("options") or {}) or {}).get("option", [])
        if isinstance(ops, dict):
            ops = [ops]
        dfc = pd.DataFrame(ops)
        if dfc.empty:
            continue
        dfc = dfc.rename(columns={"open_interest": "openInterest", "last": "lastPrice"})
        dfc["venc_opt"] = vc          # ← vencimento desta opção (para o T individual)
        if "greeks" in dfc.columns:
            def _iv(g):
                if isinstance(g, dict):
                    for chave in ("mid_iv", "smv_vol", "ask_iv", "bid_iv"):
                        v = num(g.get(chave))
                        if v > 0:
                            return v
                return 0.0
            dfc["impliedVolatility"] = dfc["greeks"].apply(_iv)
        else:
            dfc["impliedVolatility"] = 0.0
        frames.append(dfc)

    if frames:
        todas = pd.concat(frames, ignore_index=True)
        calls = todas[todas["option_type"] == "call"].copy()
        puts = todas[todas["option_type"] == "put"].copy()

    return {"spot": spot, "prev": prev, "hist": hist, "calls": calls,
            "puts": puts, "venc": venc, "vencs": vencs, "fonte": fonte, "erros": erros}

@st.cache_data(ttl=3600, show_spinner=False)
def taxa_juros_automatica():
    try:
        h = yf.Ticker("^IRX").history(period="5d")
        if not h.empty:
            return float(h["Close"].iloc[-1]) / 100.0
    except Exception:
        pass
    return None

@st.cache_data(ttl=60, show_spinner=False)
def razao_futuro(ticker, spot_etf):
    mapa = {"SPY": ("ES=F", "ES / MES"), "QQQ": ("NQ=F", "NQ / MNQ")}
    if ticker not in mapa or not spot_etf:
        return None, None, None
    simbolo, nome = mapa[ticker]
    try:
        tkf = yf.Ticker(simbolo)
        preco_fut = None
        for per, itv in (("1d", "1m"), ("5d", "1h"), ("10d", "1d")):
            fut = tkf.history(period=per, interval=itv, prepost=True)
            if not fut.empty:
                preco_fut = float(fut["Close"].iloc[-1])
                break
        if not preco_fut:
            return None, None, None
        return nome, preco_fut, preco_fut / spot_etf
    except Exception:
        return None, None, None

# ----------------------------------------------------------------------------
# ANÁLISES: VWAP · GEX · TIME PRESSURE · FLUXO · BARRAS-CHAVE · SETUPS
# ----------------------------------------------------------------------------
def calcular_vwap(hist):
    mask = [(t.time() >= dtime(9, 30)) and (t.time() <= dtime(16, 0)) for t in hist.index]
    h = hist[mask] if any(mask) else hist
    tipico = (h["High"] + h["Low"] + h["Close"]) / 3
    vol = h["Volume"]
    cum_v = vol.cumsum().replace(0, np.nan)
    vwap = (tipico * vol).cumsum() / cum_v
    var = (tipico ** 2 * vol).cumsum() / cum_v - vwap ** 2
    return h.index, vwap.ffill(), np.sqrt(var.clip(lower=0)).ffill()

def identificar_barras_chave(df, spot, col="gex", faixa=0.03):
    """6 barras-chave (primeira/maior/última, + e −) dentro de ±faixa do spot.
    A janela ±3% alinha o ▲/▼ do cabeçalho com o gráfico e elimina extremos
    sem relevância operacional (ex.: 'última exaustão' a 7% do preço)."""
    b = {}
    if df is None or df.empty or col not in df.columns:
        return b
    df = df[(df["strike"] >= spot * (1 - faixa)) & (df["strike"] <= spot * (1 + faixa))]
    if df.empty:
        return b
    pos = df[df[col] > 0].copy()
    neg = df[df[col] < 0].copy()
    if not pos.empty:
        b["maior_pos"] = float(pos.loc[pos[col].idxmax(), "strike"])
        pos["dist"] = (pos["strike"] - spot).abs()
        b["primeira_pos"] = float(pos.loc[pos["dist"].idxmin(), "strike"])
        b["ultima_pos"] = float(pos["strike"].max())
    if not neg.empty:
        b["maior_neg"] = float(neg.loc[neg[col].idxmin(), "strike"])
        neg["dist"] = (neg["strike"] - spot).abs()
        b["primeira_neg"] = float(neg.loc[neg["dist"].idxmin(), "strike"])
        b["ultima_neg"] = float(neg["strike"].min())
    return b

def calcular_gex(calls, puts, spot, venc_str, r):
    """GEX por strike — dollar-gamma PLENO (Γ·OI·100·S²) somado sobre MÚLTIPLOS
    vencimentos (D5). Cada opção usa o T do seu próprio vencimento (venc_opt) e
    um peso que decai com a distância da data — o 0DTE continua dominante, mas os
    vencimentos seguintes engrossam os muros até a magnitude do terminal Quantico."""
    hoje = pd.Timestamp.now()
    linhas = []
    for df, tipo in ((calls, "call"), (puts, "put")):
        if df is None or df.empty:
            continue
        tem_venc = "venc_opt" in df.columns
        for _, op in df.iterrows():
            k = num(op.get("strike"))
            iv = num(op.get("impliedVolatility"))
            oi = num(op.get("openInterest"))
            if iv <= 0 or oi <= 0 or not (spot * 0.90 <= k <= spot * 1.10):
                continue
            vopt = op.get("venc_opt") if tem_venc else venc_str
            dias = max((pd.Timestamp(vopt) - hoje).days, 0)
            T = max(dias / 252, 0.5 / 252)
            peso = 1.0 / (1.0 + dias / 5.0)     # 0DTE=1,0 · ~1sem≈0,5 · ~1mês≈0,2
            g = gamma_bs(spot, k, T, r, iv) * oi * 100 * spot * spot * peso
            linhas.append({"strike": k, "gex": g if tipo == "call" else -g})

    gex_df = pd.DataFrame(linhas)
    if gex_df.empty:
        return gex_df, None, None, None, None, False

    por_strike = gex_df.groupby("strike")["gex"].sum().reset_index()
    pico = por_strike["gex"].abs().max()
    if pico > 0:  # filtro A (anti-chuvisco): descarta barras < 1% do pico
        por_strike = por_strike[por_strike["gex"].abs() >= 0.01 * pico]
    por_strike = por_strike.sort_values("strike").reset_index(drop=True)
    if por_strike.empty:
        return por_strike, None, None, None, None, False

    gmax, gmin = float(por_strike["gex"].max()), float(por_strike["gex"].min())
    call_wall = float(por_strike.loc[por_strike["gex"].idxmax(), "strike"]) if gmax > 0 else None
    put_wall = float(por_strike.loc[por_strike["gex"].idxmin(), "strike"]) if gmin < 0 else None

    acum = por_strike["gex"].cumsum().values
    cruz = [float(por_strike["strike"].iloc[i]) for i in range(1, len(acum))
            if (acum[i - 1] < 0 <= acum[i]) or (acum[i - 1] >= 0 > acum[i])]
    if cruz:
        flip, dominio = min(cruz, key=lambda k: abs(k - spot)), None
    else:
        flip, dominio = None, ("neg" if acum[-1] < 0 else "pos")

    try:
        venc_hoje = (pd.Timestamp(venc_str).date() == pd.Timestamp.now().date())
    except Exception:
        venc_hoje = False
    return por_strike, call_wall, put_wall, flip, dominio, venc_hoje

def calcular_time_pressure(calls, puts, spot, venc_str, r):
    """Time Pressure por strike (1.8): charm/dia × OI × 100 × S, somado sobre
    múltiplos vencimentos (D5) com T individual e o mesmo peso decrescente do GEX.
    Calls +, puts −. Positivo = decaimento magnetiza p/ cima; picos = alívio → pullback."""
    hoje = pd.Timestamp.now()
    linhas = []
    for df, tipo in ((calls, "call"), (puts, "put")):
        if df is None or df.empty:
            continue
        tem_venc = "venc_opt" in df.columns
        for _, op in df.iterrows():
            k = num(op.get("strike"))
            iv = num(op.get("impliedVolatility"))
            oi = num(op.get("openInterest"))
            if iv <= 0 or oi <= 0 or not (spot * 0.90 <= k <= spot * 1.10):
                continue
            vopt = op.get("venc_opt") if tem_venc else venc_str
            dias = max((pd.Timestamp(vopt) - hoje).days, 0)
            T = max(dias / 252, 0.5 / 252)
            peso = 1.0 / (1.0 + dias / 5.0)
            c = abs(charm_bs(spot, k, T, r, iv)) / 252.0 * oi * 100 * spot * peso
            linhas.append({"strike": k, "tp": c if tipo == "call" else -c})
    dft = pd.DataFrame(linhas)
    if dft.empty:
        return dft
    dft = dft.groupby("strike")["tp"].sum().reset_index()
    pico = dft["tp"].abs().max()
    if pico > 0:
        dft = dft[dft["tp"].abs() >= 0.01 * pico]
    return dft.sort_values("strike").reset_index(drop=True)

def calcular_fluxo_institucional(calls, puts, spot):
    """Classificação pelos terços do spread, com duas calibrações Quantico:
    — Descoberta 3 (FILTRO Q, documentado no tutorial deles): exclui contratos
      cujo último/abertura > 2,0 (já lucraram +100%) ou < 0,05 (já perderam
      −95%). É essa limpeza que gera a leitura 'Q' exclusiva do terminal.
    — Descoberta 2 (NOTIONAL): além do prêmio (K/M, para a régua e o Volume
      Imbalance), calcula o notional do subjacente (volume·100·S, sinalizado),
      que é a escala B dos painéis Institutional Flow Q.
    bull = call comprada OU put vendida · bear = put comprada OU call vendida."""
    comp = vend = 0.0
    mapa = {}
    for df, tipo in ((calls, "call"), (puts, "put")):
        if df is None or df.empty:
            continue
        for _, row in df.iterrows():
            k = num(row.get("strike"))
            vol = num(row.get("volume"))
            bid = num(row.get("bid"))
            ask = num(row.get("ask"))
            ultimo = num(row.get("lastPrice"))
            if vol <= 0 or ask <= 0 or bid < 0 or bid >= ask or ultimo <= 0:
                continue
            abertura = num(row.get("open"))
            if abertura > 0:                      # ← FILTRO QUANTICO (Descoberta 3)
                razao = ultimo / abertura
                if razao > 2.0 or razao < 0.05:   # +100% de lucro ou −95% de perda
                    continue                       # contrato exaurido distorce o hedge
            mid = (bid + ask) / 2.0
            if mid <= 0 or (ask - bid) / mid > 0.25:   # filtro anti-spread esticado
                continue
            spread = ask - bid
            terco_baixo = bid + spread / 3.0
            terco_alto = ask - spread / 3.0
            premio = ultimo * vol * 100
            notional = vol * 100 * spot           # ← escala B (Descoberta 2)
            entrada = mapa.setdefault(k, {"bull": 0.0, "bear": 0.0, "ntl": 0.0})
            if ultimo >= terco_alto:      # negociado perto do ask = agressão compradora
                if tipo == "call":
                    comp += premio; entrada["bull"] += premio; entrada["ntl"] += notional
                else:
                    vend += premio; entrada["bear"] += premio; entrada["ntl"] -= notional
            elif ultimo <= terco_baixo:   # negociado perto do bid = agressão vendedora
                if tipo == "call":
                    vend += premio; entrada["bear"] += premio; entrada["ntl"] -= notional
                else:
                    comp += premio; entrada["bull"] += premio; entrada["ntl"] += notional
    linhas = [{"strike": k, "bull": v["bull"], "bear": v["bear"],
               "net": v["bull"] - v["bear"], "notional": v["ntl"]}
              for k, v in mapa.items()]
    if not linhas:
        return comp, vend, pd.DataFrame(
            columns=["strike", "bull", "bear", "net", "notional"])
    dff = pd.DataFrame(linhas).sort_values("strike").reset_index(drop=True)
    return comp, vend, dff

def detectar_setup(barras, spot, flip, dominio, cw, pw):
    if not barras:
        return None
    def perto(strike, tol=0.0020):
        return strike is not None and (abs(spot - strike) / spot) < tol

    pp, mp, up = barras.get("primeira_pos"), barras.get("maior_pos"), barras.get("ultima_pos")
    pn, mn, un = barras.get("primeira_neg"), barras.get("maior_neg"), barras.get("ultima_neg")

    if pn and perto(pn) and spot >= pn and mp and mp > spot:
        return dict(codigo="S6", nome="Proteção no Hedge Negativo", vies="COMPRADOR (bounce)",
                    gatilho=f"preço testando a 1ª barra− ({pn:.0f}) com ímã positivo em {mp:.0f} acima",
                    alvo=f"{mp:.0f} (ímã) / retorno ao VWAP",
                    invalidacao=f"perder {pn:.0f} com fluxo vendedor (defesa falhou)")
    if un and perto(un) and spot <= (mn or un):
        return dict(codigo="S4", nome="Pullback no Fundo", vies="COMPRADOR (bounce/reversão)",
                    gatilho=f"preço na última barra− ({un:.0f}) — exaustão da venda",
                    alvo=f"{mp:.0f} (ímã acima)" if mp else "VWAP / ímã acima",
                    invalidacao=f"aceitação abaixo de {un:.0f} (flush continua)")
    if up and perto(up) and mp and mp < spot:
        return dict(codigo="S3", nome="Pullback no Topo", vies="VENDEDOR (recuo ao ímã)",
                    gatilho=f"preço na última barra+ ({up:.0f}) com ímã em {mp:.0f} abaixo",
                    alvo=f"{mp:.0f} (ímã abaixo)",
                    invalidacao=f"romper e sustentar acima de {up:.0f}")
    if flip and spot > flip and mp and mp > spot:
        return dict(codigo="S1", nome="Rompimento Altista", vies="COMPRADOR (momentum)",
                    gatilho=f"preço cruzou o flip ({flip:.0f}) com ímã {mp:.0f} acima aberto",
                    alvo=f"{mp:.0f} (maior+)",
                    invalidacao=f"voltar para baixo do flip ({flip:.0f})")
    if pn and spot < pn:
        return dict(codigo="S2", nome="Rompimento Baixista", vies="VENDEDOR (short/flush)",
                    gatilho=f"preço perdeu a 1ª barra− ({pn:.0f}) e entrou em terreno aberto",
                    alvo=f"{mn:.0f} (maior− abaixo)" if mn else "última barra−",
                    invalidacao=f"recuperar e aceitar acima de {pn:.0f}")
    if mp and mn and mn <= spot <= mp:
        return dict(codigo="S5", nome="Consolidação (Pinning)", vies="NEUTRO (disputa/range)",
                    gatilho=f"preço preso entre o ímã+ ({mp:.0f}) e o ímã− ({mn:.0f})",
                    alvo=f"extremos ({mn:.0f} a {mp:.0f})",
                    invalidacao="romper um dos extremos")
    return None

# ----------------------------------------------------------------------------
# MENTOR DE DISCIPLINA — as 15 regras do operador
# ----------------------------------------------------------------------------
DISCIPLINA = [
    "Limite de loss diário atingido = DESLIGA. Amanhã tem mais.",
    "Constância vale mais que ganância.",
    "Não opere contra o mercado.",
    "NUNCA mova o stop achando que recupera.",
    "Aceite a dor, desligue o PC, vá malhar.",
    "Sem alavancagem: regras para aguentar 15 dias ruins.",
    "Saque e materialize a vitória.",
    "Perder faz parte — o mercado move trilhões.",
    "Ninguém fica rico do dia para a noite.",
    "Overtrading é em conta separada de idiota — nunca na conta séria.",
    "Trade não é bet nem cassino: técnica + emocional.",
    "Perdeu? Não culpe a família nem a estratégia.",
    "90% perdem por indisciplina.",
    "Opere pequeno SEMPRE; múltiplas contas.",
    "O dinheiro sai de alguém para você: foco.",
]

# ----------------------------------------------------------------------------
# COMPONENTES VISUAIS (estilo Quantico)
# ----------------------------------------------------------------------------
def selo_mercado(t_ny):
    wd, tt = t_ny.weekday(), t_ny.time()
    if wd < 5 and dtime(9, 30) <= tt < dtime(16, 0):
        return '<span class="selo selo-aberto">MERCADO ABERTO</span>'
    if wd < 5 and dtime(4, 0) <= tt < dtime(9, 30):
        return '<span class="selo selo-pre">PRÉ-MERCADO</span>'
    return '<span class="selo selo-fechado">MERCADO FECHADO</span>'

def regua_fluxo_html(comp, vend, fluxo_df=None):
    tot = comp + vend
    p_comp = (comp / tot * 100) if tot > 0 else 50.0
    p_vend = 100.0 - p_comp
    net_dia = comp - vend
    if p_comp > 60:
        status, classe = "INSTITUIÇÕES COMPRANDO AGORA", "verde"
    elif p_vend > 60:
        status, classe = "INSTITUIÇÕES VENDENDO AGORA", "vermelho"
    else:
        status, classe = "EM DISPUTA NEUTRA", "amarelo"
    # NET por-strike do topo (base da Quantico): o strike de maior |net| do dia.
    top_txt, net_top, cor_net = "", None, "amarelo"
    if fluxo_df is not None and not fluxo_df.empty and "net" in fluxo_df.columns:
        i = fluxo_df["net"].abs().idxmax()
        k_top = float(fluxo_df.loc[i, "strike"])
        net_top = float(fluxo_df.loc[i, "net"])
        cor_net = "verde" if net_top >= 0 else "vermelho"
        top_txt = (f' · TOP STRIKE <span class="{cor_net}">{k_top:.0f} '
                   f'({fmt_usd(net_top)})</span>')
    # Linha inferior: NET do topo em destaque (como no terminal) + total do dia discreto.
    if net_top is not None:
        net_html = (f'<span class="{cor_net}">NET (topo): {fmt_usd(net_top)}</span>'
                    f'<span style="color:#6b7280"> · dia {fmt_usd(net_dia)}</span>')
    else:
        net_html = (f'<span class="{"verde" if net_dia >= 0 else "vermelho"}">'
                    f'NET: {fmt_usd(net_dia)}</span>')
    return f"""
    <div class="fluxobar-wrap">
        <div class="fluxobar-top">
            <span><b>VOLUME IMBALANCE (prêmio agressor)</b>{top_txt}</span>
            <span class="{classe}"><b>{status}</b></span>
        </div>
        <div class="fluxobar">
            <div class="verde-seg" style="width: {p_comp:.1f}%"></div>
            <div class="verm-seg" style="width: {p_vend:.1f}%"></div>
        </div>
        <div class="fluxobar-sub">
            <span class="verde">▲ {p_comp:.1f}% ({fmt_usd(comp)})</span>
            {net_html}
            <span class="vermelho">▼ {p_vend:.1f}% ({fmt_usd(vend)})</span>
        </div>
    </div>"""

def cabecalho_painel(titulo, tk, spot, df, col, barras):
    mp, mn = barras.get("maior_pos"), barras.get("maior_neg")
    hora = datetime.now(ZoneInfo("America/New_York")).strftime("%H:%M")
    up = dn = ""
    if mp is not None and df is not None and not df.empty:
        v = float(df.loc[df["strike"] == mp, col].sum())
        up = f'<span class="verde">▲ {mp:.2f} <b>{fmt_usd(v)}</b></span>'
    if mn is not None and df is not None and not df.empty:
        v = float(df.loc[df["strike"] == mn, col].sum())
        dn = f'<span class="vermelho">▼ {mn:.2f} <b>{fmt_usd(v)}</b></span>'
    return f"""
    <div class="qpanel-head">
        <span class="qpanel-title">{titulo}</span>
        <span class="qpanel-tk">{tk} <b>{spot:.2f}</b></span>
    </div>
    <div class="qpanel-sub"><span>{hora} NY</span>{up}{dn}</div>"""

def grafico_barras_quantico(df, col, spot, barras, altura=260, horizontal=False):
    mp, mn = barras.get("maior_pos"), barras.get("maior_neg")
    cores = []
    for _, linha in df.iterrows():
        k, v = float(linha["strike"]), float(linha[col])
        if mp is not None and abs(k - mp) < 1e-9 and v > 0:
            cores.append("#22c55e")        # maior barra positiva = verde (ímã)
        elif mn is not None and abs(k - mn) < 1e-9 and v < 0:
            cores.append("#ef4444")        # maior barra negativa = vermelho
        else:
            cores.append("#3b82f6")        # padrão Quantico: azul
    fig = go.Figure()
    if horizontal:
        fig.add_trace(go.Bar(y=df["strike"], x=df[col], orientation="h",
                             marker_color=cores))
        fig.add_hline(y=spot, line_dash="dash", line_color="#94a3b8", line_width=1)
    else:
        fig.add_trace(go.Bar(x=df["strike"], y=df[col], marker_color=cores))
        fig.add_vline(x=spot, line_dash="dash", line_color="#94a3b8", line_width=1)
    fig.update_traces(marker_line_width=0)
    fig.update_layout(template="plotly_dark",
                      paper_bgcolor="#10161d", plot_bgcolor="#10161d",
                      margin=dict(l=6, r=6, t=4, b=6), height=altura,
                      showlegend=False,
                      xaxis=dict(gridcolor="#1c2733", zerolinecolor="#26313d"),
                      yaxis=dict(gridcolor="#1c2733", zerolinecolor="#26313d"))
    return fig

def painel_quantico(titulo, tk, spot, df, col, barras, key,
                    altura=260, faixa=0.03, horizontal=False):
    st.markdown(cabecalho_painel(titulo, tk, spot, df, col, barras),
                unsafe_allow_html=True)
    if df is None or df.empty:
        st.caption("Sem dados suficientes neste momento.")
        return
    dfv = df[(df["strike"] >= spot * (1 - faixa)) & (df["strike"] <= spot * (1 + faixa))]
    if dfv.empty:
        dfv = df
    fig = grafico_barras_quantico(dfv, col, spot, barras,
                                  altura=altura, horizontal=horizontal)
    st.plotly_chart(fig, use_container_width=True, key=key,
                    config={"displayModeBar": False})

def grafico_imbalance(dff, spot, cw, pw, alvo, altura=440):
    """Volume Imbalance Flow por strike: bear (vermelho, esq.) × bull (verde, dir.)."""
    if dff is None or dff.empty:
        return None
    df = dff[(dff["strike"] >= spot * 0.985) & (dff["strike"] <= spot * 1.015)].copy()
    if df.empty:
        df = dff.copy()
    df["tot"] = df["bull"] + df["bear"]
    df = df.sort_values("tot", ascending=False).head(14).sort_values("strike")
    fig = go.Figure()
    fig.add_trace(go.Bar(y=df["strike"], x=-df["bear"], orientation="h",
                         marker_color="#ef4444", name="Bearish",
                         text=[fmt_usd(v) for v in df["bear"]],
                         textposition="outside", textfont=dict(size=9)))
    fig.add_trace(go.Bar(y=df["strike"], x=df["bull"], orientation="h",
                         marker_color="#22c55e", name="Bullish",
                         text=[fmt_usd(v) for v in df["bull"]],
                         textposition="outside", textfont=dict(size=9)))
    fig.add_hline(y=spot, line_dash="dot", line_color="#e6edf3", line_width=1)
    if alvo:
        fig.add_hline(y=alvo, line_dash="dash", line_color="#3b82f6", line_width=1)
    if cw:
        fig.add_hline(y=cw, line_color="#a78bfa", line_width=1)
    if pw:
        fig.add_hline(y=pw, line_color="#a78bfa", line_width=1)
    fig.update_layout(template="plotly_dark", barmode="relative",
                      paper_bgcolor="#10161d", plot_bgcolor="#10161d",
                      margin=dict(l=6, r=6, t=6, b=6), height=altura,
                      showlegend=False,
                      xaxis=dict(gridcolor="#1c2733", zerolinecolor="#26313d"),
                      yaxis=dict(gridcolor="#1c2733", dtick=1))
    return fig

def grafico_niveis(hist, spot, cw, pw, flip, b_gex, vwap_val, tk, altura=560):
    """Gráfico de Níveis: candlestick 1min em tempo real (Tradier) com as linhas
    do dealer sobrepostas. Resolve a limitação do TradingView gratuito (atraso de
    15 min e ausência dos níveis de opções). NÃO é liquidez passiva do DOM de
    futuros (isso é a Fase 7 e exige feed Databento/Rithmic) — são os níveis de
    Delta-Hedging projetados sobre o preço, que é o que dá para fazer sem custo."""
    if hist is None or hist.empty or "Open" not in hist.columns:
        return None
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=hist.index, open=hist["Open"], high=hist["High"],
        low=hist["Low"], close=hist["Close"], name=tk,
        increasing_line_color="#22c55e", decreasing_line_color="#ef4444"))
    niveis = [
        (cw, "#a78bfa", "WALL (call)"),
        (pw, "#a78bfa", "WALL (put)"),
        (b_gex.get("maior_pos"), "#3b82f6", "TARGET (ímã+)"),
        (b_gex.get("primeira_pos"), "#22c55e", "1ª POSITIVA"),
        (b_gex.get("primeira_neg"), "#ef4444", "1ª NEGATIVA"),
        (b_gex.get("maior_neg"), "#f97316", "SETUP 6 / defesa"),
        (flip, "#eab308", "FLIP"),
        (vwap_val, "#fbbf24", "VWAP"),
    ]
    vistos = set()
    for nivel, cor, rotulo in niveis:
        if nivel is None or round(nivel, 2) in vistos:
            continue
        vistos.add(round(nivel, 2))
        fig.add_hline(y=nivel, line_color=cor, line_width=1,
                      line_dash="dot" if rotulo == "VWAP" else "solid",
                      annotation_text=f"{rotulo} {nivel:.2f}",
                      annotation_position="right",
                      annotation_font_size=9, annotation_font_color=cor)
    fig.update_layout(template="plotly_dark", xaxis_rangeslider_visible=False,
                      paper_bgcolor="#0a0d12", plot_bgcolor="#0a0d12",
                      margin=dict(l=6, r=90, t=6, b=6), height=altura,
                      showlegend=False,
                      xaxis=dict(gridcolor="#141c26"),
                      yaxis=dict(gridcolor="#141c26", side="right"))
    return fig


def grafico_vwap(hist, modo_bandas, bandas_pct, altura=330):
    idx, vwap_ser, sigma_ser = calcular_vwap(hist)
    h = hist.loc[idx]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=idx, y=h["Close"], name="Preço",
                             line=dict(color="#e6edf3", width=1.6)))
    fig.add_trace(go.Scatter(x=idx, y=vwap_ser, name="VWAP",
                             line=dict(color="#fbbf24", width=1.4)))
    if modo_bandas.startswith("Desvio"):
        for mult in (1, 2, 3):
            for sinal in (1, -1):
                fig.add_trace(go.Scatter(
                    x=idx, y=vwap_ser + sinal * mult * sigma_ser,
                    name=f"{'+' if sinal > 0 else '−'}{mult}σ",
                    line=dict(color="#3b82f6", width=0.8, dash="dot"),
                    opacity=max(0.25, 0.8 - 0.22 * mult), showlegend=False))
    else:
        for p in bandas_pct:
            for sinal in (1, -1):
                fig.add_trace(go.Scatter(
                    x=idx, y=vwap_ser * (1 + sinal * p / 100.0),
                    name=f"{'+' if sinal > 0 else '−'}{p}%",
                    line=dict(color="#3b82f6", width=0.8, dash="dot"),
                    opacity=0.5, showlegend=False))
    fig.update_layout(template="plotly_dark",
                      paper_bgcolor="#10161d", plot_bgcolor="#10161d",
                      margin=dict(l=6, r=6, t=8, b=6), height=altura,
                      legend=dict(orientation="h", y=1.08),
                      xaxis=dict(gridcolor="#1c2733"),
                      yaxis=dict(gridcolor="#1c2733"))
    return fig

def tabela_barras_md(b):
    def f(v):
        return f"{v:.2f}" if v is not None else "—"
    return ("| Barra | Positiva (defesa passiva) | Negativa (defesa ativa) |\n"
            "|---|---|---|\n"
            f"| **Primeira** (linha de defesa) | {f(b.get('primeira_pos'))} | {f(b.get('primeira_neg'))} |\n"
            f"| **Maior** (ímã / alvo) | {f(b.get('maior_pos'))} | {f(b.get('maior_neg'))} |\n"
            f"| **Última** (exaustão) | {f(b.get('ultima_pos'))} | {f(b.get('ultima_neg'))} |")

def cartao_html(rotulo, valor, sub=""):
    sub_html = f'<div class="sub">{sub}</div>' if sub else ""
    return f'<div class="cartao"><div class="rotulo">{rotulo}</div><div class="valor">{valor}</div>{sub_html}</div>'

# ----------------------------------------------------------------------------
# EXECUÇÃO PRINCIPAL
# ----------------------------------------------------------------------------
agora_ny = datetime.now(ZoneInfo("America/New_York"))
agora_br = datetime.now(ZoneInfo("America/Sao_Paulo"))
janela_quente = (agora_ny.time() >= dtime(9, 0)) and (agora_ny.time() <= dtime(9, 45))
st_autorefresh(interval=30000 if janela_quente else 60000, key="pq_refresh")

tickers_para_rodar = ["SPY", "QQQ"] if MODO_VISAO == "SPY + QQQ lado a lado" else [TICKER_UNICO]
r_global = taxa_juros_automatica() if USAR_R_AUTO else TAXA_MANUAL
origem_r = "^IRX automático" if (USAR_R_AUTO and r_global is not None) else "manual"
if r_global is None:
    r_global = TAXA_MANUAL

# --- Coleta e derivação por ativo -------------------------------------------
dados_ativos, falhas = {}, {}
for tk in tickers_para_rodar:
    bruto = buscar_dados(tk)
    if bruto.get("erro"):
        falhas[tk] = bruto["erro"]
        continue
    spot, hist = bruto["spot"], bruto["hist"]
    calls, puts, venc = bruto["calls"], bruto["puts"], bruto["venc"]
    if spot is None or venc is None or calls is None or calls.empty:
        falhas[tk] = " · ".join(bruto["erros"]) if bruto["erros"] else \
            "cadeia de opções indisponível no momento"
        continue

    por_strike, cw, pw, flip, dominio, v_hoje = calcular_gex(calls, puts, spot, venc, r_global)
    b_gex = identificar_barras_chave(por_strike, spot, "gex")
    tp_df = calcular_time_pressure(calls, puts, spot, venc, r_global)
    b_tp = identificar_barras_chave(tp_df, spot, "tp")
    comp, vend, fluxo_df = calcular_fluxo_institucional(calls, puts, spot)
    b_fluxo = identificar_barras_chave(fluxo_df, spot, "notional")

    vwap_val = sigma_val = None
    if hist is not None and not hist.empty:
        _, vwap_ser, sigma_ser = calcular_vwap(hist)
        if not vwap_ser.empty and pd.notna(vwap_ser.iloc[-1]):
            vwap_val = float(vwap_ser.iloc[-1])
            sigma_val = float(sigma_ser.iloc[-1]) if pd.notna(sigma_ser.iloc[-1]) else 0.0

    setup = detectar_setup(b_gex, spot, flip, dominio, cw, pw)
    dados_ativos[tk] = dict(spot=spot, prev=bruto["prev"], hist=hist, venc=venc,
                            fonte=bruto["fonte"], por_strike=por_strike, cw=cw,
                            pw=pw, flip=flip, dominio=dominio, dte0=v_hoje,
                            b_gex=b_gex, tp_df=tp_df, b_tp=b_tp, comp=comp,
                            vend=vend, fluxo_df=fluxo_df, b_fluxo=b_fluxo,
                            vwap=vwap_val, sigma=sigma_val, setup=setup)

# --- Cabeçalho ---------------------------------------------------------------
fonte_geral = "● Tempo real Tradier" if dados_ativos and all(
    d["fonte"].startswith("Tradier") for d in dados_ativos.values()) else "● Fallback yfinance (~15 min)"
cor_fonte = "#22c55e" if fonte_geral.startswith("● Tempo") else "#fbbf24"
st.markdown(f"""
<div class="pq-header">
    <div>
        <span class="pq-logo">Prumo<span class="fio">Quant</span>
        <small style="font-size:0.8rem;color:#6b7280;">v3.6</small></span>
        <span class="pq-sub">Fluxo de Opções · Delta-Hedging · Estudo</span>
    </div>
    <div class="pq-meta">
        {selo_mercado(agora_ny)}<br>
        <b>NY:</b> {agora_ny.strftime('%H:%M:%S')} · <b>BR:</b> {agora_br.strftime('%H:%M')} ·
        r: {r_global*100:.2f}% ({origem_r})<br>
        <span style='color:{cor_fonte}'>{fonte_geral}</span>
    </div>
</div>
""", unsafe_allow_html=True)

regra_dia = DISCIPLINA[agora_ny.timetuple().tm_yday % len(DISCIPLINA)]
st.markdown(f'<div class="disciplina">🧭 <b>Disciplina do dia:</b> {regra_dia}</div>',
            unsafe_allow_html=True)
with st.expander("Ver as 15 regras do operador"):
    for i, regra in enumerate(DISCIPLINA, 1):
        st.markdown(f"**{i}.** {regra}")

# --- Falhas de dados (sem travar o app) --------------------------------------
if falhas:
    lista = "<br>".join(f"<b>{k}</b>: {v}" for k, v in falhas.items())
    st.markdown(f"""
    <div class="cartao alerta-vermelho">
        <div class="rotulo">Dados indisponíveis</div>
        <div class="sub">{lista}<br><br>
        Checklist: (1) TRADIER_TOKEN salvo em Settings → Secrets do Streamlit Cloud;
        (2) chave de PRODUÇÃO regenerada (a antiga vazou no repositório público);
        (3) conta Tradier aprovada, com depósito e market data agreements aceitos
        como <i>non-professional</i>; (4) nunca usar a chave Sandbox (15 min de atraso).</div>
    </div>""", unsafe_allow_html=True)

if not dados_ativos:
    st.stop()

# --- Veto SPY×QQQ (1.5) -------------------------------------------------------
if "SPY" in dados_ativos and "QQQ" in dados_ativos:
    s_spy, s_qqq = dados_ativos["SPY"]["setup"], dados_ativos["QQQ"]["setup"]
    if s_qqq and s_qqq["codigo"] == "S2" and (not s_spy or s_spy["codigo"] != "S2"):
        st.markdown('<div class="setup-linha alerta-vermelho">⚠️ <b>VETO ATIVO (regra SPY×QQQ):</b> '
                    'o QQQ armou Rompimento Baixista (S2), mas o SPY não confirmou. '
                    'SPY é a PERMISSÃO — sem ele, operação proibida.</div>',
                    unsafe_allow_html=True)

# --- Abas ---------------------------------------------------------------------
nomes_abas = ["📊 Visão Geral", "⚡ Delta-Hedging", "🌊 Fluxo",
              "⏳ Time Pressure", "🎯 Setups", "🔀 SPY×QQQ", "📉 Níveis"]
if MOSTRAR_TV:
    nomes_abas.append("📈 Gráfico TV")
abas = st.tabs(nomes_abas)
ativos_ok = [t for t in tickers_para_rodar if t in dados_ativos]

# ============================== ABA 1 · VISÃO GERAL ============================
with abas[0]:
    for tk in ativos_ok:
        d = dados_ativos[tk]
        var = ""
        if d["prev"]:
            pct = (d["spot"] / d["prev"] - 1) * 100
            cor = "verde" if pct >= 0 else "vermelho"
            var = f' <span class="{cor}">{pct:+.2f}%</span>'
        st.markdown(f"#### {tk} — ${d['spot']:.2f}{var} &nbsp;"
                    f"<span style='font-size:0.72rem;color:#8b98a5'>venc. {d['venc']} · "
                    f"{d['fonte']}</span>", unsafe_allow_html=True)
        if d["dte0"]:
            st.caption("⚠️ Vencimento HOJE (0DTE): gamma extremo — barras mudam rápido e "
                       "picos de Time Pressure sinalizam pullback.")

        st.markdown(regua_fluxo_html(d["comp"], d["vend"], d["fluxo_df"]), unsafe_allow_html=True)
        s = d["setup"]
        if s:
            st.markdown(f'<div class="setup-linha">⚙️ <b>Setup ativo:</b> '
                        f'<span class="amarelo">{s["codigo"]} — {s["nome"]}</span> · '
                        f'Viés: <b>{s["vies"]}</b> · Alvo: {s["alvo"]}</div>',
                        unsafe_allow_html=True)

        trio = [("Delta Hedging Q", d["por_strike"], "gex", d["b_gex"]),
                ("Institutional Flow Q", d["fluxo_df"], "notional", d["b_fluxo"]),
                ("Time Pressure Q", d["tp_df"], "tp", d["b_tp"])]
        if MODO_CELULAR:
            for titulo, df_, col_, b_ in trio:
                painel_quantico(titulo, tk, d["spot"], df_, col_, b_,
                                key=f"vg_{tk}_{col_}", altura=380,
                                faixa=0.03, horizontal=True)
        else:
            colunas = st.columns(3)
            for coluna, (titulo, df_, col_, b_) in zip(colunas, trio):
                with coluna:
                    painel_quantico(titulo, tk, d["spot"], df_, col_, b_,
                                    key=f"vg_{tk}_{col_}", altura=250, faixa=0.03)

        with st.expander("Cartões estratégicos e conversão para futuros"):
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.markdown(cartao_html("Spot", fx(d["spot"])), unsafe_allow_html=True)
            c2.markdown(cartao_html("VWAP", fx(d["vwap"])), unsafe_allow_html=True)
            c3.markdown(cartao_html("Call Wall", fx(d["cw"], nd=1)), unsafe_allow_html=True)
            c4.markdown(cartao_html("Put Wall", fx(d["pw"], nd=1)), unsafe_allow_html=True)
            c5.markdown(cartao_html("Gamma Flip", fx(d["flip"], nd=1),
                                    "domínio " + (d["dominio"] or "misto")),
                        unsafe_allow_html=True)
            if MOSTRAR_FUTUROS:
                n_fut, p_fut, r_fut = razao_futuro(tk, d["spot"])
                if r_fut:
                    linhas = [("Spot", d["spot"]), ("Call Wall", d["cw"]),
                              ("Put Wall", d["pw"]), ("Gamma Flip", d["flip"]),
                              ("Ímã (maior+)", d["b_gex"].get("maior_pos")),
                              ("1ª barra−", d["b_gex"].get("primeira_neg"))]
                    md = (f"| Nível ({tk}) | ETF | Futuro ({n_fut} @ {p_fut:.1f}) |\n"
                          "|---|---|---|\n")
                    for nome, v in linhas:
                        if v:
                            md += f"| {nome} | ${v:.2f} | **{v * r_fut:.1f}** |\n"
                    st.markdown(md)
                else:
                    st.caption("Razão do futuro indisponível no momento.")

        if MOSTRAR_VWAP and d["hist"] is not None and not d["hist"].empty:
            with st.expander(f"Preço × VWAP ({tk})"):
                figv = grafico_vwap(d["hist"], MODO_BANDAS, BANDAS_VWAP.get(tk, []))
                st.plotly_chart(figv, use_container_width=True, key=f"vwap_{tk}",
                                config={"displayModeBar": False})
        st.markdown("---")

# ============================== ABA 2 · DELTA-HEDGING ==========================
with abas[1]:
    st.caption("Barras de gamma = defesa dos market makers. Positivas = guard-rails "
               "(estabiliza); negativas = gasolina no fogo (acelera). Escala: "
               "dollar-gamma pleno (Γ·OI·100·S²), escala em bilhões como no terminal de referência.")
    for tk in ativos_ok:
        d = dados_ativos[tk]
        painel_quantico("Delta Hedging Q", tk, d["spot"], d["por_strike"], "gex",
                        d["b_gex"], key=f"dh_{tk}", altura=420, faixa=0.05,
                        horizontal=MODO_CELULAR)
        st.caption(f"Gamma flip: {fx(d['flip'], nd=1)} · Call Wall: {fx(d['cw'], nd=1)} · "
                   f"Put Wall: {fx(d['pw'], nd=1)}")
        st.markdown(tabela_barras_md(d["b_gex"]))
        st.markdown("---")

# ============================== ABA 3 · FLUXO ==================================
with abas[2]:
    st.caption("Volume Imbalance Flow: prêmio agressor por strike. Verde (direita) = "
               "calls compradas / puts vendidas; vermelho (esquerda) = puts compradas / "
               "calls vendidas. Linhas: branca = spot · azul = ímã (maior+) · roxa = muros.")
    for tk in ativos_ok:
        d = dados_ativos[tk]
        st.markdown(regua_fluxo_html(d["comp"], d["vend"], d["fluxo_df"]), unsafe_allow_html=True)
        fig_i = grafico_imbalance(d["fluxo_df"], d["spot"], d["cw"], d["pw"],
                                  d["b_gex"].get("maior_pos"))
        if fig_i:
            st.markdown(cabecalho_painel("Volume Imbalance Flow", tk, d["spot"],
                                         d["fluxo_df"], "net", d["b_fluxo"]),
                        unsafe_allow_html=True)
            st.plotly_chart(fig_i, use_container_width=True, key=f"imb_{tk}",
                            config={"displayModeBar": False})
        else:
            st.caption(f"{tk}: sem fluxo classificável agora (mercado fechado ou "
                       "volume zerado).")
        painel_quantico("Institutional Flow Q (notional por strike)", tk, d["spot"],
                        d["fluxo_df"], "notional", d["b_fluxo"], key=f"flx_{tk}",
                        altura=300, faixa=0.03, horizontal=MODO_CELULAR)
        st.markdown("---")

# ============================== ABA 4 · TIME PRESSURE ==========================
with abas[3]:
    st.caption("Time Pressure (item 1.8, v1): decaimento do delta (charm) forçando o "
               "hedge dos dealers. Positivo = decadência magnetiza para CIMA; negativo = "
               "para BAIXO; picos = alívio → sinal de pullback. Semântica em validação "
               "ao vivo (item 1.9) — tratar como leitura de apoio, não gatilho isolado.")
    for tk in ativos_ok:
        d = dados_ativos[tk]
        painel_quantico("Time Pressure Q", tk, d["spot"], d["tp_df"], "tp",
                        d["b_tp"], key=f"tp_{tk}", altura=380, faixa=0.04,
                        horizontal=MODO_CELULAR)
        st.markdown(tabela_barras_md(d["b_tp"]))
        st.markdown("---")

# ============================== ABA 5 · SETUPS =================================
with abas[4]:
    st.caption("S6 é o mais assertivo · S2 é o mais perigoso e EXIGE confirmação do "
               "SPY · S5 se evita. PrumoQuant Bell (2.3): em construção — sinal "
               "congelado às 9h29:59 NY e avaliado até 10h00 com MAE/MFE.")
    for tk in ativos_ok:
        d = dados_ativos[tk]
        s = d["setup"]
        if s:
            st.markdown(f"""<div class="terminal"><span class="titulo">{tk} · {s['codigo']} — {s['nome']}</span>
Viés ........: <span class="destaque">{s['vies']}</span>
Gatilho .....: {s['gatilho']}
Alvo ........: {s['alvo']}
Invalidação .: <span class="neg">{s['invalidacao']}</span>
<span class="aviso">Cenário condicional de ESTUDO — a decisão e o risco são do operador.</span></div>""",
                        unsafe_allow_html=True)
        else:
            st.markdown(f"""<div class="terminal"><span class="titulo">{tk}</span>
Nenhum setup ativo neste momento — aguardar o preço interagir com as barras-chave.
<span class="aviso">Ficar de fora também é posição.</span></div>""",
                        unsafe_allow_html=True)
        st.markdown(f"**6 barras-chave do Delta-Hedging ({tk}):**")
        st.markdown(tabela_barras_md(d["b_gex"]))
        st.markdown("---")

# ============================== ABA 6 · SPY×QQQ ================================
with abas[5]:
    if "SPY" in dados_ativos and "QQQ" in dados_ativos:
        s_spy, s_qqq = dados_ativos["SPY"]["setup"], dados_ativos["QQQ"]["setup"]
        cod_spy = s_spy["codigo"] if s_spy else "—"
        cod_qqq = s_qqq["codigo"] if s_qqq else "—"
        if s_qqq and cod_qqq == "S2" and cod_spy == "S2":
            leitura = ("🔻 **S2 CONFIRMADO nos dois ativos** — rompimento baixista "
                       "validado. Ainda assim, exigir margem de 0,15% além do nível "
                       "(iminente × confirmado).")
        elif s_qqq and cod_qqq == "S2":
            leitura = ("⛔ **VETO** — QQQ baixista sem confirmação do SPY. "
                       "SPY é a permissão; QQQ é só o gatilho.")
        elif s_spy and s_qqq and "COMPRADOR" in s_spy["vies"] and "COMPRADOR" in s_qqq["vies"]:
            leitura = "✅ **Permissão altista** — SPY e QQQ alinhados no viés comprador."
        else:
            leitura = "🟡 **Sinais mistos** — cautela; aguardar alinhamento SPY×QQQ."
        st.markdown(f"**Leitura cruzada agora:** SPY = `{cod_spy}` · QQQ = `{cod_qqq}`")
        st.markdown(leitura)
        st.markdown("""
| Cenário | QQQ | SPY | Decisão |
|---|---|---|---|
| 1 | S2 (baixista) | S2 (baixista) | Rompimento confirmado — operável com margem 0,15% |
| 2 | S2 (baixista) | qualquer outro | **VETO** — proibido operar QQQ contra o SPY |
| 3 | viés comprador | viés comprador | Permissão altista — QQQ como instrumento de rompimento |
| 4 | sinais mistos | sinais mistos | Cautela / ficar de fora |
""")
        st.caption("Regra de ouro: SPY = liquidez/permissão (muros mais fortes, ativo de "
                   "reversão); QQQ = gatilho/rompimento. Nunca operar QQQ contra o SPY.")
    else:
        st.info("Ative o modo **SPY + QQQ lado a lado** na barra lateral para a "
                "leitura cruzada e o veto automático.")

# ============================== ABA 7 · NÍVEIS ================================
with abas[6]:
    st.caption("Candlestick 1 min em tempo real (Tradier) com os níveis do dealer "
               "sobrepostos: muros (roxo), ímã/alvo (azul), 1ª positiva (verde), 1ª "
               "negativa (vermelho), defesa do Setup 6 (laranja), flip (amarelo) e VWAP. "
               "Substitui o TradingView gratuito, que é atrasado ~15 min e não traz os "
               "níveis de opções. Obs.: a zona de liquidez passiva do DOM de futuros "
               "(as faixas horizontais do terminal deles) é a Fase 7 — exige feed pago "
               "Databento/Rithmic e não sai do TradingView.")
    for tk in ativos_ok:
        d = dados_ativos[tk]
        fig_n = grafico_niveis(d["hist"], d["spot"], d["cw"], d["pw"], d["flip"],
                               d["b_gex"], d["vwap"], tk)
        if fig_n:
            st.markdown(f"**{tk} — níveis do dealer ao vivo**")
            st.plotly_chart(fig_n, use_container_width=True, key=f"niv_{tk}",
                            config={"displayModeBar": False})
        else:
            st.caption(f"{tk}: candlestick indisponível (fora do pregão ou fallback "
                       "yfinance sem OHLC intraday).")
        st.markdown("---")

# ============================== ABA 8 · GRÁFICO TV =============================
if MOSTRAR_TV:
    with abas[7]:
        simbolos_tv = {"SPY": "AMEX%3ASPY", "QQQ": "NASDAQ%3AQQQ"}
        for tk in ativos_ok:
            url = (f"https://s.tradingview.com/widgetembed/?symbol={simbolos_tv[tk]}"
                   "&interval=5&theme=dark&style=1&locale=br&hide_top_toolbar=0"
                   "&withdateranges=1")
            components.html(f'<iframe src="{url}" style="width:100%;height:600px;'
                            'border:0;border-radius:10px;"></iframe>', height=610)

st.caption("PrumoQuant · ferramenta de ESTUDO — não é recomendação de investimento. "
           "Painel somente leitura: nenhum endpoint de ordem está implementado (trava §2.1).")
