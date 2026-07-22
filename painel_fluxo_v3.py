# =============================================================================
# PRUMOQUANT — ABERTURA NQ + ES  ·  v1.0  ·  arquivo unico
# -----------------------------------------------------------------------------
# Ferramenta de ESTUDO. Nao e recomendacao de investimento. SOMENTE LEITURA.
#
# CONTRATO DE HONESTIDADE (lema: "Quero estrategia, nao sorte"):
#   - Antes de 9h30 NY o fluxo de opcoes NAO EXISTE. Logo, antes da abertura o
#     painel mostra apenas CONTEXTO MACRO, rotulado como "PALPITE MACRO -
#     fluxo ainda nao abriu". NUNCA emite seta de direcao pre-abertura.
#   - Direcao com FLUXO REAL so aparece a partir de 9h30:15 NY (fluxo nasceu).
#   - Fora do pregao de acoes, net_dir = None (nunca zero). Sem fantasma.
#
# STACK: Tradier Pro (fluxo de opcoes SPY/QQQ) + yfinance (preco NQ/ES, macro).
# PERSISTENCIA: nenhuma na v1 (session_state apenas). Enxuto.
#
# PONTES:  QQQ (fluxo) -> NQ (execucao)  |  SPY (fluxo) -> ES (execucao)
# STOPS FIXOS: NQ 50 pts  ·  ES 7 pts   (valores Striking Bell)
# =============================================================================

import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime, date, time as dtime
import pytz

try:
    import yfinance as yf
    YF_OK = True
except Exception:
    YF_OK = False

# -----------------------------------------------------------------------------
# CONFIG GLOBAL
# -----------------------------------------------------------------------------
NY = pytz.timezone("America/New_York")

# Janela de captura (two-shot cirurgico, herdado da v5.6)
T1_PRE = dtime(9, 29, 45)     # snapshot pre-open
T2_FREEZE = dtime(9, 30, 15)  # freeze oficial com fluxo real

STOP_NQ = 50   # pts
STOP_ES = 7    # pts

# Filtros de qualidade (ajustaveis na sidebar)
DEFAULT_MAX_SPREAD_PCT = 15.0
DEFAULT_MIN_VOL = 5

TRADIER_BASE = "https://api.tradier.com/v1"


# -----------------------------------------------------------------------------
# RELOGIO / JANELA OPERACIONAL
# -----------------------------------------------------------------------------
def agora_ny():
    return datetime.now(NY)


def pregao_acoes_aberto(dt=None):
    """True somente seg-sex 9:30-16:00 NY (herdado da v5.5, mata NET fantasma)."""
    if dt is None:
        dt = agora_ny()
    if dt.weekday() >= 5:  # sab/dom
        return False
    t = dt.time()
    return dtime(9, 30) <= t <= dtime(16, 0)


def fase_do_dia(dt=None):
    """
    Retorna uma das fases que comandam TODA a UI:
      'aguardando' - tudo fechado (fim de semana ou fora do horario)
      'pre'        - pre-abertura mesmo dia util, antes de 9:29:45  -> CONTEXTO
      'captura'    - 9:29:45 a 9:30:15                              -> congelando
      'ativo'      - 9:30:15 a 16:00                                -> FLUXO REAL
      'pos'        - depois de 16:00                                -> encerrado
    """
    if dt is None:
        dt = agora_ny()
    if dt.weekday() >= 5:
        return "aguardando"
    t = dt.time()
    if t < T1_PRE:
        return "pre"
    if T1_PRE <= t < T2_FREEZE:
        return "captura"
    if T2_FREEZE <= t <= dtime(16, 0):
        return "ativo"
    return "pos"


# -----------------------------------------------------------------------------
# TRADIER — FLUXO DE OPCOES (SPY / QQQ)
# -----------------------------------------------------------------------------
def _tradier_headers():
    token = st.secrets.get("TRADIER_TOKEN", "")
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


@st.cache_data(ttl=12)  # cache 12s acompanha refresh de 15s do miolo
def tradier_expirations(ticker):
    try:
        r = requests.get(
            f"{TRADIER_BASE}/markets/options/expirations",
            params={"symbol": ticker, "includeAllRoots": "true"},
            headers=_tradier_headers(), timeout=10,
        )
        r.raise_for_status()
        data = r.json().get("expirations", {}) or {}
        dates = data.get("date", [])
        if isinstance(dates, str):
            dates = [dates]
        return sorted(dates)
    except Exception:
        return []


@st.cache_data(ttl=12)
def tradier_chain(ticker, expiration):
    try:
        r = requests.get(
            f"{TRADIER_BASE}/markets/options/chains",
            params={"symbol": ticker, "expiration": expiration, "greeks": "true"},
            headers=_tradier_headers(), timeout=10,
        )
        r.raise_for_status()
        opts = r.json().get("options", {}) or {}
        lst = opts.get("option", [])
        if isinstance(lst, dict):
            lst = [lst]
        return lst
    except Exception:
        return []


