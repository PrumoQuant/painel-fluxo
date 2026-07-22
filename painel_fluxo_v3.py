# =============================================================================
# PRUMOQUANT — ABERTURA NQ + ES  ·  v1.1  ·  arquivo unico
# -----------------------------------------------------------------------------
# Ferramenta de ESTUDO. Nao e recomendacao de investimento. SOMENTE LEITURA.
#
# MUDANCAS v1.1 (correcao do bug de escala confirmado ao vivo em 22/07):
#   BUG 1 corrigido: janela de strikes ERA 0.90-1.10*S (larga, pegava ITM
#      profundo com premio gigante). AGORA 0.97-1.03*S (so o dinheiro, como
#      a Quantico). Era a causa 3 do v8.2.
#   BUG 2 corrigido: NET agora reportado em escala de MILHARES ($K), que e a
#      escala real da Quantico (dezenas/centenas de K), nao milhoes.
#   BUG 3 corrigido: sinal do agressor ERA binario (last>=mid -> +1/-1), o que
#      gerava ruido (NET pulava de -4M para +15M). AGORA usa a distancia
#      relativa do last ao mid como PESO continuo, muito mais estavel.
#   NOVO: leitura de REGIME DE GAMMA por card (imã/estabiliza vs estilingue/
#      acelera), com base no sinal do GEX na faixa do preco.
#
# CONTRATO DE HONESTIDADE (lema: "Quero estrategia, nao sorte"):
#   - Antes de 9h30 NY o fluxo de opcoes NAO EXISTE -> so CONTEXTO MACRO,
#     rotulado "PALPITE MACRO". NUNCA seta de direcao pre-abertura.
#   - Direcao com FLUXO REAL so a partir de 9h30:15 NY.
#   - Fora do pregao de acoes, net_dir = None (nunca zero). Sem fantasma.
#   - NET continua sendo APROXIMACAO (Tradier nao da agressor por trade).
#     Calibravel pelo divisor, nunca replica exata da Quantico.
#
# STACK: Tradier Pro (fluxo SPY/QQQ) + yfinance (preco NQ/ES, macro).
# PONTES:  QQQ -> NQ  |  SPY -> ES.   STOPS: NQ 50 pts · ES 7 pts.
# =============================================================================

import streamlit as st
import requests
import pandas as pd
from datetime import datetime, time as dtime
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

T1_PRE = dtime(9, 29, 45)
T2_FREEZE = dtime(9, 30, 15)

STOP_NQ = 50
STOP_ES = 7

DEFAULT_MAX_SPREAD_PCT = 15.0
DEFAULT_MIN_VOL = 5

# v1.1: janela estreita (so o dinheiro). Era 0.90/1.10.
JANELA_LO = 0.97
JANELA_HI = 1.03

# v1.1: escala. NET reportado dividido por ESCALA_K para cair na faixa da
# Quantico (milhares). 1000 = reporta em unidades de $1K de notional.
ESCALA_K = 1000.0

TRADIER_BASE = "https://api.tradier.com/v1"


# -----------------------------------------------------------------------------
# RELOGIO / JANELA OPERACIONAL
# -----------------------------------------------------------------------------
def agora_ny():
    return datetime.now(NY)


def pregao_acoes_aberto(dt=None):
    if dt is None:
        dt = agora_ny()
    if dt.weekday() >= 5:
        return False
    t = dt.time()
    return dtime(9, 30) <= t <= dtime(16, 0)


def fase_do_dia(dt=None):
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
# TRADIER
# -----------------------------------------------------------------------------
def _tradier_headers():
    token = st.secrets.get("TRADIER_TOKEN", "")
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


