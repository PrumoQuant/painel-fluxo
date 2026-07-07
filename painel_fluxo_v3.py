# ============================================================================
# PAINEL DE FLUXO DE OPÇÕES — VERSÃO 3.6 "TERMINAL QUANTICO" (ESTUDO)
# PrumoQuant · https://prumoquant.streamlit.app
# ============================================================================
# NOVIDADES v3.6:
#  - LAYOUT TERMINAL: Integração total baseada na referência visual do Quantico.
#    Gráficos TradingView lado a lado na esquerda, grade 3x2 de painéis
#    (Delta Hedging, Inst. Flow, Time Pressure) para QQQ e SPY na direita.
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
    .block-container { max-width: 100%; padding: 1rem 2rem; }

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
WHITELIST = {"SPY", "QQQ"}   # trava de segurança §2.1

# ----------------------------------------------------------------------------
# BARRA LATERAL
# ----------------------------------------------------------------------------
st.sidebar.title("Configurações")
MODO_VISAO = st.sidebar.radio("Modo de visão", ["SPY + QQQ lado a lado", "Um ativo"])
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
    MOSTRAR_TV = st.checkbox("Painéis com gráfico TradingView", value=True)

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
    return "—" if v is None else f"{pref}{v:.{nd}f}"

def gamma_bs(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return norm.pdf(d1) / (S * sigma * np.sqrt(T))

def charm_bs(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    svt = sigma * np.sqrt(T)
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / svt
    d2 = d1 - svt
    return -norm.pdf(d1) * (2.0 * r * T - d2 * svt) / (2.0 * T * svt)

# ----------------------------------------------------------------------------
# CAMADA TRADIER
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
            return None, "401 Unauthorized"
        if r.status_code != 200:
            return None, f"HTTP {r.status_code} em {caminho}"
        return r.json(), None
    except requests.exceptions.Timeout:
        return None, f"timeout (8 s) em {caminho}"
    except Exception as e:
        return None, f"falha de rede: {e}"

def historico_timesales(ticker):
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
    df = df.set_index("time").rename(columns={"high": "High", "low": "Low",
                                              "close": "Close", "volume": "Volume"})
    cols = [c for c in ("High", "Low", "Close", "Volume") if c in df.columns]
    return df[cols] if len(cols) == 4 else None

def historico_yf(ticker):
    try:
        return yf.Ticker(ticker).history(period="1d", interval="1m", prepost=False)
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=20, show_spinner=False)
def buscar_dados(ticker):
    if ticker not in WHITELIST:
        return {"erro": f"{ticker} fora da whitelist (SPY/QQQ)."}
    erros, fonte = [], "Tradier · tempo real"
    spot = prev = None

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

    hist = historico_timesales(ticker)
    if hist is None or hist.empty:
        hist = historico_yf(ticker)
        if spot is None and hist is not None and not hist.empty:
            spot = float(hist["Close"].iloc[-1])
            fonte = "yfinance · ~15 min"

    calls = puts = venc = None
    j, e = tradier_get("/markets/options/expirations", {"symbol": ticker})
    if e:
        erros.append(f"expirations: {e}")
    else:
        exp = (j.get("expirations") or {})
        datas = exp.get("date") if isinstance(exp, dict) else None
        if datas:
            venc = datas[0] if isinstance(datas, list) else datas
    if venc:
        j, e = tradier_get("/markets/options/chains",
                           {"symbol": ticker, "expiration": venc, "greeks": "true"})
        if e:
            erros.append(f"chains: {e}")
        else:
            ops = ((j.get("options") or {}) or {}).get("option", [])
            if isinstance(ops, dict):
                ops = [ops]
            dfc = pd.DataFrame(ops)
            if not dfc.empty:
                dfc = dfc.rename(columns={"open_interest": "openInterest", "last": "lastPrice"})
                if "greeks" in dfc.columns:
                    def _iv(g):
                        if isinstance(g, dict):
                            for chave in ("mid_iv", "smv_vol", "ask_iv", "bid_iv"):
                                v = num(g.get(chave))
                                if v > 0: return v
                        return 0.0
                    dfc["impliedVolatility"] = dfc["greeks"].apply(_iv)
                else:
                    dfc["impliedVolatility"] = 0.0
                calls = dfc[dfc["option_type"] == "call"].copy()
                puts = dfc[dfc["option_type"] == "put"].copy()

    return {"spot": spot, "prev": prev, "hist": hist, "calls": calls,
            "puts": puts, "venc": venc, "fonte": fonte, "erros": erros}

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

def identificar_barras_chave(df, spot, col="gex"):
    b = {}
    if df is None or df.empty or col not in df.columns:
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
    dias = max((pd.Timestamp(venc_str) - pd.Timestamp.now()).days, 0)
    T = max(dias / 252, 0.5 / 252)
    linhas = []
    for df, tipo in ((calls, "call"), (puts, "put")):
        if df is None or df.empty:
            continue
        for _, op in df.iterrows():
            k = num(op.get("strike"))
            iv = num(op.get("impliedVolatility"))
            oi = num(op.get("openInterest"))
            if iv <= 0 or oi <= 0 or not (spot * 0.90 <= k <= spot * 1.10):
                continue
            g = gamma_bs(spot, k, T, r, iv) * oi * 100 * spot * spot * 0.01
            linhas.append({"strike": k, "gex": g if tipo == "call" else -g})

    gex_df = pd.DataFrame(linhas)
    if gex_df.empty:
        return gex_df, None, None, None, None, False

    por_strike = gex_df.groupby("strike")["gex"].sum().reset_index()
    pico = por_strike["gex"].abs().max()
    if pico > 0:
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
    dias = max((pd.Timestamp(venc_str) - pd.Timestamp.now()).days, 0)
    T = max(dias / 252, 0.5 / 252)
    linhas = []
    for df, tipo in ((calls, "call"), (puts, "put")):
        if df is None or df.empty:
            continue
        for _, op in df.iterrows():
            k = num(op.get("strike"))
            iv = num(op.get("impliedVolatility"))
            oi = num(op.get("openInterest"))
            if iv <= 0 or oi <= 0 or not (spot * 0.90 <= k <= spot * 1.10):
                continue
            c = abs(charm_bs(spot, k, T, r, iv)) / 252.0 * oi * 100 * spot
            linhas.append({"strike": k, "tp": c if tipo == "call" else -c})
    dft = pd.DataFrame(linhas)
    if dft.empty:
        return dft
    dft = dft.groupby("strike")["tp"].sum().reset_index()
    pico = dft["tp"].abs().max()
    if pico > 0:
        dft = dft[dft["tp"].abs() >= 0.01 * pico]
    return dft.sort_values("strike").reset_index(drop=True)

def calcular_fluxo_institucional(calls, puts):
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
            mid = (bid + ask) / 2.0
            if mid <= 0 or (ask - bid) / mid > 0.25:
                continue
            spread = ask - bid
            terco_baixo = bid + spread / 3.0
            terco_alto = ask - spread / 3.0
            premio = ultimo * vol * 100
            entrada = mapa.setdefault(k, {"bull": 0.0, "bear": 0.0})
            if ultimo >= terco_alto:
                if tipo == "call":
                    comp += premio; entrada["bull"] += premio
                else:
                    vend += premio; entrada["bear"] += premio
            elif ultimo <= terco_baixo:
                if tipo == "call":
                    vend += premio; entrada["bear"] += premio
                else:
                    comp += premio; entrada["bull"] += premio
    linhas = [{"strike": k, "bull": v["bull"], "bear": v["bear"],
               "net": v["bull"] - v["bear"]} for k, v in mapa.items()]
    if not linhas:
        return comp, vend, pd.DataFrame(columns=["strike", "bull", "bear", "net"])
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
        return dict(codigo="S6", nome="Proteção no Hedge Negativo", vies="COMPRADOR", gatilho=f"teste na 1ª barra− ({pn:.0f})", alvo=f"{mp:.0f}", invalidacao=f"perder {pn:.0f}")
    if un and perto(un) and spot <= (mn or un):
        return dict(codigo="S4", nome="Pullback no Fundo", vies="COMPRADOR", gatilho=f"na última barra− ({un:.0f})", alvo=f"{mp:.0f}" if mp else "VWAP", invalidacao=f"aceitação abaixo de {un:.0f}")
    if up and perto(up) and mp and mp < spot:
        return dict(codigo="S3", nome="Pullback no Topo", vies="VENDEDOR", gatilho=f"na última barra+ ({up:.0f})", alvo=f"{mp:.0f}", invalidacao=f"romper {up:.0f}")
    if flip and spot > flip and mp and mp > spot:
        return dict(codigo="S1", nome="Rompimento Altista", vies="COMPRADOR", gatilho=f"cruzou flip ({flip:.0f})", alvo=f"{mp:.0f}", invalidacao=f"voltar abaixo de {flip:.0f}")
    if pn and spot < pn:
        return dict(codigo="S2", nome="Rompimento Baixista", vies="VENDEDOR", gatilho=f"perdeu 1ª barra− ({pn:.0f})", alvo=f"{mn:.0f}" if mn else "última barra−", invalidacao=f"recuperar {pn:.0f}")
    if mp and mn and mn <= spot <= mp:
        return dict(codigo="S5", nome="Consolidação", vies="NEUTRO", gatilho=f"preso entre {mn:.0f} e {mp:.0f}", alvo=f"extremos", invalidacao="romper extremos")
    return None

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

def regua_fluxo_html(comp, vend):
    tot = comp + vend
    p_comp = (comp / tot * 100) if tot > 0 else 50.0
    p_vend = 100.0 - p_comp
    net = comp - vend
    if p_comp > 60:
        status, classe = "INSTITUIÇÕES COMPRANDO AGORA", "verde"
    elif p_vend > 60:
        status, classe = "INSTITUIÇÕES VENDENDO AGORA", "vermelho"
    else:
        status, classe = "EM DISPUTA NEUTRA", "amarelo"
    return f"""
    <div class="fluxobar-wrap">
        <div class="fluxobar-top">
            <span><b>VOLUME IMBALANCE (prêmio agressor)</b></span>
            <span class="{classe}"><b>{status}</b></span>
        </div>
        <div class="fluxobar">
            <div class="verde-seg" style="width: {p_comp:.1f}%"></div>
            <div class="verm-seg" style="width: {p_vend:.1f}%"></div>
        </div>
        <div class="fluxobar-sub">
            <span class="verde">▲ {p_comp:.1f}% ({fmt_usd(comp)})</span>
            <span class="{'verde' if net >= 0 else 'vermelho'}">NET: {fmt_usd(net)}</span>
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
            cores.append("#22c55e")
        elif mn is not None and abs(k - mn) < 1e-9 and v < 0:
            cores.append("#ef4444")
        else:
            cores.append("#3b82f6")
    fig = go.Figure()
    if horizontal:
        fig.add_trace(go.Bar(y=df["strike"], x=df[col], orientation="h", marker_color=cores))
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

def painel_quantico(titulo, tk, spot, df, col, barras, key, altura=260, faixa=0.03, horizontal=False):
    st.markdown(cabecalho_painel(titulo, tk, spot, df, col, barras), unsafe_allow_html=True)
    if df is None or df.empty:
        st.caption("Sem dados suficientes.")
        return
    dfv = df[(df["strike"] >= spot * (1 - faixa)) & (df["strike"] <= spot * (1 + faixa))]
    if dfv.empty:
        dfv = df
    fig = grafico_barras_quantico(dfv, col, spot, barras, altura=altura, horizontal=horizontal)
    st.plotly_chart(fig, use_container_width=True, key=key, config={"displayModeBar": False})

def grafico_vwap(hist, modo_bandas, bandas_pct, altura=330):
    idx, vwap_ser, sigma_ser = calcular_vwap(hist)
    h = hist.loc[idx]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=idx, y=h["Close"], name="Preço", line=dict(color="#e6edf3", width=1.6)))
    fig.add_trace(go.Scatter(x=idx, y=vwap_ser, name="VWAP", line=dict(color="#fbbf24", width=1.4)))
    if modo_bandas.startswith("Desvio"):
        for mult in (1, 2, 3):
            for sinal in (1, -1):
                fig.add_trace(go.Scatter(x=idx, y=vwap_ser + sinal * mult * sigma_ser,
                                         name=f"{'+' if sinal > 0 else '−'}{mult}σ",
                                         line=dict(color="#3b82f6", width=0.8, dash="dot"),
                                         opacity=max(0.25, 0.8 - 0.22 * mult), showlegend=False))
    else:
        for p in bandas_pct:
            for sinal in (1, -1):
                fig.add_trace(go.Scatter(x=idx, y=vwap_ser * (1 + sinal * p / 100.0),
                                         name=f"{'+' if sinal > 0 else '−'}{p}%",
                                         line=dict(color="#3b82f6", width=0.8, dash="dot"),
                                         opacity=0.5, showlegend=False))
    fig.update_layout(template="plotly_dark", paper_bgcolor="#10161d", plot_bgcolor="#10161d",
                      margin=dict(l=6, r=6, t=8, b=6), height=altura, legend=dict(orientation="h", y=1.08),
                      xaxis=dict(gridcolor="#1c2733"), yaxis=dict(gridcolor="#1c2733"))
    return fig

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

dados_ativos, falhas = {}, {}
for tk in tickers_para_rodar:
    bruto = buscar_dados(tk)
    if bruto.get("erro"):
        falhas[tk] = bruto["erro"]
        continue
    spot, hist = bruto["spot"], bruto["hist"]
    calls, puts, venc = bruto["calls"], bruto["puts"], bruto["venc"]
    if spot is None or venc is None or calls is None or calls.empty:
        falhas[tk] = " · ".join(bruto["erros"]) if bruto["erros"] else "cadeia indisponível"
        continue

    por_strike, cw, pw, flip, dominio, v_hoje = calcular_gex(calls, puts, spot, venc, r_global)
    b_gex = identificar_barras_chave(por_strike, spot, "gex")
    tp_df = calcular_time_pressure(calls, puts, spot, venc, r_global)
    b_tp = identificar_barras_chave(tp_df, spot, "tp")
    comp, vend, fluxo_df = calcular_fluxo_institucional(calls, puts)
    b_fluxo = identificar_barras_chave(fluxo_df, spot, "net")

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

# --- Cabeçalho ---
fonte_geral = "● Tempo real Tradier" if dados_ativos and all(d["fonte"].startswith("Tradier") for d in dados_ativos.values()) else "● Fallback yfinance (~15 min)"
cor_fonte = "#22c55e" if fonte_geral.startswith("● Tempo") else "#fbbf24"
st.markdown(f"""
<div class="pq-header">
    <div>
        <span class="pq-logo">Prumo<span class="fio">Quant</span>
        <small style='font-size:0.8rem;color:#6b7280;'>v3.6</small></span>
        <span class="pq-sub">Terminal Quantico · Estudo</span>
    </div>
    <div class="pq-meta">
        {selo_mercado(agora_ny)}<br>
        <b>NY:</b> {agora_ny.strftime('%H:%M:%S')} · <b>BR:</b> {agora_br.strftime('%H:%M')} · r: {r_global*100:.2f}%<br>
        <span style='color:{cor_fonte}'>{fonte_geral}</span>
    </div>
</div>
""", unsafe_allow_html=True)

if falhas:
    lista = "<br>".join(f"<b>{k}</b>: {v}" for k, v in falhas.items())
    st.markdown(f'<div class="cartao alerta-vermelho"><div class="rotulo">Aviso</div><div class="sub">{lista}</div></div>', unsafe_allow_html=True)

if not dados_ativos:
    st.stop()

# ----------------------------------------------------------------------------
# MODO TERMINAL (LAYOUT QUANTICO)
# ----------------------------------------------------------------------------
if MODO_VISAO == "SPY + QQQ lado a lado" and "SPY" in dados_ativos and "QQQ" in dados_ativos:
    col_esq, col_dir = st.columns([0.38, 0.62], gap="small")

    with col_esq:
        c_tv_qqq, c_tv_spy = st.columns(2, gap="small")
        with c_tv_qqq:
            if MOSTRAR_TV:
                components.html('<iframe src="https://s.tradingview.com/widgetembed/?symbol=NASDAQ%3AQQQ&interval=5&theme=dark&style=1&locale=br&hide_top_toolbar=1&withdateranges=0" style="width:100%;height:640px;border:0;border-radius:8px;"></iframe>', height=650)
        with c_tv_spy:
            if MOSTRAR_TV:
                components.html('<iframe src="https://s.tradingview.com/widgetembed/?symbol=AMEX%3ASPY&interval=5&theme=dark&style=1&locale=br&hide_top_toolbar=1&withdateranges=0" style="width:100%;height:640px;border:0;border-radius:8px;"></iframe>', height=650)

    with col_dir:
        # --- Linha Superior: QQQ ---
        d_q = dados_ativos["QQQ"]
        cq1, cq2, cq3 = st.columns(3, gap="small")
        with cq1:
            painel_quantico("Delta Hedging Q", "QQQ", d_q["spot"], d_q["por_strike"], "gex", d_q["b_gex"], key="dh_q", altura=280, faixa=0.04)
        with cq2:
            painel_quantico("Institutional Flow Q", "QQQ", d_q["spot"], d_q["fluxo_df"], "net", d_q["b_fluxo"], key="if_q", altura=280, faixa=0.03)
        with cq3:
            painel_quantico("Time Pressure Q", "QQQ", d_q["spot"], d_q["tp_df"], "tp", d_q["b_tp"], key="tp_q", altura=280, faixa=0.04)

        st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

        # --- Linha Inferior: SPY ---
        d_s = dados_ativos["SPY"]
        cs1, cs2, cs3 = st.columns(3, gap="small")
        with cs1:
            painel_quantico("Delta Hedging Q", "SPY", d_s["spot"], d_s["por_strike"], "gex", d_s["b_gex"], key="dh_s", altura=280, faixa=0.04)
        with cs2:
            painel_quantico("Institutional Flow Q", "SPY", d_s["spot"], d_s["fluxo_df"], "net", d_s["b_fluxo"], key="if_s", altura=280, faixa=0.03)
        with cs3:
            painel_quantico("Time Pressure Q", "SPY", d_s["spot"], d_s["tp_df"], "tp", d_s["b_tp"], key="tp_s", altura=280, faixa=0.04)

    # --- Análises Complementares Ocultas ---
    st.markdown("---")
    with st.expander("🛠️ Visão Geral, Análise de Setups e VWAP"):
        for tk in ["QQQ", "SPY"]:
            d = dados_ativos[tk]
            st.markdown(f"#### {tk} · Spot: ${d['spot']:.2f}")
            st.markdown(regua_fluxo_html(d["comp"], d["vend"]), unsafe_allow_html=True)
            if MOSTRAR_VWAP and d["hist"] is not None and not d["hist"].empty:
                st.plotly_chart(grafico_vwap(d["hist"], MODO_BANDAS, BANDAS_VWAP.get(tk, [])), use_container_width=True, key=f"vwap_{tk}")
        
        st.markdown("#### Leitura Cruzada SPY×QQQ")
        s_spy, s_qqq = dados_ativos["SPY"]["setup"], dados_ativos["QQQ"]["setup"]
        cod_spy = s_spy["codigo"] if s_spy else "—"
        cod_qqq = s_qqq["codigo"] if s_qqq else "—"
        st.write(f"**SPY:** `{cod_spy}` · **QQQ:** `{cod_qqq}`")

else:
    # Fallback para "Um ativo"
    tk = TICKER_UNICO
    d = dados_ativos[tk]
    if MOSTRAR_TV:
        simbolos_tv = {"SPY": "AMEX%3ASPY", "QQQ": "NASDAQ%3AQQQ"}
        components.html(f'<iframe src="https://s.tradingview.com/widgetembed/?symbol={simbolos_tv[tk]}&interval=5&theme=dark&style=1&locale=br&hide_top_toolbar=1&withdateranges=0" style="width:100%;height:400px;border:0;border-radius:8px;"></iframe>', height=410)
    
    st.markdown(regua_fluxo_html(d["comp"], d["vend"]), unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1: painel_quantico("Delta Hedging Q", tk, d["spot"], d["por_strike"], "gex", d["b_gex"], key="dh1", altura=300, faixa=0.04, horizontal=MODO_CELULAR)
    with c2: painel_quantico("Institutional Flow Q", tk, d["spot"], d["fluxo_df"], "net", d["b_fluxo"], key="if1", altura=300, faixa=0.03, horizontal=MODO_CELULAR)
    with c3: painel_quantico("Time Pressure Q", tk, d["spot"], d["tp_df"], "tp", d["b_tp"], key="tp1", altura=300, faixa=0.04, horizontal=MODO_CELULAR)
    
    if MOSTRAR_VWAP and d["hist"] is not None and not d["hist"].empty:
        st.plotly_chart(grafico_vwap(d["hist"], MODO_BANDAS, BANDAS_VWAP.get(tk, [])), use_container_width=True, key=f"vwap_1_{tk}")