@st.cache_data(ttl=12)
def preco_spot(ticker):
    """Ultimo preco do ETF via Tradier quote."""
    try:
        r = requests.get(
            f"{TRADIER_BASE}/markets/quotes",
            params={"symbols": ticker}, headers=_tradier_headers(), timeout=10,
        )
        r.raise_for_status()
        q = r.json().get("quotes", {}).get("quote", {})
        if isinstance(q, list):
            q = q[0]
        return float(q.get("last") or q.get("close") or 0.0)
    except Exception:
        return 0.0


# -----------------------------------------------------------------------------
# NET OPERACIONAL — aproximacao direcional do Volume Imbalance
# -----------------------------------------------------------------------------
# LIMITE ESTRUTURAL HONESTO: a Tradier so da volume ACUMULADO por strike (sem o
# lado agressor de cada trade). Isto e uma APROXIMACAO, calibravel pelo divisor,
# NUNCA uma replica do Imbalance da Quantico. So calculado com pregao aberto.
# -----------------------------------------------------------------------------
def net_operacional(ticker, spot, divisor=1.0, max_spread_pct=DEFAULT_MAX_SPREAD_PCT,
                    min_vol=DEFAULT_MIN_VOL):
    """
    NET op = so vencimento mais proximo (0DTE) + janela 0.90-1.10*S + divisor.
    Retorna None se pregao fechado (protege contra fantasma).
    Sinal: >0 = compradora (calls compradas / puts vendidas); <0 = vendedora.
    """
    if not pregao_acoes_aberto():
        return None
    if spot <= 0:
        return None

    exps = tradier_expirations(ticker)
    if not exps:
        return None
    exp = exps[0]  # 0DTE / mais proximo
    chain = tradier_chain(ticker, exp)
    if not chain:
        return None

    lo, hi = 0.90 * spot, 1.10 * spot
    net = 0.0
    for o in chain:
        try:
            strike = float(o.get("strike", 0))
            if not (lo <= strike <= hi):
                continue
            vol = float(o.get("volume") or 0)
            if vol < min_vol:
                continue
            bid = float(o.get("bid") or 0)
            ask = float(o.get("ask") or 0)
            mid = (bid + ask) / 2.0 if (bid + ask) > 0 else 0
            if mid <= 0:
                continue
            spread_pct = (ask - bid) / mid * 100 if mid > 0 else 999
            if spread_pct > max_spread_pct:
                continue
            last = float(o.get("last") or mid)
            notional = vol * last * 100.0
            otype = (o.get("option_type") or "").lower()
            # proxy direcional: call negociada acima do mid = compra agressora (+)
            #                   put  negociada acima do mid = compra agressora (-)
            press = 1.0 if last >= mid else -1.0
            if otype == "call":
                net += press * notional
            elif otype == "put":
                net += -press * notional
        except Exception:
            continue

    return net / divisor if divisor else net


# -----------------------------------------------------------------------------
# TRES INDICADORES (por-strike, janela ATM) — placar de votos
# -----------------------------------------------------------------------------
def tres_indicadores(ticker, spot, max_spread_pct, min_vol):
    """
    Retorna dict com voto de cada indicador em {+1, 0, -1}:
      delta_hedging, fluxo_inst, time_pressure
    Aproximacoes honestas sobre volume acumulado da Tradier.
    Retorna None se pregao fechado.
    """
    if not pregao_acoes_aberto() or spot <= 0:
        return None
    exps = tradier_expirations(ticker)
    if not exps:
        return None
    chain = tradier_chain(ticker, exps[0])
    if not chain:
        return None

    lo, hi = 0.95 * spot, 1.05 * spot
    gex = 0.0          # delta-hedging proxy (gamma exposure sinal)
    fluxo = 0.0        # fluxo institucional (notional call vs put)
    theta_press = 0.0  # time pressure proxy

    for o in chain:
        try:
            strike = float(o.get("strike", 0))
            if not (lo <= strike <= hi):
                continue
            vol = float(o.get("volume") or 0)
            if vol < min_vol:
                continue
            oi = float(o.get("open_interest") or 0)
            g = o.get("greeks") or {}
            gamma = float(g.get("gamma") or 0)
            theta = float(g.get("theta") or 0)
            last = float(o.get("last") or 0)
            otype = (o.get("option_type") or "").lower()

            # Delta-Hedging: GEX = gamma*OI*100*S^2, calls + / puts -
            g_contrib = gamma * oi * 100.0 * (spot ** 2)
            gex += g_contrib if otype == "call" else -g_contrib

            # Fluxo institucional (notional): calls compradas +, puts compradas -
            notional = vol * last * 100.0
            fluxo += notional if otype == "call" else -notional

            # Time Pressure: theta decay force (magnitude via theta*vol)
            theta_press += theta * vol * (1 if otype == "call" else -1)
        except Exception:
            continue

    def voto(x, dead=0.0):
        if x > dead:
            return 1
        if x < -dead:
            return -1
        return 0

    return {
        "delta_hedging": voto(gex),
        "fluxo_inst": voto(fluxo),
        "time_pressure": voto(theta_press),
    }