@st.cache_data(ttl=12)
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
# NET OPERACIONAL — v1.1 (tres bugs de escala corrigidos)
# -----------------------------------------------------------------------------
def net_operacional(ticker, spot, divisor=1.0, max_spread_pct=DEFAULT_MAX_SPREAD_PCT,
                    min_vol=DEFAULT_MIN_VOL):
    """
    NET op v1.1 = 0DTE + janela ESTREITA (0.97-1.03*S) + peso continuo de
    agressor + escala em milhares. Retorna None se pregao fechado.
    Sinal: >0 comprador; <0 vendedor. Unidade: ~milhares (comparavel a Quantico).
    """
    if not pregao_acoes_aberto() or spot <= 0:
        return None

    exps = tradier_expirations(ticker)
    if not exps:
        return None
    chain = tradier_chain(ticker, exps[0])
    if not chain:
        return None

    lo, hi = JANELA_LO * spot, JANELA_HI * spot
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

            # BUG 3 corrigido: peso CONTINUO em vez de +1/-1 binario.
            # (last - mid) / (spread/2) da uma medida de "quao agressor",
            # limitada a [-1, +1]. Reduz o ruido do sinal.
            half = (ask - bid) / 2.0
            if half > 0:
                press = (last - mid) / half
                press = max(-1.0, min(1.0, press))
            else:
                press = 0.0

            if otype == "call":
                net += press * notional
            elif otype == "put":
                net += -press * notional
        except Exception:
            continue

    net = net / ESCALA_K              # BUG 2: escala em milhares
    return net / divisor if divisor else net


# -----------------------------------------------------------------------------
# TRES INDICADORES + REGIME DE GAMMA — v1.1
# -----------------------------------------------------------------------------
def tres_indicadores(ticker, spot, max_spread_pct, min_vol):
    """
    Retorna dict:
      delta_hedging, fluxo_inst, time_pressure  -> votos {+1,0,-1}
      gex_faixa   -> GEX liquido na faixa do preco (para regime de gamma)
    None se pregao fechado.
    """
    if not pregao_acoes_aberto() or spot <= 0:
        return None
    exps = tradier_expirations(ticker)
    if not exps:
        return None
    chain = tradier_chain(ticker, exps[0])
    if not chain:
        return None

    lo, hi = JANELA_LO * spot, JANELA_HI * spot
    gex = 0.0
    fluxo = 0.0
    theta_press = 0.0

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

            g_contrib = gamma * oi * 100.0 * (spot ** 2)
            gex += g_contrib if otype == "call" else -g_contrib

            notional = vol * last * 100.0
            fluxo += notional if otype == "call" else -notional

            theta_press += theta * vol * (1 if otype == "call" else -1)
        except Exception:
            continue

    def voto(x):
        if x > 0:
            return 1
        if x < 0:
            return -1
        return 0

    return {
        "delta_hedging": voto(gex),
        "fluxo_inst": voto(fluxo),
        "time_pressure": voto(theta_press),
        "gex_faixa": gex,   # valor bruto para o regime
    }


def regime_gamma(gex_faixa):
    """
    Le o regime a partir do GEX liquido na faixa do preco.
    GEX positivo -> ima (estabiliza, range).  Negativo -> estilingue (acelera).
    """
    if gex_faixa is None:
        return ("—", "pregao fechado")
    if gex_faixa > 0:
        return ("🧲 GAMMA POSITIVO", "ima: segura/estabiliza, tende a range")
    if gex_faixa < 0:
        return ("🎢 GAMMA NEGATIVO", "estilingue: acelera, tende a tendencia")
    return ("—", "neutro")


