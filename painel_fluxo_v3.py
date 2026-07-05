# ============================================================================
# PAINEL DE FLUXO DE OPÇÕES — VERSÃO 3.1 "MODO ABERTURA" (ESTUDO PESSOAL)
# PrumoQuant · https://prumoquant.streamlit.app
# ============================================================================
# Novidades da v3.1 em relação à v3:
#   1. VISÃO DUPLA: SPY + QQQ lado a lado na mesma tela, com LEITURA
#      CRUZADA automática (regra: os muros do SPY são os mais fortes do
#      mercado; queda no QQQ tende a frear quando o SPY encosta no put
#      wall — possível repique; atravessar o paredão exige fluxo
#      vendedor persistente).
#   2. MODO ABERTURA: selo de PRÉ-MERCADO (4h–9h30 NY), relógios de NY e
#      Brasília no cabeçalho, score heurístico de viés de abertura
#      (−100 a +100) e playbook de abertura com cenários condicionais.
#   3. Atualização adaptativa: 30 s na janela quente (9h00–9h45 NY),
#      60 s no restante.
#   4. Quando o GEX acumulado não cruza zero na banda ±10%, o painel
#      informa o regime dominante (positivo/negativo em toda a banda).
#   5. FILTRO A (limpeza de gamma): strikes com GEX abaixo de 1% do pico
#      são descartados da curva — remove o "chuvisco" de open interest
#      fantasma / opções muito fora do dinheiro, deixando muros e flip
#      mais nítidos, sem perder nada relevante.
#   6. FILTRO C (aviso 0DTE): quando o vencimento analisado é HOJE, o
#      painel avisa no gráfico e no playbook que parte do open interest
#      pode já estar liquidada e a curva envelhece rápido (o OI do
#      yfinance só atualiza 1x/dia).
#   7. FASE 1.1 — BARRAS-CHAVE: identifica e marca as 6 barras-chave do
#      Delta-Hedging (primeira/maior/última, positiva e negativa) no
#      gráfico e no playbook. É a fundação para detectar os 6 setups.
#   8. FASE 1.2 — MOTOR DOS 6 SETUPS: detecta qual setup do método está
#      armado (S1 Rompimento Altista, S2 Rompimento Baixista, S3 Pullback
#      no Topo, S4 Pullback no Fundo, S5 Consolidação, S6 Proteção no
#      Hedge Negativo) pela posição do preço frente às barras-chave, e
#      narra gatilho/alvo/invalidação. Exibido em banner no topo e no
#      playbook. Rótulos das barras no gráfico melhorados (legibilidade).
#   9. REFINO S2: distingue "iminente" (preço colado na 1ª barra−, banner
#      amarelo, aguardar) de "confirmado" (preço abaixo com margem). Evita
#      chamar de rompimento um simples toque na barra.
#  10. FASE 1.6 — CALCULADORA DE CONVERSÃO: converte os níveis do ETF
#      (SPY/QQQ) para o futuro (ES/NQ) usando a razão calculada AO VIVO
#      (basis = preço do futuro ÷ preço do ETF). Tabela com spot, muros e
#      flip já no preço do futuro, para operar na corretora.
#  11. FASE 1.5 — VETO SPY×QQQ: regra de ouro do método em código. SPY dá
#      a permissão, QQQ é o gatilho. Setup do QQQ contra o SPY = VETO
#      (banner, playbook e leitura cruzada); S2 no QQQ sem S2 no SPY =
#      VETO; alinhados = "permissão concedida".
#  12. FASE 1.7 — JUROS AUTOMÁTICO: r buscado do ^IRX (T-bill 13 semanas)
#      com cache de 1 h e fallback manual. Origem exibida no cabeçalho.
#  13. FASE 2.2 — MODO CELULAR: toggle na barra lateral. Gamma vira
#      barras HORIZONTAIS (strikes no eixo Y), cartões em 2 linhas de 3,
#      layout todo empilhado (dual = SPY sobre QQQ).
#  14. MENTOR DE DISCIPLINA: regras escritas pelo próprio operador; uma
#      por dia em banner + expander com todas. Estratégia, não sorte.
#
# HONESTIDADE TÉCNICA (não remover):
#   - Dados yfinance: gratuitos e ATRASADOS (~15 min em opções); open
#     interest atualiza 1x/dia (de madrugada — por isso os muros da manhã
#     valem para o dia). Opções NÃO negociam no pré-mercado: antes das
#     9h30 de NY não existe fluxo de opções para ninguém.
#   - O "score de abertura" é um ESCORE HEURÍSTICO (nota composta de
#     fatores com pesos), não probabilidade estatística real.
#   - Net premium é estimativa por diferença de volume + inferência
#     bid/ask, não fluxo de tick.
#   - Ferramenta de ESTUDO. Não é recomendação de investimento.
# ============================================================================

import os
from datetime import datetime, time as dtime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from scipy.stats import norm
from streamlit_autorefresh import st_autorefresh