def placar_4_votos(indic, net):
    """
    Combina 3 indicadores + NET operacional em placar de 4 votos.
    Retorna (direcao_str, votos_compra, votos_venda, detalhe_dict).
    """
    if indic is None:
        return ("Fluxo fechado", 0, 0, {})
    votos = dict(indic)
    votos["net_op"] = 1 if (net or 0) > 0 else (-1 if (net or 0) < 0 else 0)

    comp = sum(1 for v in votos.values() if v > 0)
    vend = sum(1 for v in votos.values() if v < 0)

    if comp >= 3:
        direcao = "COMPRADO"
    elif vend >= 3:
        direcao = "VENDIDO"
    else:
        direcao = "LATERAL"
    return (direcao, comp, vend, votos)


def intensidade(comp, vend):
    forte = max(comp, vend)
    if forte >= 4:
        return "Forte"
    if forte == 3:
        return "Moderada"
    return "Lateral"


# -----------------------------------------------------------------------------
# MACRO (yfinance) — CONTEXTO, nunca gatilho
# -----------------------------------------------------------------------------
@st.cache_data(ttl=60)
def macro_contexto():
    """VIX, DXY, US10Y + futuros NQ/ES. Retorna dict de % e niveis. Contexto."""
    out = {}
    if not YF_OK:
        return out
    tickers = {"VIX": "^VIX", "DXY": "DX-Y.NYB", "US10Y": "^TNX",
               "NQ": "NQ=F", "ES": "ES=F"}
    for nome, tk in tickers.items():
        try:
            h = yf.Ticker(tk).history(period="2d")
            if len(h) >= 2:
                prev = float(h["Close"].iloc[-2])
                cur = float(h["Close"].iloc[-1])
                pct = (cur - prev) / prev * 100 if prev else 0.0
                out[nome] = {"valor": cur, "pct": pct}
            elif len(h) == 1:
                out[nome] = {"valor": float(h["Close"].iloc[-1]), "pct": 0.0}
        except Exception:
            continue
    return out


def vies_macro(macro):
    """
    Palpite de regime risk-on/risk-off a partir do macro.
    ROTULADO SEMPRE como palpite. NUNCA e sinal de fluxo.
    Score negativo = risk-off (viés vendedor); positivo = risk-on.
    """
    if not macro:
        return ("SEM DADO", 0.0)
    score = 0.0
    # VIX subindo = risk-off (peso negativo)
    if "VIX" in macro:
        score -= macro["VIX"]["pct"] * 0.5
    # DXY subindo = risk-off para acoes (peso negativo leve)
    if "DXY" in macro:
        score -= macro["DXY"]["pct"] * 0.3
    # Futuros NQ/ES: sobem = risk-on
    for k in ("NQ", "ES"):
        if k in macro:
            score += macro[k]["pct"] * 1.0
    if score > 0.3:
        rotulo = "risk-on (palpite altista)"
    elif score < -0.3:
        rotulo = "risk-off (palpite baixista)"
    else:
        rotulo = "neutro / indefinido"
    return (rotulo, score)