def placar_4_votos(indic, net):
    if indic is None:
        return ("Fluxo fechado", 0, 0, {})
    votos = {
        "delta_hedging": indic.get("delta_hedging", 0),
        "fluxo_inst": indic.get("fluxo_inst", 0),
        "time_pressure": indic.get("time_pressure", 0),
    }
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
# MACRO (yfinance) — CONTEXTO
# -----------------------------------------------------------------------------
@st.cache_data(ttl=60)
def macro_contexto():
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
    if not macro:
        return ("SEM DADO", 0.0)
    score = 0.0
    if "VIX" in macro:
        score -= macro["VIX"]["pct"] * 0.5
    if "DXY" in macro:
        score -= macro["DXY"]["pct"] * 0.3
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
# UI — CARD
# -----------------------------------------------------------------------------
def render_card(nome_fut, ticker_fluxo, stop_pts, fase, macro, cfg):
    st.subheader(f"{nome_fut}  ·  fluxo via {ticker_fluxo}")

    fut = macro.get(nome_fut, {})
    if fut:
        st.metric(f"{nome_fut} (futuro agora)", f"{fut['valor']:.2f}",
                  f"{fut['pct']:+.2f}%")

    if fase in ("pre", "aguardando", "captura"):
        rotulo, score = vies_macro(macro)
        st.warning("PALPITE MACRO — fluxo ainda nao abriu. NAO e sinal de fluxo.")
        st.write(f"**Viés macro:** {rotulo}  ·  score {score:+.2f}")
        if fase == "captura":
            st.info("Congelando snapshot do fluxo (9h29:45 → 9h30:15)…")
        st.caption("Sem direção. O fluxo vota a partir de 9h30:15 NY.")
        return

    if fase == "pos":
        st.info("Pregao encerrado (apos 16h NY). Sem leitura de fluxo ativa.")
        return

    spot = preco_spot(ticker_fluxo)
    if spot <= 0:
        st.error(f"Sem cotacao de {ticker_fluxo} (warm-up/credencial). "
                 "Painel segue sem quebrar.")
        return

    net = net_operacional(ticker_fluxo, spot, divisor=cfg["divisor"],
                          max_spread_pct=cfg["max_spread"], min_vol=cfg["min_vol"])
    indic = tres_indicadores(ticker_fluxo, spot, cfg["max_spread"], cfg["min_vol"])
    direcao, comp, vend, votos = placar_4_votos(indic, net)
    inten = intensidade(comp, vend)

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

    # NET em escala de milhares (comparavel a Quantico)
    if net is not None:
        st.write(f"**NET operacional:** {net:+,.0f} (~$K, aproximacao calibravel)")
    else:
        st.write("**NET operacional:** — (pregao fechado)")

    # v1.1: regime de gamma
    if indic is not None:
        selo, desc = regime_gamma(indic.get("gex_faixa"))
        st.write(f"**Regime:** {selo} — {desc}")

    if comp >= 3:
        st.success(f"GATILHO: comprar {nome_fut} na abertura · Stop fixo {stop_pts} pts")
    elif vend >= 3:
        st.success(f"GATILHO: vender {nome_fut} na abertura · Stop fixo {stop_pts} pts")
    else:
        st.warning("Sem gatilho (placar < 3/4). Ficar de fora, aguardar definicao.")

    st.caption(f"Stop fixo {nome_fut}: {stop_pts} pts. Estudo — nao e recomendacao.")


# -----------------------------------------------------------------------------
# MAIN
# -----------------------------------------------------------------------------
def main():
    st.set_page_config(page_title="PrumoQuant · Abertura NQ+ES", layout="wide")
    st.title("PrumoQuant — Trader de Abertura · NQ + ES")
    st.caption("Ferramenta de ESTUDO. Nao e recomendacao de investimento. SOMENTE LEITURA.")

    dt = agora_ny()
    fase = fase_do_dia(dt)
    fase_label = {
        "aguardando": "🌙 Aguardando (mercado fechado)",
        "pre": "🌅 Pré-abertura (contexto macro)",
        "captura": "📸 Captura (congelando fluxo)",
        "ativo": "🟢 Ativo (fluxo real)",
        "pos": "🔒 Encerrado",
    }.get(fase, fase)
    st.info(f"**Hora NY:** {dt.strftime('%H:%M:%S')} · **Fase:** {fase_label}")

    st.sidebar.header("Filtros / Calibração")
    cfg = {
        "max_spread": st.sidebar.slider("Spread máx (%)", 1.0, 50.0,
                                        DEFAULT_MAX_SPREAD_PCT, 1.0),
        "min_vol": st.sidebar.slider("Volume mínimo por strike", 1, 100,
                                     DEFAULT_MIN_VOL, 1),
        "divisor": st.sidebar.number_input("Divisor de calibração NET", 0.1, 100.0,
                                           1.0, 0.1),
    }
    st.sidebar.caption("Divisor: ajuste fino lado a lado com a Quantico "
                       "(NET op ÷ NET Quantico). v1.1 ja corrige a escala grossa.")

    macro = macro_contexto()

    col1, col2 = st.columns(2)
    with col1:
        render_card("NQ", "QQQ", STOP_NQ, fase, macro, cfg)
    with col2:
        render_card("ES", "SPY", STOP_ES, fase, macro, cfg)

    st.divider()
    st.caption(
        "v1.1: janela estreita 0.97-1.03*S, NET em milhares, sinal de agressor "
        "continuo (menos ruido), regime de gamma por card. NET segue sendo "
        "aproximacao (Tradier nao da agressor por trade) — calibrar divisor ao vivo."
    )


if __name__ == "__main__":
    main()