# ----------------------------------------------------------------------------
# CONFIGURAÇÃO DA PÁGINA + ESTILO
# ----------------------------------------------------------------------------
st.set_page_config(page_title="PrumoQuant — Fluxo de Opções (estudo)",
                   layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    .stApp { background-color: #0b0f14; }
    section[data-testid="stSidebar"] { background-color: #10161d; }
    h1, h2, h3, p, span, label { color: #e6edf3; }

    .cartao {
        background: #131a22; border: 1px solid #1f2937; border-radius: 10px;
        padding: 12px 14px 9px 14px; height: 100%;
    }
    .cartao .rotulo { font-size: 0.68rem; letter-spacing: 1px;
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
MODO_VISAO = st.sidebar.radio("Modo de visão",
                              ["Um ativo", "SPY + QQQ lado a lado"])
TICKER_UNICO = st.sidebar.selectbox("Ativo (modo um ativo)", ["SPY", "QQQ"])
MODO_CELULAR = st.sidebar.checkbox(
    "📱 Modo celular (layout vertical)", value=False,
    help="Gamma em barras horizontais e tudo empilhado — muito mais "
         "legível em tela estreita.")
st.sidebar.markdown("---")
USAR_R_AUTO = st.sidebar.checkbox(
    "Taxa de juros automática (^IRX)", value=True,
    help="Busca a taxa real do T-bill americano de 13 semanas no Yahoo. "
         "Se falhar, usa o valor manual abaixo.")
TAXA_MANUAL = st.sidebar.number_input("Taxa de juros manual (reserva)",
                                      value=0.05, step=0.005, format="%.3f")
MOSTRAR_FUTUROS = st.sidebar.checkbox(
    "Converter níveis para futuros (ES/NQ)", value=True,
    help="Mostra os muros e alvos já convertidos para o preço do futuro "
         "correspondente, para operar na corretora.")
st.sidebar.caption("Ferramenta de ESTUDO. Dados gratuitos/atrasados "
                   "(yfinance). Não é recomendação de investimento.")

# ----------------------------------------------------------------------------
# AUXILIARES
# ----------------------------------------------------------------------------

def num(v):
    """Float seguro: vazio/NaN vira 0 (não contamina somas)."""
    try:
        x = float(v)
        return 0.0 if pd.isna(x) else x
    except (TypeError, ValueError):
        return 0.0


def fmt_usd(v):
    """$1.2M, $340K — formato humano."""
    v = num(v); s = "-" if v < 0 else ""; a = abs(v)
    if a >= 1e9: return f"{s}${a/1e9:.1f}B"
    if a >= 1e6: return f"{s}${a/1e6:.1f}M"
    if a >= 1e3: return f"{s}${a/1e3:.0f}K"
    return f"{s}${a:.0f}"


def gamma_bs(S, K, T, r, sigma):
    """Gamma de Black-Scholes (a 'aceleração' do hedge dos dealers)."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return norm.pdf(d1) / (S * sigma * np.sqrt(T))


@st.cache_data(ttl=25, show_spinner=False)
def buscar_dados(ticker):
    """Histórico 1 min (COM pré/pós-mercado), fechamento anterior e cadeia."""
    tk = yf.Ticker(ticker)
    hist = tk.history(period="1d", interval="1m", prepost=True)

    # Fechamento anterior (para o gap): últimos 5 dias em barras diárias.
    prev_close = None
    diario = tk.history(period="5d", interval="1d")
    if not diario.empty:
        hoje_ny = pd.Timestamp.now(tz=diario.index.tz).date()
        if diario.index[-1].date() == hoje_ny and len(diario) >= 2:
            prev_close = float(diario["Close"].iloc[-2])
        else:
            prev_close = float(diario["Close"].iloc[-1])

    vencs = tk.options
    if not vencs:
        return hist, prev_close, None, None, None
    venc = vencs[0]
    cadeia = tk.option_chain(venc)
    return hist, prev_close, cadeia.calls.copy(), cadeia.puts.copy(), venc


@st.cache_data(ttl=60, show_spinner=False)
def razao_futuro(ticker, spot_etf):
    """
    CALCULADORA DE CONVERSÃO (Fase 1.6).

    Converte níveis do ETF (SPY/QQQ) para o futuro correspondente
    (ES/NQ), que é onde o usuário de fato opera. A razão NÃO é fixa —
    varia com dividendos e juros (o 'basis') — então a calculamos ao
    vivo, dividindo o preço real do futuro pelo preço do ETF.

    Ex.: se ES=F está 7460 e SPY está 745, a razão é ~10,01. Um muro
    em 742 no SPY vira 742 × 10,01 ≈ 7427 no ES.

    Retorna (nome_futuro, nome_micro, razao) ou (None, None, None) se
    o preço do futuro não estiver disponível.
    """
    mapa = {
        "SPY": ("ES=F", "ES / MES", "S&P 500"),
        "QQQ": ("NQ=F", "NQ / MNQ", "Nasdaq 100"),
    }
    if ticker not in mapa or not spot_etf:
        return None, None, None
    simbolo, nome, _ = mapa[ticker]
    try:
        fut = yf.Ticker(simbolo).history(period="1d", interval="1m",
                                         prepost=True)
        if fut.empty:
            return None, None, None
        preco_fut = float(fut["Close"].iloc[-1])
        razao = preco_fut / spot_etf
        return nome, preco_fut, razao
    except Exception:
        return None, None, None


@st.cache_data(ttl=3600, show_spinner=False)
def taxa_juros_automatica():
    """
    JUROS AUTOMÁTICO (Fase 1.7). Busca o ^IRX — rendimento do T-bill
    americano de 13 semanas — que o Yahoo cota em % ao ano (ex.: 5.21).
    É a aproximação padrão da 'taxa livre de risco' do Black-Scholes.
    Cache de 1 hora (juros não muda a cada minuto). Se falhar, o painel
    usa o valor manual da barra lateral (fallback).
    """
    try:
        h = yf.Ticker("^IRX").history(period="5d")
        if h.empty:
            return None
        v = float(h["Close"].iloc[-1])
        if 0 < v < 20:          # sanidade: taxa entre 0% e 20% a.a.
            return v / 100.0
    except Exception:
        pass
    return None


def calcular_vwap(hist):
    """VWAP apenas da sessão regular (9h30–16h NY); pré-mercado fora."""
    mask = [(t.time() >= dtime(9, 30)) and (t.time() <= dtime(16, 0))
            for t in hist.index]
    h = hist[mask] if any(mask) else hist
    tipico = (h["High"] + h["Low"] + h["Close"]) / 3
    vwap = (tipico * h["Volume"]).cumsum() / h["Volume"].cumsum().replace(0, np.nan)
    return h.index, vwap.ffill()


def calcular_gex(calls, puts, spot, venc_str, r):
    """
    GEX por strike (calls +, puts −), banda ±10% do spot.
    Retorna também 'dominio': se o acumulado não cruza zero, informa se a
    banda inteira é positiva ou negativa (em vez de 'flip não identificado').
    """
    dias = max((pd.Timestamp(venc_str) - pd.Timestamp.now()).days, 0)
    T = max(dias / 252, 0.5 / 252)

    linhas = []
    for df, tipo in ((calls, "call"), (puts, "put")):
        for _, op in df.iterrows():
            k = num(op.get("strike"))
            iv = num(op.get("impliedVolatility"))
            oi = num(op.get("openInterest"))
            if iv <= 0 or oi <= 0 or not (spot * 0.90 <= k <= spot * 1.10):
                continue
            g = gamma_bs(spot, k, T, r, iv) * oi * 100 * spot
            linhas.append({"strike": k, "gex": g if tipo == "call" else -g})

    gex_df = pd.DataFrame(linhas)
    if gex_df.empty:
        return gex_df, None, None, None, None, False

    por_strike = gex_df.groupby("strike")["gex"].sum().reset_index()

    # -------- FILTRO A: recorte do "chuvisco" de gamma irrelevante --------
    # Strikes cujo GEX é uma fração ínfima do maior GEX da curva não
    # representam pressão real de hedge (open interest fantasma / opções
    # muito fora do dinheiro). Descartamos os que ficam abaixo de 1% do
    # pico absoluto — os muros e o flip ficam mais nítidos, sem perder
    # nada relevante. É o "aumentar o contraste" da radiografia.
    pico = por_strike["gex"].abs().max()
    if pico > 0:
        por_strike = por_strike[por_strike["gex"].abs() >= 0.01 * pico]
    por_strike = por_strike.reset_index(drop=True)
    if por_strike.empty:
        return por_strike, None, None, None, None, False

    call_wall = por_strike.loc[por_strike["gex"].idxmax(), "strike"]
    put_wall = por_strike.loc[por_strike["gex"].idxmin(), "strike"]

    ordenado = por_strike.sort_values("strike").reset_index(drop=True)
    acum = ordenado["gex"].cumsum().values
    cruz = [float(ordenado["strike"][i]) for i in range(1, len(acum))
            if (acum[i-1] < 0 <= acum[i]) or (acum[i-1] >= 0 > acum[i])]
    if cruz:
        flip, dominio = min(cruz, key=lambda k: abs(k - spot)), None
    else:
        flip, dominio = None, ("neg" if acum[-1] < 0 else "pos")

    # -------- FILTRO C: o vencimento analisado é HOJE? (0DTE) --------
    # Se sim, parte do open interest pode já ter sido exercida/liquidada
    # e o yfinance só atualiza o OI 1x/dia — a curva envelhece rápido.
    try:
        venc_hoje = (pd.Timestamp(venc_str).date()
                     == pd.Timestamp.now().date())
    except Exception:
        venc_hoje = False

    # -------- BARRAS-CHAVE (Fase 1.1) --------
    barras = identificar_barras_chave(por_strike, spot)

    return por_strike, call_wall, put_wall, flip, dominio, venc_hoje, barras


def identificar_barras_chave(por_strike, spot):
    """
    Identifica as 6 barras-chave do Delta-Hedging, conforme o método:

    Lado POSITIVO (gamma+, zonas ímã / estabilizadoras):
      - primeira+ : positiva mais próxima do preço → linha de defesa/flip
      - maior+    : maior barra positiva → o "ímã do dia" (vira suporte
                    se rompida por cima)
      - última+   : positiva mais distante acima → exaustão da alta

    Lado NEGATIVO (gamma−, zonas de aceleração):
      - primeira− : negativa mais próxima do preço → a mais defendida
                    pelo dealer (ele evita hedge agressivo aqui)
      - maior−    : maior barra negativa (em módulo) → alvo da aceleração
      - última−   : negativa mais distante abaixo → exaustão da queda

    "Relevância" já vem garantida pelo Filtro A (chuvisco removido antes).
    Retorna dicionário {rótulo: strike} apenas com o que existir.
    """
    b = {}
    if por_strike is None or por_strike.empty:
        return b

    pos = por_strike[por_strike["gex"] > 0].copy()
    neg = por_strike[por_strike["gex"] < 0].copy()

    # ----- Lado positivo -----
    if not pos.empty:
        # Maior positiva (ímã): maior valor de GEX
        b["maior_pos"] = float(pos.loc[pos["gex"].idxmax(), "strike"])
        # Primeira positiva: a positiva de strike mais próximo do preço
        pos["dist"] = (pos["strike"] - spot).abs()
        b["primeira_pos"] = float(pos.loc[pos["dist"].idxmin(), "strike"])
        # Última positiva: a positiva de maior strike (topo da faixa +)
        b["ultima_pos"] = float(pos["strike"].max())

    # ----- Lado negativo -----
    if not neg.empty:
        # Maior negativa (alvo): GEX mais negativo (menor valor)
        b["maior_neg"] = float(neg.loc[neg["gex"].idxmin(), "strike"])
        # Primeira negativa: a negativa de strike mais próximo do preço
        neg["dist"] = (neg["strike"] - spot).abs()
        b["primeira_neg"] = float(neg.loc[neg["dist"].idxmin(), "strike"])
        # Última negativa: a negativa de menor strike (fundo da faixa −)
        b["ultima_neg"] = float(neg["strike"].min())

    return b


def detectar_setup(barras, spot, flip, dominio, cw, pw):
    """
    MOTOR DOS 6 SETUPS (Fase 1.2).

    Recebe as barras-chave e a posição do preço e identifica qual dos 6
    setups do método está ARMADO (ou nenhum claro). Retorna um dicionário:
      {codigo, nome, vies, alvo, gatilho, invalidacao, obs}

    Lógica (proximidade medida em % do preço; "colado" = < 0.15%):
      S6 Proteção Hedge Negativo: preço testando a 1ª barra− (por cima),
         com barras+ acima (ímãs). O mais assertivo — dealer defende.
      S4 Pullback no Fundo: preço na última barra− (exaustão da queda).
      S3 Pullback no Topo: preço na última barra+ (exaustão da alta).
      S1 Rompimento Altista: preço acima do flip, ímã (maior+) acima.
      S2 Rompimento Baixista: preço abaixo da 1ª barra− (perdeu o nível).
      S5 Consolidação: preço entre maior+ acima e maior− abaixo (pinning).
    Testados em ordem de prioridade; o primeiro que casar vence.
    """
    if not barras:
        return None

    def prox(strike):
        return abs(spot - strike) / spot if strike else 9.9

    def perto(strike, tol=0.0020):     # ~0,20%
        return strike is not None and prox(strike) < tol

    pp = barras.get("primeira_pos")
    mp = barras.get("maior_pos")
    up = barras.get("ultima_pos")
    pn = barras.get("primeira_neg")
    mn = barras.get("maior_neg")
    un = barras.get("ultima_neg")

    # ---- S6: Proteção no Hedge Negativo (mais assertivo) ----
    # Preço testando a 1ª barra negativa por cima, com ímã(s) positivo(s)
    # acima para dar suporte à defesa do dealer.
    if pn and perto(pn) and spot >= pn and mp and mp > spot:
        return dict(
            codigo="S6", nome="Proteção no Hedge Negativo",
            vies="COMPRADOR (bounce)",
            gatilho=f"preço testando a 1ª barra− ({pn:.0f}) com ímã "
                    f"positivo em {mp:.0f} acima",
            alvo=f"{mp:.0f} (ímã) / retorno ao VWAP",
            invalidacao=f"perder {pn:.0f} com fluxo vendedor (defesa falhou)",
            obs="Setup mais assertivo: dealer defende agressivamente a "
                "zona negativa. Confirmar defesa do SPY na mesma região.")

    # ---- S4: Pullback no Fundo (exaustão da queda) ----
    if un and perto(un) and spot <= (mn or un):
        return dict(
            codigo="S4", nome="Pullback no Fundo",
            vies="COMPRADOR (bounce/reversão)",
            gatilho=f"preço na última barra− ({un:.0f}) — exaustão da venda",
            alvo=f"{mp:.0f} (ímã acima)" if mp else "VWAP / ímã acima",
            invalidacao=f"aceitação abaixo de {un:.0f} (flush continua)",
            obs="Movimento costuma ser rápido no início e estancar perto "
                "do ímã. Confirmar exaustão no SPY.")

    # ---- S3: Pullback no Topo (exaustão da alta) ----
    if up and perto(up) and mp and mp < spot:
        return dict(
            codigo="S3", nome="Pullback no Topo",
            vies="VENDEDOR (recuo ao ímã)",
            gatilho=f"preço na última barra+ ({up:.0f}) com ímã em "
                    f"{mp:.0f} abaixo",
            alvo=f"{mp:.0f} (ímã abaixo)",
            invalidacao=f"romper e sustentar acima de {up:.0f} "
                        f"(continuação altista)",
            obs="Reversão para o ímã inferior, salvo se instituições "
                "forçarem continuação. Confirmar com SPY na última barra+.")

    # ---- S2: Rompimento Baixista (o mais perigoso) ----
    # Distinção importante: "testando/iminente" (preço a centavos da 1ª
    # barra negativa, ainda encostado) NÃO é o mesmo que "confirmado"
    # (preço claramente abaixo). O método exige rompimento com margem,
    # não um toque. Usamos 0,15% de folga como fronteira.
    if pn and spot < pn:
        margem = (pn - spot) / spot  # quão abaixo da 1ª negativa
        if margem < 0.0015:
            return dict(
                codigo="S2", nome="Rompimento Baixista (IMINENTE)",
                status="iminente", vies="VENDEDOR — aguardar confirmação",
                gatilho=f"preço colado na 1ª barra− ({pn:.0f}), ainda sem "
                        f"rompimento confirmado (margem {margem*100:.2f}%)",
                alvo=f"{mn:.0f} (maior barra−) SE confirmar" if mn
                     else "próximo suporte",
                invalidacao=f"voltar a se firmar acima de {pn:.0f}",
                obs="NÃO é rompimento ainda — o preço está testando. Esperar "
                    "fechamento abaixo COM o SPY também perdendo o nível. "
                    "Entrar aqui é antecipar um movimento não confirmado.")
        return dict(
            codigo="S2", nome="Rompimento Baixista",
            status="confirmado", vies="VENDEDOR (aceleração)",
            gatilho=f"preço abaixo da 1ª barra− ({pn:.0f}), "
                    f"margem {margem*100:.2f}%",
            alvo=f"{mn:.0f} (maior barra−)" if mn else "próximo suporte",
            invalidacao=f"retomar acima de {pn:.0f}",
            obs="O MAIS PERIGOSO: o dealer ainda pode estar defendendo. "
                "EXIGE que o SPY também tenha perdido o nível. Proteja em "
                "break-even assim que possível.")

    # ---- S1: Rompimento Altista ----
    if flip and spot > flip and mp and mp > spot:
        return dict(
            codigo="S1", nome="Rompimento Altista",
            vies="COMPRADOR (continuação)",
            gatilho=f"preço acima do flip ({flip:.0f}), ímã em {mp:.0f} acima",
            alvo=f"{mp:.0f} (ímã)",
            invalidacao=f"perder o flip ({flip:.0f}) de volta",
            obs="Sobe nível a nível até o ímã. Exige SPY LIVRE na direção "
                "(sem muro barrando acima).")

    # ---- S5: Consolidação (pinning) ----
    if mp and mn and mn < spot < mp:
        # Preço espremido entre o maior ímã positivo acima e a maior
        # barra negativa abaixo → tende a lateralizar.
        return dict(
            codigo="S5", nome="Consolidação (pinning)",
            vies="NEUTRO — evitar",
            gatilho=f"preço preso entre maior− ({mn:.0f}) e maior+ ({mp:.0f})",
            alvo="sem alvo direcional (lateral)",
            invalidacao=f"rompimento de {mp:.0f} (alta) ou {mn:.0f} (baixa)",
            obs="Zona de 'pinning' que dilacera traders. Melhor EVITAR até "
                "um rompimento claro com confirmação do SPY.")

    return dict(
        codigo="—", nome="Nenhum setup claro",
        vies="NEUTRO / aguardar",
        gatilho="preço não está numa geometria de setup definida",
        alvo="—", invalidacao="—",
        obs="Aguardar o preço se aproximar de uma barra-chave.")


def aplicar_veto_spy_qqq(dspy, dqqq):
    """
    VETO SPY×QQQ (Fase 1.5) — a regra de ouro do método virando código.

    SPY = PERMISSÃO (muros mais fortes do mercado, benchmark de liquidez).
    QQQ = GATILHO (instrumento de rompimento). Nunca operar o QQQ contra
    o SPY. Esta função compara os setups dos dois ativos e:
      - VETA o setup do QQQ quando o SPY aponta na direção oposta;
      - VETA um S2 no QQQ se o SPY não tiver também perdido o nível
        (exigência explícita do método para rompimento baixista);
      - CONFIRMA ("permissão concedida") quando estão alinhados.
    O veto é gravado dentro do setup do QQQ e aparece no banner, no
    playbook e na leitura cruzada.
    """
    s_q = dqqq.get("setup")
    s_s = dspy.get("setup")
    if not s_q or s_q.get("codigo") in (None, "—"):
        return

    def direcao(s):
        if not s:
            return None
        v = s.get("vies", "")
        if "COMPRADOR" in v:
            return "compra"
        if "VENDEDOR" in v:
            return "venda"
        return None

    dir_q, dir_s = direcao(s_q), direcao(s_s)
    if not dir_q:
        return

    if dir_s and dir_s != dir_q:
        s_q["veto"] = (
            f"SPY em {s_s['codigo']} ({dir_s.upper()}) na direção OPOSTA "
            f"ao {s_q['codigo']} do QQQ ({dir_q.upper()}). Regra do "
            f"método: o SPY dá a permissão — não operar o QQQ contra ele.")
    elif s_q.get("codigo") == "S2" and (not s_s or s_s.get("codigo") != "S2"):
        s_q["veto"] = (
            "S2 (rompimento baixista) no QQQ EXIGE que o SPY também tenha "
            "perdido o nível — e o SPY ainda não confirmou.")
    else:
        s_q["confirmacao"] = "SPY alinhado — permissão concedida."


def estimar_fluxo(calls, puts, ticker, acumular):
    """Net premium estimado + fluxo por strike (fotografias de volume)."""
    k_snap, k_serie, k_strike = f"snap_{ticker}", f"serie_{ticker}", f"strikes_{ticker}"
    arq = f"fluxo_{ticker}_{datetime.now():%Y%m%d}.csv"

    if k_serie not in st.session_state:
        st.session_state[k_serie] = []
        if os.path.exists(arq):
            try:
                st.session_state[k_serie] = (pd.read_csv(arq).fillna(0.0)
                                             .to_dict("records"))
            except Exception:
                pass
    if k_strike not in st.session_state:
        st.session_state[k_strike] = {}

    atual = {}
    for df, eh_call in ((calls, True), (puts, False)):
        for _, op in df.iterrows():
            atual[op["contractSymbol"]] = (
                num(op.get("volume")), num(op.get("lastPrice")),
                num(op.get("bid")), num(op.get("ask")),
                eh_call, num(op.get("strike")))

    bull = bear = 0.0
    anterior = st.session_state.get(k_snap)

    if anterior is not None and acumular:
        for simb, (vol, last, bid, ask, eh_call, strike) in atual.items():
            d_vol = vol - anterior.get(simb, (0,))[0]
            if d_vol <= 0 or last <= 0:
                continue
            meio = (bid + ask) / 2 if (bid > 0 and ask > 0) else last
            # Filtro de liquidez: spread largo torna a inferência frágil.
            if bid > 0 and ask > 0 and meio > 0 and (ask - bid) / meio > 0.25:
                continue
            premio = d_vol * last * 100
            comprador = last >= meio
            eh_bull = (eh_call and comprador) or (not eh_call and not comprador)
            if eh_bull:
                bull += premio
            else:
                bear += premio
            st.session_state[k_strike][strike] = (
                st.session_state[k_strike].get(strike, 0.0)
                + (premio if eh_bull else -premio))

    st.session_state[k_snap] = atual

    if acumular and anterior is not None:
        serie = st.session_state[k_serie]
        ult = serie[-1] if serie else {"bull_acum": 0, "bear_acum": 0,
                                       "net_acum": 0}
        serie.append({"hora": datetime.now().strftime("%H:%M"),
                      "bull_acum": num(ult["bull_acum"]) + bull,
                      "bear_acum": num(ult["bear_acum"]) + bear,
                      "net_acum": num(ult["net_acum"]) + (bull - bear)})
        try:
            pd.DataFrame(serie).to_csv(arq, index=False)
        except Exception:
            pass

    return st.session_state[k_serie], st.session_state[k_strike]


def score_abertura(spot, prev_close, flip, cw, pw, dominio, hist):
    """
    ESCORE HEURÍSTICO de viés de abertura (−100 a +100). NÃO é
    probabilidade: é uma nota composta de 4 fatores com pesos fixos.
      35% gap vs. fechamento anterior (satura em ±0,5%)
      20% regime (spot vs. flip, ou domínio da banda)
      20% espaço entre os muros (mais sala para cima = positivo)
      25% tendência dos últimos ~30 min (satura em ±0,3%)
    """
    fatores = []
    gap = 0.0
    if prev_close:
        gap = (spot - prev_close) / prev_close * 100
        fatores.append((0.35, max(-1.0, min(1.0, gap / 0.5))))
    if flip is not None:
        fatores.append((0.20, 1.0 if spot > flip else -1.0))
    elif dominio:
        fatores.append((0.20, -1.0 if dominio == "neg" else 1.0))
    if cw and pw and cw > pw:
        sala = ((cw - spot) - (spot - pw)) / (cw - pw)
        fatores.append((0.20, max(-1.0, min(1.0, sala))))
    if len(hist) >= 30:
        var = (hist["Close"].iloc[-1] / hist["Close"].iloc[-30] - 1) * 100
        fatores.append((0.25, max(-1.0, min(1.0, var / 0.3))))

    peso_total = sum(p for p, _ in fatores) or 1.0
    score = 100 * sum(p * v for p, v in fatores) / peso_total
    return round(score), gap


def barra_score(score):
    """Barra ASCII do score: [██████░░░░] +62"""
    blocos = max(0, min(10, int(round(abs(score) / 10))))
    return f"[{'█' * blocos}{'░' * (10 - blocos)}] {score:+d}"


def playbook_abertura(ticker, spot, prev_close, cw, pw, flip, dominio,
                      score, gap, agora_ny):
    """Bloco-terminal do MODO ABERTURA (pré-mercado e primeiros minutos)."""
    L = [f"<span class='titulo'>MODO ABERTURA · {ticker} · "
         f"{agora_ny:%H:%M} NY</span>"]
    if prev_close:
        L.append(f"GAP .........: {gap:+.2f}% vs. fechamento anterior "
                 f"({prev_close:.2f})")
    rotulo = ("VIÉS COMPRADOR" if score >= 30 else
              "VIÉS VENDEDOR" if score <= -30 else "NEUTRO / MISTO")
    classe = ("titulo" if score >= 30 else
              "neg" if score <= -30 else "destaque")
    L.append(f"SCORE .......: {barra_score(score)} → "
             f"<span class='{classe}'>{rotulo}</span> "
             f"(escore heurístico, NÃO probabilidade)")
    L.append("")
    if cw and pw:
        colado_cw = abs(spot - cw) / spot < 0.0015
        colado_pw = abs(spot - pw) / spot < 0.0015
        if colado_cw:
            L.append(f"[1] Abrindo COLADO no call wall ({cw:.2f}) → NÃO "
                     f"PERSEGUIR compra; observar aceitação/rejeição.")
        else:
            ref = flip if (flip and pw < flip < spot) else pw
            L.append(f"[1] SE abrir e sustentar acima de {ref:.2f} com fluxo "
                     f"comprador após 9:30 → caminho estatístico até o call "
                     f"wall ({cw:.2f}). Leitura inválida perdendo {ref:.2f}.")
        if colado_pw:
            L.append(f"[2] Abrindo COLADO no put wall ({pw:.2f}) → zona de "
                     f"freio por hedge; NÃO PERSEGUIR venda; observar reação.")
        else:
            ref2 = flip if (flip and spot < flip < cw) else cw
            L.append(f"[2] SE abrir e perder {pw:.2f} com fluxo vendedor "
                     f"confirmando → aceleração abaixo do muro; leitura "
                     f"inválida retomando acima de {ref2:.2f}.")
    L.append("")
    L.append("<span class='aviso'>Opções NÃO negociam no pré-mercado: fluxo "
             "real só após 9:30 NY. Muros do OI da manhã. Dados atrasados "
             "~15 min. Cenários de ESTUDO — não é recomendação; a decisão e "
             "o risco são sempre seus.</span>")
    return "<div class='terminal'>" + "\n".join(L) + "</div>"


def gerar_playbook(t, d, agora_local):
    """Playbook-terminal da sessão (regras da v3 + regime dominante)."""
    L = [f"<span class='titulo'>PLAYBOOK {t} · "
         f"{agora_local:%d/%m/%Y %H:%M}</span>"]
    if d["estado"] == "fechado":
        L.append(f"<span class='destaque'>[MERCADO FECHADO]</span> níveis do "
                 f"pregão de {d['data_sessao']} — leitura preparatória.")
    L.append("")
    if d.get("venc_hoje"):
        L.append("<span class='destaque'>⚠ VENCIMENTO HOJE (0DTE):</span> "
                 "parte do open interest pode já ter sido exercida/liquidada "
                 "e o dado do OI só atualiza 1x/dia — a curva de gamma "
                 "envelhece rápido, sobretudo perto do fechamento. Tratar os "
                 "muros com cautela extra hoje.")
        L.append("")
    spot, flip, dominio = d["spot"], d["flip"], d["dominio"]
    if flip is not None:
        if spot > flip:
            L.append(f"REGIME ......: gamma POSITIVO (spot {spot:.2f} > flip "
                     f"{flip:.2f}) → movimentos contidos; muros como ímã.")
        else:
            L.append(f"REGIME ......: gamma NEGATIVO (spot {spot:.2f} < flip "
                     f"{flip:.2f}) → movimentos tendem a ACELERAR.")
    elif dominio == "neg":
        L.append("REGIME ......: GEX negativo em TODA a banda ±10% → regime "
                 "negativo dominante; sem flip próximo, quedas encontram "
                 "pouco freio estrutural até o put wall.")
    elif dominio == "pos":
        L.append("REGIME ......: GEX positivo em TODA a banda ±10% → regime "
                 "positivo dominante; mercado tende a ficar 'colado'.")
    if d["vwap_atual"]:
        difp = (spot - d["vwap_atual"]) / d["vwap_atual"] * 100
        if abs(difp) < 0.05:
            L.append(f"VWAP ........: {d['vwap_atual']:.2f} · preço COLADO "
                     f"({difp:+.2f}%) → mercado em decisão, sem dono.")
        else:
            lado = "ACIMA" if difp > 0 else "ABAIXO"
            dono = "compradores" if difp > 0 else "vendedores"
            L.append(f"VWAP ........: {d['vwap_atual']:.2f} · preço {lado} "
                     f"({difp:+.2f}%) → {dono} no controle.")
    na = d["net_acum"]
    if na > 0:
        L.append(f"FLUXO .......: {fmt_usd(na)} líquido comprador (estimado).")
    elif na < 0:
        L.append(f"FLUXO .......: {fmt_usd(na)} líquido vendedor (estimado).")
    else:
        L.append("FLUXO .......: sem leitura acumulada nesta sessão.")
    cw, pw = d["cw"], d["pw"]
    if cw and pw:
        L.append(f"MUROS .......: call wall {cw:.0f} "
                 f"({(cw-spot)/spot*100:+.2f}%) | put wall {pw:.0f} "
                 f"({(pw-spot)/spot*100:+.2f}%)")

        # ----- Mapa das barras-chave (Fase 1.1) -----
        barras = d.get("barras") or {}
        if barras:
            def linha_barra(rot, chave):
                s = barras.get(chave)
                if s is None:
                    return None
                return f"{rot} {s:.0f} ({(s-spot)/spot*100:+.2f}%)"
            positivas = [x for x in (
                linha_barra("1ª+", "primeira_pos"),
                linha_barra("maior+", "maior_pos"),
                linha_barra("últ+", "ultima_pos")) if x]
            negativas = [x for x in (
                linha_barra("1ª−", "primeira_neg"),
                linha_barra("maior−", "maior_neg"),
                linha_barra("últ−", "ultima_neg")) if x]
            if positivas:
                L.append("BARRAS + ....: " + "  |  ".join(positivas)
                         + "  (ímã/estabiliza)")
            if negativas:
                L.append("BARRAS − ....: " + "  |  ".join(negativas)
                         + "  (acelera)")
        L.append("")

        # ----- SETUP DETECTADO (Fase 1.2) -----
        s = d.get("setup")
        if s and s["codigo"] != "—":
            L.append(f"<span class='destaque'>▶ SETUP {s['codigo']} — "
                     f"{s['nome'].upper()} · viés {s['vies']}</span>")
            L.append(f"  gatilho .....: {s['gatilho']}")
            L.append(f"  alvo ........: {s['alvo']}")
            L.append(f"  invalidação .: {s['invalidacao']}")
            if s.get("veto"):
                L.append(f"  <span class='neg'>⛔ VETO SPY×QQQ: "
                         f"{s['veto']}</span>")
            elif s.get("confirmacao"):
                L.append(f"  <span class='titulo'>✔ {s['confirmacao']}"
                         f"</span>")
            L.append(f"  <span class='aviso'>{s['obs']}</span>")
            L.append("")
        elif s:
            L.append(f"<span class='aviso'>▶ {s['nome']} — {s['obs']}</span>")
            L.append("")
        L.append("<span class='titulo'>CENÁRIOS (estudo, não recomendação)"
                 "</span>")
        if abs(spot - cw) / spot < 0.0015:
            L.append(f"[1] Preço COLADO no call wall ({cw:.2f}): zona de "
                     f"realização — NÃO PERSEGUIR compra aqui.")
        else:
            L.append(f"[1] SE sustentar acima do VWAP e do put wall "
                     f"({pw:.2f}) com fluxo comprador → call wall ({cw:.2f}) "
                     f"como ímã. Invalidação: perda do VWAP c/ fluxo "
                     f"vendedor.")
        if abs(spot - pw) / spot < 0.0015:
            L.append(f"[2] Preço COLADO no put wall ({pw:.2f}): freio por "
                     f"hedge — NÃO PERSEGUIR venda aqui.")
        else:
            L.append(f"[2] SE perder o VWAP com fluxo vendedor → put wall "
                     f"({pw:.2f}) vira alvo/suporte. Invalidação: retomada "
                     f"do VWAP.")
    L.append("")
    L.append("<span class='aviso'>Premissas: dealers vendidos (convenção), "
             "dados gratuitos/atrasados, fluxo estimado. Ferramenta de "
             "estudo — não é recomendação de investimento.</span>")
    return "<div class='terminal'>" + "\n".join(L) + "</div>"


def leitura_cruzada(dspy, dqqq):
    """A regra do cruzamento SPY×QQQ: os muros do SPY mandam."""
    L = ["<span class='titulo'>LEITURA CRUZADA SPY × QQQ</span>",
         "Princípio: o SPY tem o open interest mais profundo do mercado — "
         "seus muros são os mais fortes. O QQQ anda colado no índice; "
         "leitura do QQQ sem olhar o SPY é leitura pela metade.", ""]

    s_spot, s_pw, s_cw = dspy["spot"], dspy["pw"], dspy["cw"]
    q_flip, q_dom = dqqq["flip"], dqqq["dominio"]
    qqq_neg = (q_flip is not None and dqqq["spot"] < q_flip) or q_dom == "neg"

    if s_pw:
        prox_pw = (s_spot - s_pw) / s_spot * 100
        if 0 <= prox_pw < 0.50:
            extra = (": mesmo com o QQQ em regime negativo, possível REPIQUE "
                     "conjunto. Atravessar o paredão do SPY exige fluxo "
                     "vendedor persistente — na primeira visita, o freio é o "
                     "mais provável." if qqq_neg else ".")
            L.append(f"<span class='destaque'>⚑ SPY a {prox_pw:.2f}% do put "
                     f"wall ({s_pw:.0f}) — paredão forte.</span> Quedas "
                     f"tendem a FREAR aqui pela compra defensiva dos "
                     f"dealers{extra}")
        elif prox_pw < 0:
            L.append(f"<span class='neg'>⚑ SPY ABAIXO do put wall "
                     f"({s_pw:.0f}): o paredão foi atravessado — o freio "
                     f"virou teto; regime de aceleração ganha peso.</span>")
    if s_cw:
        prox_cw = (s_cw - s_spot) / s_spot * 100
        if 0 <= prox_cw < 0.50:
            L.append(f"⚑ SPY a {prox_cw:.2f}% do call wall ({s_cw:.0f}): "
                     f"altas tendem a frear aqui — cuidado ao comprar QQQ "
                     f"esticado com o SPY no teto.")

    def regime(d):
        if d["flip"] is not None:
            return "pos" if d["spot"] > d["flip"] else "neg"
        return d["dominio"]

    r_s, r_q = regime(dspy), regime(dqqq)
    if r_s and r_q:
        if r_s == r_q:
            nome = "POSITIVO" if r_s == "pos" else "NEGATIVO"
            L.append(f"Regimes ALINHADOS ({nome}) nos dois ativos → leitura "
                     f"mais confiável.")
        else:
            L.append("Regimes DIVERGENTES entre SPY e QQQ → sinal misto; em "
                     "divergência, os níveis do SPY têm precedência.")

    # ----- Veto/permissão dos setups (Fase 1.5) -----
    s_q = dqqq.get("setup") or {}
    if s_q.get("veto"):
        L.append("")
        L.append(f"<span class='neg'>⛔ VETO NO SETUP DO QQQ: "
                 f"{s_q['veto']}</span>")
    elif s_q.get("confirmacao"):
        L.append("")
        L.append(f"<span class='titulo'>✔ Setup do QQQ com {s_q['confirmacao'].lower()}</span>")

    L.append("")
    L.append("<span class='aviso'>Leitura automática por regras; premissas "
             "estatísticas podem falhar. Estudo, não recomendação.</span>")
    return "<div class='terminal'>" + "\n".join(L) + "</div>"


def cartao(rotulo, valor, sub="", classe=""):
    return (f"<div class='cartao'><div class='rotulo'>{rotulo}</div>"
            f"<div class='valor {classe}'>{valor}</div>"
            f"<div class='sub'>{sub}</div></div>")


def faixa_setup(d):
    """Banner destacado do setup detectado, para leitura de relance."""
    s = d.get("setup")
    if not s:
        return
    cod = s["codigo"]
    status = s.get("status", "")
    if cod == "—":
        cor_borda, cor_texto, fundo = "#374151", "#9ca3af", "#131a22"
    elif status == "iminente":
        # Setup se formando mas não confirmado → amarelo (aguardar)
        cor_borda, cor_texto, fundo = "#92400e", "#fbbf24", "#422006"
    elif "COMPRADOR" in s["vies"]:
        cor_borda, cor_texto, fundo = "#14532d", "#22c55e", "#052e16"
    elif "VENDEDOR" in s["vies"] and "aguardar" not in s["vies"]:
        cor_borda, cor_texto, fundo = "#7f1d1d", "#f87171", "#450a0a"
    else:
        cor_borda, cor_texto, fundo = "#92400e", "#fbbf24", "#422006"
    titulo = (f"SETUP {cod} — {s['nome']}" if cod != "—" else s["nome"])
    # Veto SPY×QQQ tem prioridade visual máxima: borda vermelha + aviso.
    veto = s.get("veto")
    conf = s.get("confirmacao")
    if veto:
        cor_borda, fundo = "#7f1d1d", "#2a0a0a"
    extra = ""
    if veto:
        extra = (f"<div style='color:#f87171;font-size:0.85rem;"
                 f"font-weight:700;margin-top:4px;'>⛔ VETO: {veto}</div>")
    elif conf:
        extra = (f"<div style='color:#22c55e;font-size:0.8rem;"
                 f"margin-top:4px;'>✔ {conf}</div>")
    st.markdown(
        f"<div style='background:{fundo};border:1px solid {cor_borda};"
        f"border-radius:10px;padding:10px 16px;margin:4px 0 10px 0;'>"
        f"<span style='color:{cor_texto};font-weight:700;font-size:0.95rem;'>"
        f"▶ {d['ticker']} · {titulo}</span>"
        f"<span style='color:#8b98a5;font-size:0.85rem;'> &nbsp;·&nbsp; "
        f"viés {s['vies']} &nbsp;·&nbsp; alvo: {s['alvo']}</span>"
        f"{extra}</div>",
        unsafe_allow_html=True)


def tabela_conversao(d):
    """
    Tabela de conversão dos níveis-chave para o futuro (Fase 1.6).
    Mostra spot, muros, flip e alvos do setup já no preço do ES/NQ,
    para o usuário operar direto na corretora.
    """
    razao = d.get("fut_razao")
    if not razao or not d.get("fut_nome"):
        return
    spot = d["spot"]
    nome = d["fut_nome"]

    def conv(v):
        return v * razao if v else None

    linhas = [("Spot", spot)]
    if d["cw"]:
        linhas.append(("Call Wall (resistência)", d["cw"]))
    if d["pw"]:
        linhas.append(("Put Wall (suporte)", d["pw"]))
    if d["flip"]:
        linhas.append(("Gamma Flip", d["flip"]))

    html = (f"<div style='background:#131a22;border:1px solid #1f2937;"
            f"border-radius:10px;padding:12px 16px;margin:6px 0;'>"
            f"<div style='color:#8b98a5;font-size:0.72rem;letter-spacing:1px;"
            f"text-transform:uppercase;margin-bottom:6px;'>"
            f"Conversão para {nome} &nbsp;·&nbsp; razão {razao:.3f} "
            f"&nbsp;·&nbsp; futuro em {d['fut_preco']:.2f}</div>"
            f"<table style='width:100%;font-size:0.85rem;color:#e6edf3;"
            f"border-collapse:collapse;'>"
            f"<tr style='color:#8b98a5;font-size:0.72rem;'>"
            f"<td>Nível</td><td style='text-align:right;'>{d['ticker']}</td>"
            f"<td style='text-align:right;'>{nome.split(' / ')[0]}</td></tr>")
    for rot, val in linhas:
        html += (f"<tr><td style='padding:2px 0;'>{rot}</td>"
                 f"<td style='text-align:right;font-variant-numeric:"
                 f"tabular-nums;'>{val:.2f}</td>"
                 f"<td style='text-align:right;font-variant-numeric:"
                 f"tabular-nums;color:#fbbf24;'>{conv(val):.2f}</td></tr>")
    html += ("</table><div style='color:#6b7280;font-size:0.72rem;"
             "margin-top:6px;'>Razão calculada ao vivo (basis = futuro ÷ "
             "ETF); varia com dividendos/juros. Estudo, não recomendação."
             "</div></div>")
    st.markdown(html, unsafe_allow_html=True)


def tema(fig, altura):
    fig.update_layout(template="plotly_dark", height=altura,
                      paper_bgcolor="#0b0f14", plot_bgcolor="#0f151c",
                      margin=dict(t=46, b=26, l=10, r=10),
                      legend=dict(orientation="h", y=1.12, x=0),
                      font=dict(size=12))
    fig.update_xaxes(gridcolor="#1f2937")
    fig.update_yaxes(gridcolor="#1f2937")
    return fig


def processar(ticker, acumular_fluxo):
    """Roda o pipeline completo de um ativo e devolve tudo num dicionário."""
    hist, prev_close, calls, puts, venc = buscar_dados(ticker)
    if hist is None or hist.empty or calls is None:
        return None
    spot = float(hist["Close"].iloc[-1])
    idx_vwap, vwap = calcular_vwap(hist)
    vwap_atual = float(vwap.iloc[-1]) if not vwap.dropna().empty else None
    por_strike, cw, pw, flip, dominio, venc_hoje, barras = calcular_gex(
        calls, puts, spot, venc, TAXA_JUROS)
    setup = detectar_setup(barras, spot, flip, dominio, cw, pw)
    fut_nome, fut_preco, fut_razao = (razao_futuro(ticker, spot)
                                      if MOSTRAR_FUTUROS else (None, None, None))
    ultimo = hist.index[-1]
    atraso = (pd.Timestamp.now(tz=ultimo.tz) - ultimo).total_seconds() / 60
    serie, strikes = estimar_fluxo(calls, puts, ticker, acumular_fluxo)
    na = num(serie[-1]["net_acum"]) if serie else 0.0
    return dict(ticker=ticker, hist=hist, prev_close=prev_close, spot=spot,
                idx_vwap=idx_vwap, vwap=vwap, vwap_atual=vwap_atual,
                por_strike=por_strike, cw=cw, pw=pw, flip=flip,
                dominio=dominio, venc=venc, venc_hoje=venc_hoje,
                barras=barras, setup=setup, ultimo=ultimo, atraso=atraso,
                fut_nome=fut_nome, fut_preco=fut_preco, fut_razao=fut_razao,
                serie=serie, strikes=strikes, net_acum=na,
                bull_acum=num(serie[-1]["bull_acum"]) if serie else 0.0,
                bear_acum=num(serie[-1]["bear_acum"]) if serie else 0.0)


def grafico_gex(d, altura=340, horizontal=False):
    faixa = d["por_strike"][(d["por_strike"]["strike"] > d["spot"] * 0.965) &
                            (d["por_strike"]["strike"] < d["spot"] * 1.035)]
    cores = ["#22c55e" if g >= 0 else "#3b82f6" for g in faixa["gex"]]

    # ---------- MODO CELULAR (Fase 2.2): barras HORIZONTAIS ----------
    # Strikes no eixo vertical: em tela estreita, a leitura fica muito
    # mais natural (como um "mapa de profundidade" de cima para baixo).
    if horizontal:
        fig = go.Figure()
        fig.add_bar(y=faixa["strike"], x=faixa["gex"], orientation="h",
                    marker_color=cores)
        fig.add_hline(y=d["spot"], line_dash="dot", line_color="#e6edf3",
                      annotation_text=f"Spot {d['spot']:.2f}",
                      annotation_position="top right",
                      annotation_font_color="#e6edf3")
        if d["cw"]:
            fig.add_hline(y=d["cw"], line_color="#22c55e",
                          annotation_text="Call Wall",
                          annotation_position="top left",
                          annotation_font_color="#22c55e")
        if d["pw"]:
            fig.add_hline(y=d["pw"], line_color="#ef4444",
                          annotation_text="Put Wall",
                          annotation_position="bottom left",
                          annotation_font_color="#ef4444")
        if d["flip"]:
            fig.add_hline(y=d["flip"], line_dash="dash",
                          line_color="#eab308", annotation_text="Flip",
                          annotation_position="left",
                          annotation_font_color="#eab308")
        aviso_0dte = "  ⚠ VENCE HOJE" if d.get("venc_hoje") else ""
        fig.update_layout(title=f"{d['ticker']} — Gamma (venc. "
                                f"{d['venc']}){aviso_0dte}")
        fig.update_xaxes(tickformat="~s")
        return tema(fig, altura)

    # ---------- MODO DESKTOP: barras verticais (original) ----------
    fig = go.Figure()
    fig.add_bar(x=faixa["strike"], y=faixa["gex"],
                marker_color=cores)
    fig.add_vline(x=d["spot"], line_dash="dot", line_color="#e6edf3",
                  annotation_text=f"Spot {d['spot']:.2f}",
                  annotation_position="top",
                  annotation_font_color="#e6edf3")
    if d["cw"]:
        fig.add_vline(x=d["cw"], line_color="#22c55e",
                      annotation_text="Call Wall",
                      annotation_position="bottom left",
                      annotation_font_color="#22c55e")
    if d["pw"]:
        fig.add_vline(x=d["pw"], line_color="#ef4444",
                      annotation_text="Put Wall",
                      annotation_position="bottom right",
                      annotation_font_color="#ef4444")
    if d["flip"]:
        fig.add_vline(x=d["flip"], line_dash="dash", line_color="#eab308",
                      annotation_text="Flip",
                      annotation_position="bottom",
                      annotation_font_color="#eab308")

    # -------- Marcação das 6 barras-chave (Fase 1.1) --------
    # Rótulos curtos no topo (positivas) ou base (negativas) da barra.
    # Nomes dos muros ficam na BASE do gráfico e as barras-chave no TOPO,
    # em planos separados, para não se sobreporem.
    barras = d.get("barras") or {}
    rotulos = {
        "primeira_pos": ("1+", "#4ade80"),
        "maior_pos":    ("MÁX+", "#22c55e"),
        "ultima_pos":   ("ú+", "#4ade80"),
        "primeira_neg": ("1−", "#60a5fa"),
        "maior_neg":    ("MÁX−", "#3b82f6"),
        "ultima_neg":   ("ú−", "#60a5fa"),
    }
    ps = d["por_strike"]
    for chave, (txt, cor) in rotulos.items():
        strike = barras.get(chave)
        if strike is None:
            continue
        linha = ps[ps["strike"] == strike]
        if linha.empty:
            continue
        valor = float(linha["gex"].iloc[0])
        acima = valor >= 0
        fig.add_annotation(
            x=strike, y=valor,
            text=txt, showarrow=False,
            yshift=16 if acima else -16,
            font=dict(size=11, color=cor, family="Consolas, monospace"),
            bgcolor="rgba(11,15,20,0.7)",
        )

    aviso_0dte = "  ⚠ VENCE HOJE (0DTE)" if d.get("venc_hoje") else ""
    fig.update_layout(title=f"{d['ticker']} — Gamma por Strike "
                            f"(venc. {d['venc']}){aviso_0dte}")
    fig.update_yaxes(tickformat="~s")
    return tema(fig, altura)


def cartoes_do_ativo(d, mobile=False):
    va = d["vwap_atual"]
    if va:
        difp = (d["spot"] - va) / va * 100
        if abs(difp) < 0.05:
            vcls, vsub = "amarelo", "colado — equilíbrio"
        elif difp > 0:
            vcls, vsub = "verde", f"{difp:+.2f}% acima"
        else:
            vcls, vsub = "vermelho", f"{difp:+.2f}% abaixo"
    else:
        vcls, vsub = "", ""
    ncls = ("verde" if d["net_acum"] > 0 else
            "vermelho" if d["net_acum"] < 0 else "")
    if d["flip"]:
        flip_txt = f"{d['flip']:.0f}"
        flip_sub = ("regime positivo" if d["spot"] > d["flip"]
                    else "regime negativo")
    else:
        flip_txt = "banda −" if d["dominio"] == "neg" else (
            "banda +" if d["dominio"] == "pos" else "—")
        flip_sub = ("negativo dominante" if d["dominio"] == "neg" else
                    "positivo dominante" if d["dominio"] == "pos" else "")

    itens = [
        ("Spot", f"{d['spot']:.2f}", "", ""),
        ("VWAP", f"{va:.2f}" if va else "—", vsub, vcls),
        ("Call Wall", f"{d['cw']:.0f}" if d["cw"] else "—",
         f"{(d['cw']-d['spot'])/d['spot']*100:+.2f}%" if d["cw"] else "",
         "verde"),
        ("Put Wall", f"{d['pw']:.0f}" if d["pw"] else "—",
         f"{(d['pw']-d['spot'])/d['spot']*100:+.2f}%" if d["pw"] else "",
         "vermelho"),
        ("Gamma Flip", flip_txt, flip_sub, ""),
        ("Net Premium", fmt_usd(d["net_acum"]), "sessão", ncls),
    ]
    # Celular: 2 linhas de 3 cartões (cabem na tela); desktop: 1 linha de 6.
    grupos = [itens[:3], itens[3:]] if mobile else [itens]
    for grupo in grupos:
        cols = st.columns(len(grupo))
        for c, (rot, val, sub, cls) in zip(cols, grupo):
            c.markdown(cartao(rot, val, sub, cls), unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# EXECUÇÃO PRINCIPAL
# ----------------------------------------------------------------------------
# Carrega o SPY primeiro só para descobrir o relógio de NY (fuso da bolsa):
d_probe = buscar_dados("SPY")[0]
if d_probe is None or d_probe.empty:
    st_autorefresh(interval=60_000, key="auto")
    st.warning("Sem dados no momento (falha do yfinance). "
               "Nova tentativa em 60 s.")
    st.stop()

TZ_NY = d_probe.index[-1].tz
agora_ny = pd.Timestamp.now(tz=TZ_NY)
try:
    agora_br = pd.Timestamp.now(tz="America/Sao_Paulo")
except Exception:
    agora_br = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=3)

atraso_probe = (agora_ny - d_probe.index[-1]).total_seconds() / 60
t_ny, dia_util = agora_ny.time(), agora_ny.weekday() < 5
if dia_util and dtime(9, 30) <= t_ny < dtime(16, 0) and atraso_probe < 20:
    ESTADO = "aberto"
elif dia_util and dtime(4, 0) <= t_ny < dtime(9, 30):
    ESTADO = "pre"
else:
    ESTADO = "fechado"

# Janela quente (abertura chegando ou recém-aberta): 30 s; senão 60 s.
# Mais rápido que 30 s o Yahoo bloqueia — e não adianta: o dado é atrasado.
janela_quente = dia_util and (dtime(9, 0) <= t_ny < dtime(9, 45))
st_autorefresh(interval=30_000 if janela_quente else 60_000, key="auto")

selo = {"aberto": "<span class='selo selo-aberto'>● MERCADO ABERTO</span>",
        "pre": "<span class='selo selo-pre'>● PRÉ-MERCADO</span>",
        "fechado": "<span class='selo selo-fechado'>● MERCADO FECHADO</span>"
        }[ESTADO]

# ----------------------------------------------------------------------------
# MENTOR DE DISCIPLINA — regras escritas pelo próprio operador.
# Uma por dia (rotação) + botão para ver todas. Trade é técnica + emocional.
# ----------------------------------------------------------------------------

MENSAGENS_DISCIPLINA = [
    "Se chegar no seu limite de loss diário, DESLIGA. Não tente reverter: "
    "você sai da estratégia e vira jogador de sorte e azar. Não seja "
    "infantil — isso aqui é uma empresa, leve a sério. Amanhã tem mais.",
    "Não seja ganancioso. Constância é o segredo. Você sempre perdeu por "
    "ganância.",
    "Não adianta operar contra o mercado.",
    "Mover o stop para baixo ou para cima porque 'acha que o mercado vai "
    "recuperar' é a fórmula exata para perder todas as suas contas. Não "
    "seja idiota!",
    "Aceite a dor da perda. Desliga o PC e aceita a dor. Vai malhar, fazer "
    "outra coisa. Não tente recuperar.",
    "Não opere alavancado — isso quebra a sua conta em um ou dois trades. "
    "Faça regras para aguentar perder 15 dias seguidos sem perder a conta. "
    "Sem conta, amanhã você está fudido.",
    "Sacar faz bem para a alma. De preferência, saque no caixa eletrônico e "
    "veja a materialização do que conquistou. Compre roupas novas, vá a um "
    "bom restaurante — e lembre: você venceu porque NÃO saiu da estratégia "
    "e NÃO foi ganancioso.",
    "Perder faz parte. Você é um pequeno trader num mercado que movimenta "
    "trilhões de dólares. Deixa de ser infantil.",
    "Você não vai ficar rico da noite para o dia no trade. Talvez nunca "
    "fique — mas pode viver confortável.",
    "Pare de ficar ansioso, clicando igual um maluco. Overtrading é excesso "
    "de negociação sem fundamento: gera custo alto e MUITO prejuízo. Se "
    "quiser ser idiota, separe uma conta para isso — não alimente essa "
    "sensação na conta séria.",
    "Trade não é pirâmide, não é bet, não é cassino. É técnica pura + "
    "emocional.",
    "Perdeu? Não ponha a culpa na família nem na estratégia.",
    "90% das pessoas perdem: não têm disciplina, não têm estratégia e ficam "
    "se sabotando.",
    "Opere pequeno SEMPRE. Não perca sua fonte de renda. O segredo é "
    "múltiplas contas.",
    "No trade o dinheiro muda de mão: sai de alguém para você. Fique "
    "focado, sem ganância, que o dinheiro do operador que está na Ásia vem "
    "para você. Seja mais esperto que eles!",
]


def mentor_disciplina():
    """Banner com a regra de disciplina do dia + expander com todas."""
    idx = pd.Timestamp.now().dayofyear % len(MENSAGENS_DISCIPLINA)
    msg = MENSAGENS_DISCIPLINA[idx]
    st.markdown(
        f"<div style='background:#1a1406;border-left:3px solid #fbbf24;"
        f"border-radius:6px;padding:8px 14px;margin:2px 0 8px 0;"
        f"color:#e6edf3;font-size:0.85rem;'>"
        f"<span style='color:#fbbf24;font-weight:700;'>🧭 DISCIPLINA · </span>"
        f"{msg}</div>", unsafe_allow_html=True)
    with st.expander("Ver todas as regras de disciplina"):
        for m in MENSAGENS_DISCIPLINA:
            st.markdown(f"- {m}")


# ---- Taxa de juros (Fase 1.7): automática via ^IRX, manual de reserva ----
R_AUTO = taxa_juros_automatica() if USAR_R_AUTO else None
TAXA_JUROS = R_AUTO if R_AUTO else TAXA_MANUAL
origem_r = "auto ^IRX" if R_AUTO else "manual"

st.markdown(f"## PrumoQuant — Fluxo de Opções &nbsp; {selo}",
            unsafe_allow_html=True)
st.caption(f"NY {agora_ny:%H:%M} · Brasília {agora_br:%H:%M} · abertura "
           f"9:30 NY · atualização a cada "
           f"{'30 s (janela quente)' if janela_quente else '60 s'} · dados "
           f"atrasados ~15 min (yfinance) · r {TAXA_JUROS*100:.2f}% "
           f"({origem_r})")
mentor_disciplina()

tickers = ["SPY", "QQQ"] if MODO_VISAO.startswith("SPY") else [TICKER_UNICO]
dados = {}
for tk_ in tickers:
    d = processar(tk_, acumular_fluxo=(ESTADO == "aberto"))
    if d:
        dados[tk_] = d

if not dados:
    st.warning("Sem dados de opções no momento. Nova tentativa automática.")
    st.stop()

# ---- VETO SPY×QQQ (Fase 1.5): SPY dá a permissão, QQQ é o gatilho ----
if "SPY" in dados and "QQQ" in dados:
    aplicar_veto_spy_qqq(dados["SPY"], dados["QQQ"])

janela_abertura = (ESTADO == "pre" or
                   (ESTADO == "aberto" and t_ny < dtime(9, 45)))

# ---------------- MODO UM ATIVO ----------------
if len(dados) == 1:
    d = list(dados.values())[0]
    t = d["ticker"]
    cartoes_do_ativo(d)
    faixa_setup(d)
    tabela_conversao(d)
    st.markdown("")

    if janela_abertura:
        sc, gap = score_abertura(d["spot"], d["prev_close"], d["flip"],
                                 d["cw"], d["pw"], d["dominio"], d["hist"])
        st.markdown(playbook_abertura(t, d["spot"], d["prev_close"], d["cw"],
                                      d["pw"], d["flip"], d["dominio"], sc,
                                      gap, agora_ny), unsafe_allow_html=True)

    if MODO_CELULAR:
        # ---- Layout celular: tudo empilhado, gamma na horizontal ----
        st.plotly_chart(grafico_gex(d, 560, horizontal=True),
                        use_container_width=True)
        if ESTADO != "aberto":
            st.info("Fluxo pausado (fora do pregão). Opções não negociam "
                    "no pré-mercado.")
        f4 = go.Figure()
        f4.add_scatter(x=d["hist"].index, y=d["hist"]["Close"], name="Preço",
                       line=dict(color="#eab308", width=1.6))
        f4.add_scatter(x=d["idx_vwap"], y=d["vwap"], name="VWAP",
                       line=dict(color="#a78bfa", width=1.6))
        f4.update_layout(title="Intradiário (com pré/pós): preço x VWAP")
        st.plotly_chart(tema(f4, 260), use_container_width=True)
        st.caption("Modo celular: gráficos completos de fluxo disponíveis "
                   "no desktop.")
        ce = cd = None
    else:
        ce, cd = st.columns([3, 2])
    if ce is not None:
      with ce:
        st.plotly_chart(grafico_gex(d, 380), use_container_width=True)
        if len(d["serie"]) >= 2 and (d["bull_acum"] + d["bear_acum"]) > 0:
            df_f = pd.DataFrame(d["serie"])
            f2 = go.Figure()
            f2.add_scatter(x=df_f["hora"], y=df_f["bull_acum"],
                           fill="tozeroy", name="Comprador (acum.)",
                           line_color="#22c55e")
            f2.add_scatter(x=df_f["hora"], y=df_f["bear_acum"],
                           fill="tozeroy", name="Vendedor (acum.)",
                           line_color="#ef4444")
            f2.update_layout(title="Net Premium estimado — sessão")
            f2.update_yaxes(tickprefix="$", tickformat="~s")
            st.plotly_chart(tema(f2, 300), use_container_width=True)
        elif ESTADO == "aberto":
            st.info("Fluxo em construção — ~2 ciclos após a abertura.")
        else:
            st.info("Fluxo pausado (fora do pregão). Opções não negociam "
                    "no pré-mercado.")
    if cd is not None:
      with cd:
        total = d["bull_acum"] + d["bear_acum"]
        if total > 0:
            rot = "Comprador" if d["net_acum"] >= 0 else "Vendedor"
            cor = "#22c55e" if d["net_acum"] >= 0 else "#ef4444"
            f3 = go.Figure(go.Pie(labels=["Comprador", "Vendedor"],
                                  values=[d["bull_acum"], d["bear_acum"]],
                                  hole=0.68,
                                  marker_colors=["#22c55e", "#ef4444"],
                                  textinfo="percent"))
            f3.update_layout(title="Balanço do fluxo",
                             annotations=[dict(
                                 text=f"<b>{fmt_usd(d['net_acum'])}</b><br>"
                                      f"{rot}",
                                 showarrow=False,
                                 font=dict(size=16, color=cor))],
                             showlegend=False)
            st.plotly_chart(tema(f3, 290), use_container_width=True)
        if d["strikes"]:
            df_s = pd.DataFrame([{"strike": k, "net": v}
                                 for k, v in d["strikes"].items()])
            top = (df_s.reindex(df_s["net"].abs()
                                .sort_values(ascending=False).index)
                   .head(12).sort_values("strike"))
            f5 = go.Figure(go.Bar(y=[f"{s:.0f}" for s in top["strike"]],
                                  x=top["net"], orientation="h",
                                  marker_color=["#22c55e" if v >= 0 else
                                                "#ef4444"
                                                for v in top["net"]]))
            f5.update_layout(title="Fluxo por strike — sessão")
            f5.update_xaxes(tickprefix="$", tickformat="~s")
            st.plotly_chart(tema(f5, 300), use_container_width=True)
        f4 = go.Figure()
        f4.add_scatter(x=d["hist"].index, y=d["hist"]["Close"], name="Preço",
                       line=dict(color="#eab308", width=1.6))
        f4.add_scatter(x=d["idx_vwap"], y=d["vwap"], name="VWAP",
                       line=dict(color="#a78bfa", width=1.6))
        f4.update_layout(title="Intradiário (com pré/pós): preço x VWAP")
        st.plotly_chart(tema(f4, 270), use_container_width=True)

    st.markdown(gerar_playbook(
        t, dict(d, estado=ESTADO,
                data_sessao=d["ultimo"].strftime("%d/%m/%Y")), agora_br),
        unsafe_allow_html=True)

# ---------------- MODO SPY + QQQ LADO A LADO ----------------
else:
    if MODO_CELULAR:
        # ---- Celular: um ativo abaixo do outro, gamma horizontal ----
        for tk_ in ("SPY", "QQQ"):
            d = dados.get(tk_)
            if not d:
                st.warning(f"Sem dados de {tk_} neste ciclo.")
                continue
            st.markdown(f"### {tk_}")
            cartoes_do_ativo(d, mobile=True)
            faixa_setup(d)
            tabela_conversao(d)
            if janela_abertura:
                sc, gap = score_abertura(d["spot"], d["prev_close"],
                                         d["flip"], d["cw"], d["pw"],
                                         d["dominio"], d["hist"])
                st.markdown(playbook_abertura(tk_, d["spot"],
                                              d["prev_close"], d["cw"],
                                              d["pw"], d["flip"],
                                              d["dominio"], sc, gap,
                                              agora_ny),
                            unsafe_allow_html=True)
            st.plotly_chart(grafico_gex(d, 520, horizontal=True),
                            use_container_width=True)
    else:
      col_spy, col_qqq = st.columns(2)
      for col, tk_ in ((col_spy, "SPY"), (col_qqq, "QQQ")):
        d = dados.get(tk_)
        if not d:
            col.warning(f"Sem dados de {tk_} neste ciclo.")
            continue
        with col:
            st.markdown(f"### {tk_}")
            cartoes_do_ativo(d)
            faixa_setup(d)
            tabela_conversao(d)
            if janela_abertura:
                sc, gap = score_abertura(d["spot"], d["prev_close"],
                                         d["flip"], d["cw"], d["pw"],
                                         d["dominio"], d["hist"])
                st.markdown(playbook_abertura(tk_, d["spot"],
                                              d["prev_close"], d["cw"],
                                              d["pw"], d["flip"],
                                              d["dominio"], sc, gap,
                                              agora_ny),
                            unsafe_allow_html=True)
            st.plotly_chart(grafico_gex(d, 320), use_container_width=True)
            f4 = go.Figure()
            f4.add_scatter(x=d["hist"].index, y=d["hist"]["Close"],
                           name="Preço",
                           line=dict(color="#eab308", width=1.5))
            f4.add_scatter(x=d["idx_vwap"], y=d["vwap"], name="VWAP",
                           line=dict(color="#a78bfa", width=1.5))
            f4.update_layout(title="Preço x VWAP")
            st.plotly_chart(tema(f4, 240), use_container_width=True)

    if "SPY" in dados and "QQQ" in dados:
        st.markdown(leitura_cruzada(dados["SPY"], dados["QQQ"]),
                    unsafe_allow_html=True)
        for tk_ in ("SPY", "QQQ"):
            d = dados[tk_]
            st.markdown(gerar_playbook(
                tk_, dict(d, estado=ESTADO,
                          data_sessao=d["ultimo"].strftime("%d/%m/%Y")),
                agora_br), unsafe_allow_html=True)
