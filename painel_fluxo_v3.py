# ============================================================================
# PAINEL DE FLUXO DE OPÇÕES — VERSÃO 3.4 "CALIBRAÇÃO DO FLUXO" (ESTUDO)
# PrumoQuant · https://prumoquant.streamlit.app
# ============================================================================
# Novidades da v3.4 (calibração pós-pregão de 06/07/2026 — o dia em que o
# nosso fluxo estimado divergiu do Volume Imbalance real da Quantico:
# nosso SPY "55% vendedor" × deles "92% bullish" num rali de +1%):
#  23. CLASSIFICAÇÃO POR TERÇOS DO SPREAD: antes, negócio abaixo do MEIO
#      do spread contava como "vendido". No 0DTE o decaimento (theta)
#      derruba os prêmios o dia inteiro e os prints ficam abaixo do meio
#      mesmo com agressão COMPRADORA → viés vendedor sistemático. Agora:
#      terço de cima do spread = comprado; terço de baixo = vendido; o
#      MIOLO é ambíguo e é DESCARTADO. Perder volume é melhor do que
#      classificar errado. (Solução definitiva = tick real na Fase 3 / Tradier.)
#  24. JANELA RECENTE (~30 min) NA RÉGUA DE FLUXO, em LINGUAGEM SIMPLES:
#      "instituições COMPRANDO agora / VENDENDO agora / em DISPUTA" —
#      the accumulated total hides the afternoon reversal.
#  25. LINHA "SINAL SIMPLES" DO PLAYBOOK (estilo Striking Bell):
#      ação → alvo → desmonte, sem jargão.
#
# CONEXÃO REAL-TIME ATIVADA (TRADIER API):
#  - Substituição completa do yfinance para dados de opções em tempo real.
#  - Autenticação via Chave de Produção de Nova York (Dados LITE $0/mês).
# ============================================================================

import os
import requests
from datetime import datetime, time as dtime
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from scipy.stats import norm
from streamlit_autorefresh import st_autorefresh

# ----------------------------------------------------------------------------
# CREDENCIAIS DE ACESSO — TRADIER REAL-TIME API (PRODUÇÃO)
# ----------------------------------------------------------------------------
# Cole aqui o código longo que aparece borrado na sua tela de produção
TRADIER_TOKEN = "zf2QGlhppXTGt8aygeW7ZloQ2KQv..." 
TRADIER_ACCOUNT_ID = "6YB87394"