# -----------------------------------------------------------------------------
# UI — CARD DE UM ATIVO (NQ ou ES)
# -----------------------------------------------------------------------------
def render_card(nome_fut, ticker_fluxo, stop_pts, fase, macro, cfg):
    st.subheader(f"{nome_fut}  ·  fluxo via {ticker_fluxo}")

    fut_key = "NQ" if nome_fut == "NQ" else "ES"
    fut = macro.get(fut_key, {})
    if fut:
        st.metric(f"{nome_fut} (futuro agora)", f"{fut['valor']:.2f}",
                  f"{fut['pct']:+.2f}%")

    # ----- FASE PRE / AGUARDANDO: so contexto, sem seta -----
    if fase in ("pre", "aguardando", "captura"):
        rotulo, score = vies_macro(macro)
        st.warning(
            "PALPITE MACRO — fluxo ainda nao abriu. "
            "Isto NAO e sinal de fluxo, e contexto de regime."
        )
        st.write(f"**Viés macro:** {rotulo}  ·  score {score:+.2f}")
        if fase == "captura":
            st.info("Congelando snapshot do fluxo (9h29:45 → 9h30:15)…")
        st.caption("Sem direção. O fluxo vota a partir de 9h30:15 NY.")
        return

    if fase == "pos":
        st.info("Pregao encerrado (apos 16h NY). Sem leitura de fluxo ativa.")
        return

    # ----- FASE ATIVO: fluxo real -----
    spot = preco_spot(ticker_fluxo)
    if spot <= 0:
        st.error(f"Sem cotacao de {ticker_fluxo} (warm-up ou credencial). "
                 "Painel segue sem quebrar.")
        return

    net = net_operacional(ticker_fluxo, spot, divisor=cfg["divisor"],
                          max_spread_pct=cfg["max_spread"], min_vol=cfg["min_vol"])
    indic = tres_indicadores(ticker_fluxo, spot, cfg["max_spread"], cfg["min_vol"])
    direcao, comp, vend, votos = placar_4_votos(indic, net)
    inten = intensidade(comp, vend)

    # PLANO estilo Hound, mas com fluxo real
    cor = {"COMPRADO": "🟢", "VENDIDO": "🔴", "LATERAL": "🟡"}.get(direcao, "⚪")
    st.markdown(f"### {cor} Direção: **{direcao}**  ·  Intensidade: **{inten}**")
    st.write(f"**Placar 4 votos:** {comp} compra × {vend} venda")

    if votos:
        vt = pd.DataFrame([
            {"Indicador": "Delta-Hedging", "Voto": votos.get("delta_hedging", 0)},
            {"Indicador": "Fluxo Institucional", "Voto": votos.get("fluxo_inst", 0)},
            {"Indicador": "Time Pressure", "Voto": votos.get("time_pressure", 0)},
            {"Indicador": "NET operacional", "Voto": votos.get("net_op", 0)},
        ])
        st.dataframe(vt, hide_index=True, use_container_width=True)

    if net is not None:
        st.write(f"**NET operacional:** {net:+,.0f}  (aproximacao, calibravel)")
    else:
        st.write("**NET operacional:** — (pregao fechado)")

    # Gatilho: 3+/4 = entrar; senao aguardar
    if comp >= 3:
        st.success(f"GATILHO: comprar {nome_fut} na abertura  ·  Stop fixo {stop_pts} pts")
    elif vend >= 3:
        st.success(f"GATILHO: vender {nome_fut} na abertura  ·  Stop fixo {stop_pts} pts")
    else:
        st.warning("Sem gatilho (placar < 3/4). Ficar de fora, aguardar definicao.")

    st.caption(f"Stop fixo {nome_fut}: {stop_pts} pts. "
               "Ferramenta de estudo — nao e recomendacao.")


# -----------------------------------------------------------------------------
# MAIN
# -----------------------------------------------------------------------------
def main():
    st.set_page_config(page_title="PrumoQuant · Abertura NQ+ES", layout="wide")
    st.title("PrumoQuant — Trader de Abertura  ·  NQ + ES")
    st.caption("Ferramenta de ESTUDO. Nao e recomendacao de investimento. "
               "SOMENTE LEITURA.")

    dt = agora_ny()
    fase = fase_do_dia(dt)

    fase_label = {
        "aguardando": "🌙 Aguardando (mercado fechado)",
        "pre": "🌅 Pré-abertura (contexto macro)",
        "captura": "📸 Captura (congelando fluxo)",
        "ativo": "🟢 Ativo (fluxo real)",
        "pos": "🔒 Encerrado",
    }.get(fase, fase)
    st.info(f"**Hora NY:** {dt.strftime('%H:%M:%S')}  ·  **Fase:** {fase_label}")

    # Sidebar: filtros de qualidade + divisor de calibracao
    st.sidebar.header("Filtros / Calibração")
    cfg = {
        "max_spread": st.sidebar.slider("Spread máx (%)", 1.0, 50.0,
                                        DEFAULT_MAX_SPREAD_PCT, 1.0),
        "min_vol": st.sidebar.slider("Volume mínimo por strike", 1, 100,
                                     DEFAULT_MIN_VOL, 1),
        "divisor": st.sidebar.number_input("Divisor de calibração NET", 0.1, 100.0,
                                           1.0, 0.1),
    }
    st.sidebar.caption("Divisor: calibrar lado a lado com a Quantico "
                       "(NET op ÷ NET Quantico).")

    macro = macro_contexto()

    col1, col2 = st.columns(2)
    with col1:
        render_card("NQ", "QQQ", STOP_NQ, fase, macro, cfg)
    with col2:
        render_card("ES", "SPY", STOP_ES, fase, macro, cfg)

    st.divider()
    st.caption(
        "Honestidade estrutural: antes de 9h30 NY nao existe fluxo de opcoes; "
        "o painel mostra so contexto macro rotulado como palpite. Direcao com "
        "fluxo real a partir de 9h30:15. NET e aproximacao direcional (Tradier "
        "so da volume acumulado, sem agressor), calibravel pelo divisor."
    )


if __name__ == "__main__":
    main()