# ----------------------------------------------------------------------------
# CONFIGURAÇÃO DA PÁGINA + ESTILO
# ----------------------------------------------------------------------------
st.set_page_config(page_title="PrumoQuant — Fluxo de Opções (estudo)",
                   layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    .stApp { background-color: #0b0f14; }
    section[data-testid="stSidebar"] { background-color: #0e141b; }
    h1, h2, h3, p, span, label { color: #e6edf3; }
    .block-container { padding-top: 1.1rem; max-width: 1500px; }

    /* ---------- Cabeçalho institucional ---------- */
    .pq-header { display: flex; justify-content: space-between;
        align-items: flex-end; padding: 2px 0 10px 0; margin-bottom: 6px;
        border-bottom: 1px solid #1c2733; }
    .pq-logo { font-size: 1.55rem; font-weight: 800; letter-spacing: 1px;
        color: #e6edf3; }
    .pq-logo .fio { color: #fbbf24; }
    .pq-sub { display: block; font-size: 0.72rem; color: #8b98a5;
        letter-spacing: 2px; text-transform: uppercase; margin-top: 2px; }
    .pq-meta { text-align: right; font-size: 0.72rem; color: #8b98a5;
        line-height: 1.5; }

    /* ---------- Abas ---------- */
    .stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid #1c2733; }
    .stTabs [data-baseweb="tab"] { background: transparent; color: #8b98a5;
        font-size: 0.85rem; padding: 8px 14px; border-radius: 8px 8px 0 0; }
    .stTabs [aria-selected="true"] { color: #e6edf3; background: #131a22;
        border-bottom: 2px solid #fbbf24; }

    /* ---------- Cartões ---------- */
    .cartao {
        background: linear-gradient(180deg, #131a22 0%, #10161d 100%);
        border: 1px solid #1e2936; border-radius: 10px;
        padding: 12px 14px 9px 14px; height: 100%;
    }
    .cartao .rotulo { font-size: 0.66rem; letter-spacing: 1.5px;
        text-transform: uppercase; color: #8b98a5; margin-bottom: 2px; }
    .cartao .valor { font-size: 1.35rem; font-weight: 700; color: #e6edf3;
        font-variant-numeric: tabular-nums; }
    .cartao .sub { font-size: 0.72rem; color: #8b98a5; margin-top: 2px; }
    .verde { color: #22c55e !important; }
    .vermelho { color: #ef4444 !important; }
    .amarelo { color: #eab308 !important; }

    .selo { display: inline-block; padding: 4px 12px; border-radius: 999px;
        font-size: 0.75rem; font-weight: 700; letter-spacing: 1px; }
    .selo-aberto  { background: #052e16; color: #22c55e; border: 1px solid #14532d; }
    .selo-fechado { background: #450a0a; color: #f87171; border: 1px solid #7f1d1d; }
    .selo-pre     { background: #422006; color: #fbbf24; border: 1px solid #92400e; }

    /* ---------- Linha de disciplina (discreta) ---------- */
    .disciplina { font-size: 0.78rem; color: #9aa7b4; padding: 2px 0 0 0; }
    .disciplina b { color: #fbbf24; font-weight: 700; }

    /* ---------- Linha discreta de setup (v3.3) ---------- */
    .setup-linha { font-size: 0.8rem; padding: 6px 12px; border-radius: 8px;
        background: #10161d; border: 1px solid #1e2936;
        margin: 2px 0 8px 0; color: #c9d4de; }
    .setup-linha b { font-weight: 700; }

    /* ---------- Régua de fluxo (estilo Volume Imbalance) ---------- */
    .fluxobar-wrap { background: #10161d; border: 1px solid #1e2936;
        border-radius: 8px; padding: 8px 12px 10px 12px;
        margin: 2px 0 8px 0; }
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

    .terminal {
        background: #05100a; border: 1px solid #14532d; border-radius: 10px;
        padding: 18px 22px; font-family: 'Consolas', 'Courier New', monospace;
        font-size: 0.9rem; line-height: 1.7; color: #86efac;
        white-space: pre-wrap; margin-bottom: 12px;
    }
    .terminal .titulo { color: #22c55e; font-weight: 700; }
    .terminal .aviso { color: #6b7280; font-size: 0.78rem; }
    .terminal .destaque { color: #fbbf24; font-weight: 700; }
    .terminal .neg { color: #f87171; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

st.sidebar.title("Configurações")
MODO_VISAO = st.sidebar.radio("Modo de visão", ["Um ativo", "SPY + QQQ lado a lado"])
TICKER_UNICO = st.sidebar.selectbox("Ativo (modo um ativo)", ["SPY", "QQQ"])
MODO_CELULAR = st.sidebar.checkbox(
    "📱 Modo celular (layout vertical)", value=False,
    help="Gamma em barras horizontais e tudo empilhado — muito mais legível em tela estreita.")
st.sidebar.markdown("---")
USAR_R_AUTO = st.sidebar.checkbox(
    "Taxa de juros automática (^IRX)", value=True,
    help="Busca a taxa real do T-bill americano de 13 semanas no Yahoo. Se falhar, usa o valor manual abaixo.")
TAXA_MANUAL = st.sidebar.number_input("Taxa de juros manual (reserva)", value=0.05, step=0.005, format="%.3f")
MOSTRAR_FUTUROS = st.sidebar.checkbox(
    "Converter níveis para futuros (ES/NQ)", value=True,
    help="Mostra os muros e alvos já convertidos para o preço do futuro correspondente, para operar na corretora.")

with st.sidebar.expander("Preferências de exibição"):
    MOSTRAR_VWAP = st.checkbox("Gráfico Preço × VWAP (com bandas)", value=True)
    MODO_BANDAS = st.selectbox("Modo das bandas VWAP", ["Desvio padrão (σ)", "Porcentagem (%)"], index=0)
    BANDAS_QQQ_TXT = st.text_input("Bandas VWAP QQQ", "0.235, 0.47, 0.705")
    BANDAS_SPY_TXT = st.text_input("Bandas VWAP SPY", "0.14, 0.28, 0.42")
    MOSTRAR_TV = st.checkbox("Aba com gráfico TradingView embutido", value=True)

def parse_bandas(txt):
    out = []
    for p in str(txt).replace(";", ",").split(","):
        try:
            v = float(p.strip().replace("%", ""))
            if 0 < v < 5: out.append(v)
        except Exception: pass
    return out[:3]

BANDAS_VWAP = {"QQQ": parse_bandas(BANDAS_QQQ_TXT), "SPY": parse_bandas(BANDAS_SPY_TXT)}
st.sidebar.caption("Ferramenta de ESTUDO. Dados de Opções Real-Time via TRADIER API.")

# ----------------------------------------------------------------------------
# AUXILIARES MATEMÁTICOS E FORMATADORES
# ----------------------------------------------------------------------------
def num(v):
    try:
        x = float(v)
        return 0.0 if pd.isna(x) else x
    except (TypeError, ValueError): return 0.0

def fmt_usd(v):
    v = num(v); s = "-" if v < 0 else ""; a = abs(v)
    if a >= 1e9: return f"{s}${a/1e9:.1f}B"
    if a >= 1e6: return f"{s}${a/1e6:.1f}M"
    if a >= 1e3: return f"{s}${a/1e3:.0f}K"
    return f"{s}${a:.0f}"

def gamma_bs(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0: return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return norm.pdf(d1) / (S * sigma * np.sqrt(T))

# ----------------------------------------------------------------------------
# MOTOR DE CAPTURA TRADIER API (SUBSTITUTO DO YFINANCE OPTIONS)
# ----------------------------------------------------------------------------
@st.cache_data(ttl=5, show_spinner=False)
def buscar_dados(ticker):
    """
    Mantém o histórico de preços intradiários pelo yfinance, mas puxa a cadeia 
    de opções EM TEMPO REAL absoluto através da sua chave de Produção da Tradier.
    """
    tk = yf.Ticker(ticker)
    hist = tk.history(period="1d", interval="1m", prepost=True)

    # Preço de fechamento anterior para gaps
    prev_close = None
    diario = tk.history(period="5d", interval="1d")
    if not diario.empty:
        hoje_ny = pd.Timestamp.now(tz=diario.index.tz).date()
        if diario.index[-1].date() == hoje_ny and len(diario) >= 2:
            prev_close = float(diario["Close"].iloc[-2])
        else:
            prev_close = float(diario["Close"].iloc[-1])

    # --- Puxar Opções via Tradier ---
    url_venc = f"https://api.tradier.com/v1/markets/options/expirations"
    headers = {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}
    
    try:
        # 1. Pega os vencimentos ativos
        res_venc = requests.get(url_venc, params={"symbol": ticker.upper()}, headers=headers)
        if res_venc.status_code != 200 or not res_venc.json().get("expirations"):
            return hist, prev_close, None, None, None
            
        vencs = res_venc.json()["expirations"]["date"]
        venc_atual = vencs[0] if isinstance(vencs, list) else vencs # Pega o 0DTE/Mais próximo

        # 2. Pega a cadeia de opções completa
        url_chain = "https://api.tradier.com/v1/markets/options/chains"
        params_chain = {"symbol": ticker.upper(), "expiration": venc_atual, "greeks": "true"}
        res_chain = requests.get(url_chain, params=params_chain, headers=headers)
        
        if res_chain.status_code == 200:
            dados_opcoes = res_chain.json().get("options", {}).get("option", [])
            df_completo = pd.DataFrame(dados_opcoes)
            
            if df_completo.empty:
                return hist, prev_close, None, None, venc_atual
            
            # Padronização Exata para manter compatível com os filtros e cálculos do seu código antigo
            df_completo = df_completo.rename(columns={
                'strike': 'strike',
                'open_interest': 'openInterest',
                'volume': 'volume',
                'bid': 'bid',
                'ask': 'ask',
                'last': 'lastPrice',
                'greeks': 'greeks'
            })
            
            # Extrai volatilidade implícita calculada pela Tradier (se houver no nó) ou usa campo nativo
            if 'greeks' in df_completo.columns:
                df_completo['impliedVolatility'] = df_completo['greeks'].apply(lambda x: num(x.get('ask_iv')) if isinstance(x, dict) else 0.0)
            else:
                df_completo['impliedVolatility'] = df_completo.get('greeks.ask_iv', 0.2) 

            # Separa exatamente no formato das variáveis originais
            calls = df_completo[df_completo["option_type"] == "call"].copy()
            puts = df_completo[df_completo["option_type"] == "put"].copy()
            
            return hist, prev_close, calls, puts, venc_atual
            
    except Exception as e:
        st.error(f"Erro na comunicação com a API Tradier: {e}")
        
    return hist, prev_close, None, None, None

# ----------------------------------------------------------------------------
# SISTEMA PRUMOQUANT V3.4 (MANTENDO TODAS AS SUAS REGRAS MATRIZES)
# ----------------------------------------------------------------------------
@st.cache_data(ttl=60, show_spinner=False)
def razao_futuro(ticker, spot_etf):
    mapa = {"SPY": ("ES=F", "ES / MES", "S&P 500"), "QQQ": ("NQ=F", "NQ / MNQ", "Nasdaq 100")}
    if ticker not in mapa or not spot_etf: return None, None, None
    simbolo, nome, _ = mapa[ticker]
    try:
        tkf = yf.Ticker(simbolo)
        preco_fut = None
        for per, itv in (("1d", "1m"), ("5d", "1h"), ("10d", "1d")):
            fut = tkf.history(period=per, interval=itv, prepost=True)
            if not fut.empty:
                preco_fut = float(fut["Close"].iloc[-1])
                break
        if not preco_fut: return None, None, None
        return nome, preco_fut, preco_fut / spot_etf
    except Exception: return None, None, None

@st.cache_data(ttl=3600, show_spinner=False)
def taxa_juros_automatica():
    try:
        h = yf.Ticker("^IRX").history(period="5d")
        if not h.empty: return float(h["Close"].iloc[-1]) / 100.0
    except Exception: pass
    return None

def calcular_vwap(hist):
    mask = [(t.time() >= dtime(9, 30)) and (t.time() <= dtime(16, 0)) for t in hist.index]
    h = hist[mask] if any(mask) else hist
    tipico = (h["High"] + h["Low"] + h["Close"]) / 3
    vol = h["Volume"]
    cum_v = vol.cumsum().replace(0, np.nan)
    vwap = (tipico * vol).cumsum() / cum_v
    var = (tipico ** 2 * vol).cumsum() / cum_v - vwap ** 2
    return h.index, vwap.ffill(), np.sqrt(var.clip(lower=0)).ffill()

def calcular_gex(calls, puts, spot, venc_str, r):
    dias = max((pd.Timestamp(venc_str) - pd.Timestamp.now()).days, 0)
    T = max(dias / 252, 0.5 / 252)
    linhas = []
    
    for df, tipo in ((calls, "call"), (puts, "put")):
        if df is None or df.empty: continue
        for _, op in df.iterrows():
            k = num(op.get("strike"))
            iv = num(op.get("impliedVolatility"))
            oi = num(op.get("openInterest"))
            if iv <= 0 or oi <= 0 or not (spot * 0.90 <= k <= spot * 1.10): continue
            g = gamma_bs(spot, k, T, r, iv) * oi * 100 * spot
            linhas.append({"strike": k, "gex": g if tipo == "call" else -g})

    gex_df = pd.DataFrame(linhas)
    if gex_df.empty: return gex_df, None, None, None, None, False, {}

    por_strike = gex_df.groupby("strike")["gex"].sum().reset_index()
    pico = por_strike["gex"].abs().max()
    
    # FILTRO A (Anti-chuvisco)
    if pico > 0: por_strike = por_strike[por_strike["gex"].abs() >= 0.01 * pico]
    por_strike = por_strike.reset_index(drop=True)
    if por_strike.empty: return por_strike, None, None, None, None, False, {}

    gmax, gmin = float(por_strike["gex"].max()), float(por_strike["gex"].min())
    call_wall = por_strike.loc[por_strike["gex"].idxmax(), "strike"] if gmax > 0 else None
    put_wall = por_strike.loc[por_strike["gex"].idxmin(), "strike"] if gmin < 0 else None

    ordenado = por_strike.sort_values("strike").reset_index(drop=True)
    acum = ordenado["gex"].cumsum().values
    cruz = [float(ordenado["strike"][i]) for i in range(1, len(acum)) if (acum[i-1] < 0 <= acum[i]) or (acum[i-1] >= 0 > acum[i])]
    flip, dominio = (min(cruz, key=lambda k: abs(k - spot)), None) if cruz else (None, "neg" if acum[-1] < 0 else "pos")

    try: venc_hoje = (pd.Timestamp(venc_str).date() == pd.Timestamp.now().date())
    except Exception: venc_hoje = False

    barras = identificar_barras_chave(por_strike, spot)
    return por_strike, call_wall, put_wall, flip, dominio, venc_hoje, barras

def identificar_barras_chave(por_strike, spot):
    b = {}
    if por_strike is None or por_strike.empty: return b
    pos = por_strike[por_strike["gex"] > 0].copy()
    neg = por_strike[por_strike["gex"] < 0].copy()

    if not pos.empty:
        b["maior_pos"] = float(pos.loc[pos["gex"].idxmax(), "strike"])
        pos["dist"] = (pos["strike"] - spot).abs()
        b["primeira_pos"] = float(pos.loc[pos["dist"].idxmin(), "strike"])
        b["ultima_pos"] = float(pos["strike"].max())
    if not neg.empty:
        b["maior_neg"] = float(neg.loc[neg["gex"].idxmin(), "strike"])
        neg["dist"] = (neg["strike"] - spot).abs()
        b["primeira_neg"] = float(neg.loc[neg["dist"].idxmin(), "strike"])
        b["ultima_neg"] = float(neg["strike"].min())
    return b

# ----------------------------------------------------------------------------
# ITEM 23: LOGICA DE CLASSIFICACAO DA CALIBRACAO POR TERÇOS DE SPREAD
# ----------------------------------------------------------------------------
def calcular_fluxo_institucional_v34(calls, puts):
    """
    Implementação da Regra de Calibração 23 (Terços do Spread).
    Elimina o viés do decaimento (theta) limpando o miolo ambíguo do spread.
    """
    total_comprado, total_vendido = 0.0, 0.0
    fluxo_por_strike = {}

    for df, tipo_opcao in ((calls, "call"), (puts, "put")):
        if df is None or df.empty: continue
        for _, row in df.iterrows():
            k = num(row.get("strike"))
            vol = num(row.get("volume"))
            bid = num(row.get("bid"))
            ask = num(row.get("ask"))
            ultimo = num(row.get("lastPrice"))
            
            if vol <= 0 or bid >= ask or ultimo <= 0: continue
            
            spread = ask - bid
            # Dividindo o spread em 3 partes iguais
            terco_baixo = bid + (spread / 3.0)
            terco_alto = ask - (spread / 3.0)
            
            premium = ultimo * vol * 100
            
            # Classificação por Terço de Fluxo Estrito
            if ultimo >= terco_alto:  # Agressão na Compra (Terço Superior)
                if tipo_opcao == "call":
                    total_comprado += premium
                    fluxo_por_strike[k] = fluxo_por_strike.get(k, 0.0) + premium
                else:
                    total_vendido += premium
                    fluxo_por_strike[k] = fluxo_por_strike.get(k, 0.0) - premium
            elif ultimo <= terco_baixo:  # Agressão na Venda (Terço Inferior)
                if tipo_opcao == "call":
                    total_vendido += premium
                    fluxo_por_strike[k] = fluxo_por_strike.get(k, 0.0) - premium
                else:
                    total_comprado += premium
                    fluxo_por_strike[k] = fluxo_por_strike.get(k, 0.0) + premium
            # Se cair no miolo entre terco_baixo e terco_alto, descarta (Item 23)

    return total_comprado, total_vendido, fluxo_por_strike

def identificar_barras_fluxo(strikes, spot):
    b = {}
    if not strikes: return b
    df = pd.DataFrame([{"strike": num(k), "net": num(v)} for k, v in strikes.items()])
    df = df[df["net"] != 0]
    if df.empty: return b
    pico = df["net"].abs().max()
    if pico > 0: df = df[df["net"].abs() >= 0.01 * pico]
    if df.empty: return b

    pos = df[df["net"] > 0].copy()
    neg = df[df["net"] < 0].copy()

    if not pos.empty:
        b["maior_pos"] = float(pos.loc[pos["net"].idxmax(), "strike"])
        pos["dist"] = (pos["strike"] - spot).abs()
        b["primeira_pos"] = float(pos.loc[pos["dist"].idxmin(), "strike"])
        b["ultima_pos"] = float(pos["strike"].max())
    if not neg.empty:
        b["maior_neg"] = float(neg.loc[neg["net"].idxmin(), "strike"])
        neg["dist"] = (neg["strike"] - spot).abs()
        b["primeira_neg"] = float(neg.loc[neg["dist"].idxmin(), "strike"])
        b["ultima_neg"] = float(neg["strike"].min())
    return b

def detectar_setup(barras, spot, flip, dominio, cw, pw):
    if not barras: return None
    def perto(strike, tol=0.0020): return strike is not None and (abs(spot - strike) / spot) < tol

    pp, mp, up = barras.get("primeira_pos"), barras.get("maior_pos"), barras.get("ultima_pos")
    pn, mn, un = barras.get("primeira_neg"), barras.get("maior_neg"), barras.get("ultima_neg")

    if pn and perto(pn) and spot >= pn and mp and mp > spot:
        return dict(codigo="S6", nome="Proteção no Hedge Negativo", vies="COMPRADOR (bounce)",
                    gatilho=f"preço testando a 1ª barra− ({pn:.0f}) com ímã positivo em {mp:.0f} acima",
                    alvo=f"{mp:.0f} (ímã) / retorno ao VWAP",
                    invalidacao=f"perder {pn:.0f} com fluxo vendedor (defesa falhou)",
                    obs="Setup mais assertivo: dealer defende agressivamente a zona negativa.")

    if un and perto(un) and spot <= (mn or un):
        return dict(codigo="S4", nome="Pullback no Fundo", vies="COMPRADOR (bounce/reversão)",
                    gatilho=f"preço na última barra− ({un:.0f}) — exaustão da venda",
                    alvo=f"{mp:.0f} (ímã acima)" if mp else "VWAP / ímã acima",
                    invalidacao=f"aceitação abaixo de {un:.0f} (flush continua)",
                    obs="Movimento costuma ser rápido no início e estancar perto do ímã.")

    if up and perto(up) and mp and mp < spot:
        return dict(codigo="S3", nome="Pullback no Topo", vies="VENDEDOR (recuo ao ímã)",
                    gatilho=f"preço na última barra+ ({up:.0f}) com ímã em {mp:.0f} abaixo",
                    alvo=f"{mp:.0f} (ímã abaixo)", invalidacao=f"romper e sustentar acima de {up:.0f}",
                    obs="Reversão para o ímã inferior, salvo se instituições forçarem continuação.")

    if flip and spot > flip and mp and mp > spot:
        return dict(codigo="S1", nome="Rompimento Altista", vies="COMPRADOR (momentum)",
                    gatilho=f"preço cruzou o flip ({flip:.0f}) com ímã {mp:.0f} acima aberto",
                    alvo=f"{mp:.0f} (maior+)", invalidacao=f"voltar para baixo do flip ({flip:.0f})",
                    obs="Aceleração livre até o call wall ou ímã.")

    if pn and spot < pn:
        return dict(codigo="S2", nome="Rompimento Baixista", vies="VENDEDOR (short/flush)",
                    gatilho=f"preço perdeu a 1ª barra− ({pn:.0f}) e entrou em terreno aberto",
                    alvo=f"{mn:.0f} (maior− abaixo)" if mn else "Última barra−",
                    invalidacao=f"recuperar e aceitar acima de {pn:.0f}",
                    obs="Zona de aceleração dos dealers (short gamma). Movimentos violentos.")

    if mp and mn and mn <= spot <= mp:
        return dict(codigo="S5", nome="Consolidação (Pinning)", vies="NEUTRO (disputa/range)",
                    gatilho=f"preço preso entre o ímã+ ({mp:.0f}) e o ímã− ({mn:.0f})",
                    alvo=f"Extremos da consolidação ({mn:.0f} a {mp:.0f})", invalidacao="Romper um dos extremos",
                    obs="Evitar entradas no meio do range. Operar apenas as extremidades.")
    return None

# ----------------------------------------------------------------------------
# MONTAGEM E LOGICA DO RENDERIZADOR COMPLETO
# ----------------------------------------------------------------------------
# Gerenciamento de Autorefresh Dinâmico (Item 3)
agora_ny = datetime.now()
janela_quente = (agora_ny.time() >= dtime(9, 0)) and (agora_ny.time() <= dtime(9, 45))
st_autorefresh(interval=30000 if janela_quente else 60000, key="pq_refresh")

# Cabeçalho PrumoQuant
st.markdown(f"""
<div class="pq-header">
    <div>
        <span class="pq-logo">Prumo<span class="fio">Quant</span> <small style='font-size:0.8rem;color:#6b7280;'>v3.4</small></span>
        <span class="pq-sub">Trading Institucional & Opções</span>
    </div>
    <div class="pq-meta">
        <b>NY:</b> {agora_ny.strftime('%H:%M:%S')} | <b>BR:</b> {datetime.now().strftime('%H:%M')}<br>
        <span style='color:#fbbf24'>● Dados Real-Time Tradier</span>
    </div>
</div>
""", unsafe_allow_html=True)

# Processador Principal de Dados
tickers_para_rodar = ["SPY", "QQQ"] if MODO_VISAO == "SPY + QQQ lado a lado" else [TICKER_UNICO]
r_global = taxa_juros_automatica() if USAR_R_AUTO else TAXA_MANUAL
if r_global is None: r_global = TAXA_MANUAL

dados_ativos = {}
for tk in tickers_para_rodar:
    hist, pc, calls, puts, venc = buscar_dados(tk)
    if hist.empty or calls is None:
        st.warning(f"Aguardando primeira resposta da API da Tradier para o ativo {tk}...")
        st.stop()
    
    spot = float(hist["Close"].iloc[-1])
    idx_vwap, vwap_ser, sigma_ser = calcular_vwap(hist)
    vwap_val = float(vwap_ser.iloc[-1]) if not vwap_ser.empty else spot
    sigma_val = float(sigma_ser.iloc[-1]) if not sigma_ser.empty else 0.0
    
    por_strike, cw, pw, flip, dom, v_hoje, b_gex = calcular_gex(calls, puts, spot, venc, r_global)
    comp, vend, strk_fluxo = calcular_fluxo_institucional_v34(calls, puts)
    b_fluxo = identificar_barras_fluxo(strk_fluxo, spot)
    
    dados_ativos[tk] = {
        "spot": spot, "vwap": vwap_val, "sigma": sigma_val, "hist": hist, "p_close": pc,
        "por_strike": por_strike, "cw": cw, "pw": pw, "flip": flip, "dominio": dom, "0dte": v_hoje,
        "b_gex": b_gex, "comp": comp, "vend": vend, "strk_fluxo": strk_fluxo, "b_fluxo": b_fluxo, "venc": venc
    }

# Banner do Veto SPY × QQQ (Item 11)
if MODO_VISAO == "SPY + QQQ lado a lado":
    s_spy = detectar_setup(dados_ativos["SPY"]["b_gex"], dados_ativos["SPY"]["spot"], dados_ativos["SPY"]["flip"], dados_ativos["SPY"]["dominio"], dados_ativos["SPY"]["cw"], dados_ativos["SPY"]["pw"])
    s_qqq = detectar_setup(dados_ativos["QQQ"]["b_gex"], dados_ativos["QQQ"]["spot"], dados_ativos["QQQ"]["flip"], dados_ativos["QQQ"]["dominio"], dados_ativos["QQQ"]["cw"], dados_ativos["QQQ"]["pw"])
    
    if s_qqq and s_spy and s_qqq["codigo"] == "S2" and s_spy["codigo"] != "S2":
        st.markdown('<div class="setup-linha" style="border-color:#ef4444; background:#2d1414;">⚠️ <b>VETO ATIVO:</b> QQQ armou Rompimento Baixista (S2) mas o SPY não confirmou. Operação proibida por desalinhamento.</div>', unsafe_allow_html=True)

# Renderização de Abas Estilo Quantico
tab1, tab2, tab3 = st.tabs(["📊 Visão Geral", "⚡ Delta-Hedging (GEX)", "🌊 Fluxo de Agressão"])

with tab1:
    col_layout = st.columns(2) if (MODO_VISAO == "SPY + QQQ lado a lado" and not MODO_CELULAR) else [st.container()]
    
    for idx, tk in enumerate(tickers_para_rodar):
        target_col = col_layout[idx] if len(col_layout) > 1 else st
        d = dados_ativos[tk]
        
        with target_col:
            st.subheader(f"Painel Principal {tk}")
            
            # Régua de fluxo estilo Volume Imbalance da Quantico (Item 19)
            tot_f = d["comp"] + d["vend"]
            p_comp = (d["comp"] / tot_f * 100) if tot_f > 0 else 50.0
            p_vend = (d["vend"] / tot_f * 100) if tot_f > 0 else 50.0
            net_f = d["comp"] - d["vend"]
            
            # Item 24: Janela recente em linguagem simples
            status_recente = "INSTITUIÇÕES COMPRANDO AGORA" if p_comp > 60 else ("INSTITUIÇÕES VENDENDO AGORA" if p_vend > 60 else "EM DISPUTA NEUTRA")
            
            st.markdown(f"""
            <div class="fluxobar-wrap">
                <div class="fluxobar-top">
                    <span><b>RÉGUA DE FLUXO (IMBALANCE)</b></span>
                    <span class="{'verde' if net_f>=0 else 'vermelho'}"><b>{status_recente}</b></span>
                </div>
                <div class="fluxobar">
                    <div class="verde-seg" style="width: {p_comp}%"></div>
                    <div class="verm-seg" style="width: {p_vend}%"></div>
                </div>
                <div class="fluxobar-sub">
                    <span class="verde">▲ {p_comp:.1f}% ({fmt_usd(d['comp'])})</span>
                    <span class="{ 'verde' if net_f>=0 else 'vermelho' }">NET: {fmt_usd(net_f)}</span>
                    <span class="vermelho">▼ {p_vend:.1f}% ({fmt_usd(d['vend'])})</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # Setup em uma linha discreta (Item 19)
            s = detectar_setup(d["b_gex"], d["spot"], d["flip"], d["dominio"], d["cw"], d["pw"])
            if s:
                st.markdown(f'<div class="setup-linha">⚙️ <b>Setup Ativo {tk}:</b> <span class="amarelo">{s["codigo"]} - {s["nome"]}</span> | Viés: <b>{s["vies"]}</b> | Alvo: {s["alvo"]}</div>', unsafe_allow_html=True)
            
            # Cartões e tabelas recolhidos em Expander abaixo dos resumos gráficos (Item 19)
            with st.expander("👁️ Ver Cartões Estratégicos, Bandas VWAP e Conversor Futuro"):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Preço Spot", f"${d['spot']:.2f}")
                c2.metric("VWAP Regular", f"${d['vwap']:.2f}")
                c3.metric("Call Wall Muro", f"${d['cw']:.1f}" if d['cw'] else "N/A")
                c4.metric("Put Wall Muro", f"${d['pw']:.1f}" if d['pw'] else "N/A")
                
                # Calculadora de Conversão ES/NQ para a Boleta (Item 10)
                n_fut, p_fut, r_fut = razao_futuro(tk, d["spot"])
                if r_fut:
                    st.markdown(f"""
                    | Nível ETF ({tk}) | Preço Equivalente no Futuro ({n_fut}) | Função Operacional |
                    | :--- | :--- | :--- |
                    | **Spot:** ${d['spot']:.2f} | **${d['spot']*r_fut:.1f}** | Preço Atual de Tela |
                    | **Call Wall:** ${d['cw']:.1f} | **${d['cw']*r_fut:.1f}** | Resistência Máxima / Alvo |
                    | **Put Wall:** ${d['pw']:.1f} | **${d['pw']*r_fut:.1f}** | Suporte Extremo / Defesa |
                    | **Flip:** ${d['flip']:.1f} | **${d['flip']*r_fut:.1f}** | Divisor de Águas do Regime |
                    """, unsafe_allow_html=True)

with tab2:
    st.subheader("Curva Física de Exposição Gamma (GEX)")
    for tk in tickers_para_rodar:
        d = dados_ativos[tk]
        fig = go.Figure()
        fig.add_trace(go.Bar(x=d["por_strike"]["strike"], y=d["por_strike"]["gex"], name="GEX", marker_color=np.where(d["por_strike"]["gex"]>=0, '#22c55e', '#ef4444')))
        fig.update_layout(title=f"Mapa de Muros de Delta-Hedging para {tk} (Vencimento: {d['venc']})", template="plotly_dark", background_color="#0b0f14")
        st.plotly_chart(fig, use_container_width=True)

with tab3:
    st.subheader("Fluxo Líquido Institucional por Strike (Agressão)")
    for tk in tickers_para_rodar:
        d = dados_ativos[tk]
        fig_f = go.Figure()
        ks = list(d["strk_fluxo"].keys())
        vs = list(d["strk_fluxo"].values())
        if ks:
            fig_f.add_trace(go.Bar(x=ks, y=vs, name="Net Premium", marker_color=np.where(np.array(vs)>=0, '#22c55e', '#ef4444')))
        fig_f.update_layout(title=f"Prévia do Direcional do Dealer por Strike (DDF) — {tk}", template="plotly_dark")
        st.plotly_chart(fig_f, use_container_width=True)
