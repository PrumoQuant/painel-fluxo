# ============================================================================
# PAINEL DE FLUXO DE OPÇÕES — VERSÃO 3 (ESTUDO PESSOAL)
# ============================================================================
# Correções e melhorias em relação à v2:
#   1. GAMMA FLIP corrigido: só strikes a ±10% do preço; escolhe o
#      cruzamento de sinal MAIS PRÓXIMO do spot (antes pegava lixo distante).
#   2. VWAP com zona de equilíbrio (±0,05%): fim da leitura "vendedores no
#      controle" por diferença de 1 centavo.
#   3. NaN eliminado na entrada e na saída; CSV recarregado é saneado.
#   4. Detecção de MERCADO ABERTO/FECHADO pela idade do dado: fora do
#      pregão o fluxo congela e o painel avisa qual sessão está exibindo.
#   5. Fluxo POR STRIKE (volume imbalance) — em quais strikes o dinheiro
#      está entrando, painel novo.
#   6. Estética: tema escuro, valores em formato humano ($1.2M),
#      playbook em estilo terminal, deltas Δ1m/Δ5m/Δ10m do fluxo.
#
# HONESTIDADE TÉCNICA (vale sempre):
#   - Dados yfinance: gratuitos, atrasados (~15 min em opções), open
#     interest atualizado 1x/dia. O net premium é ESTIMATIVA por
#     diferença de volume + inferência bid/ask, não fluxo real de tick.
#   - A convenção do GEX (calls +, puts -) é PREMISSA sobre o
#     posicionamento dos dealers, não fato observável.
#   - Ferramenta de ESTUDO. Não é recomendação de investimento.
#
# Como rodar (Windows):
#   pip install streamlit yfinance plotly pandas numpy scipy streamlit-autorefresh
#   streamlit run painel_fluxo_v3.py
# ============================================================================

import os
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from scipy.stats import norm
from streamlit_autorefresh import st_autorefresh

# ----------------------------------------------------------------------------
# CONFIGURAÇÃO DA PÁGINA + ESTILO VISUAL
# ----------------------------------------------------------------------------
st.set_page_config(page_title="Painel de Fluxo — Estudo", layout="wide",
                   initial_sidebar_state="collapsed")

# CSS: força o visual escuro e cria os componentes customizados
# (cartões de métrica, selo de status do mercado, caixa-terminal do playbook).
st.markdown("""
<style>
    .stApp { background-color: #0b0f14; }
    section[data-testid="stSidebar"] { background-color: #10161d; }
    h1, h2, h3, p, span, label { color: #e6edf3; }

    /* Cartões de métricas */
    .cartao {
        background: #131a22; border: 1px solid #1f2937; border-radius: 10px;
        padding: 14px 16px 10px 16px; height: 100%;
    }
    .cartao .rotulo { font-size: 0.72rem; letter-spacing: 1px;
        text-transform: uppercase; color: #8b98a5; margin-bottom: 2px; }
    .cartao .valor { font-size: 1.55rem; font-weight: 700; color: #e6edf3;
        font-variant-numeric: tabular-nums; }
    .cartao .sub { font-size: 0.75rem; color: #8b98a5; margin-top: 2px; }
    .verde { color: #22c55e !important; }
    .vermelho { color: #ef4444 !important; }
    .amarelo { color: #eab308 !important; }

    /* Selo de status do mercado */
    .selo {
        display: inline-block; padding: 4px 12px; border-radius: 999px;
        font-size: 0.75rem; font-weight: 700; letter-spacing: 1px;
    }
    .selo-aberto { background: #052e16; color: #22c55e; border: 1px solid #14532d; }
    .selo-fechado { background: #450a0a; color: #f87171; border: 1px solid #7f1d1d; }

    /* Caixa-terminal do playbook */
    .terminal {
        background: #05100a; border: 1px solid #14532d; border-radius: 10px;
        padding: 20px 24px; font-family: 'Consolas', 'Courier New', monospace;
        font-size: 0.92rem; line-height: 1.75; color: #86efac;
        white-space: pre-wrap;
    }
    .terminal .titulo { color: #22c55e; font-weight: 700; }
    .terminal .aviso { color: #6b7280; font-size: 0.8rem; }
    .terminal .destaque { color: #fbbf24; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

st_autorefresh(interval=60_000, key="atualizacao_automatica")

st.sidebar.title("Configurações")
TICKER = st.sidebar.selectbox("Ativo (ETF líquido)", ["SPY", "QQQ"])
TAXA_JUROS = st.sidebar.number_input("Taxa de juros anual (r)", value=0.05,
                                     step=0.005, format="%.3f")
st.sidebar.caption("Ferramenta de ESTUDO. Dados gratuitos/atrasados "
                   "(yfinance). Não é recomendação de investimento.")

# ----------------------------------------------------------------------------
# FUNÇÕES AUXILIARES
# ----------------------------------------------------------------------------

def num(valor):
    """Converte para float tratando vazio/NaN como 0 (evita contaminar somas)."""
    try:
        v = float(valor)
        return 0.0 if pd.isna(v) else v
    except (TypeError, ValueError):
        return 0.0


def fmt_usd(v):
    """Formato humano de dinheiro: $1.2M, $340K, -$18K. Traders leem assim."""
    v = num(v)
    sinal = "-" if v < 0 else ""
    a = abs(v)
    if a >= 1_000_000_000: return f"{sinal}${a/1_000_000_000:.1f}B"
    if a >= 1_000_000:     return f"{sinal}${a/1_000_000:.1f}M"
    if a >= 1_000:         return f"{sinal}${a/1_000:.0f}K"
    return f"{sinal}${a:.0f}"


def gamma_black_scholes(S, K, T, r, sigma):
    """Gamma pela fórmula de Black-Scholes (a 'aceleração' do hedge)."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return norm.pdf(d1) / (S * sigma * np.sqrt(T))


@st.cache_data(ttl=55, show_spinner=False)
def buscar_dados(ticker):
    """Busca histórico intradiário (1 min) e a cadeia do vencimento mais próximo."""
    tk = yf.Ticker(ticker)
    hist = tk.history(period="1d", interval="1m")
    vencs = tk.options
    if not vencs:
        return hist, None, None, None
    venc = vencs[0]
    cadeia = tk.option_chain(venc)
    return hist, cadeia.calls.copy(), cadeia.puts.copy(), venc


def calcular_vwap(hist):
    """VWAP: preço médio ponderado por volume — o 'preço justo' do dia."""
    tipico = (hist["High"] + hist["Low"] + hist["Close"]) / 3
    vol = hist["Volume"].replace(0, np.nan)
    vwap = (tipico * hist["Volume"]).cumsum() / hist["Volume"].cumsum().replace(0, np.nan)
    return vwap.ffill()


def calcular_gex(calls, puts, spot, venc_str, r):
    """
    Exposição gamma dos dealers por strike (convenção: calls +, puts -).
    Restrito a strikes a ±10% do spot — fora disso o GEX é irrelevante
    e só polui o gráfico e o cálculo do flip (o bug da v2).
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
            g = gamma_black_scholes(spot, k, T, r, iv)
            gex = g * oi * 100 * spot
            linhas.append({"strike": k, "gex": gex if tipo == "call" else -gex})

    gex_df = pd.DataFrame(linhas)
    if gex_df.empty:
        return gex_df, None, None, None

    por_strike = gex_df.groupby("strike")["gex"].sum().reset_index()
    call_wall = por_strike.loc[por_strike["gex"].idxmax(), "strike"]
    put_wall = por_strike.loc[por_strike["gex"].idxmin(), "strike"]

    # GAMMA FLIP corrigido: entre todos os pontos onde o GEX acumulado
    # troca de sinal, escolhemos o MAIS PRÓXIMO do preço atual.
    ordenado = por_strike.sort_values("strike").reset_index(drop=True)
    acum = ordenado["gex"].cumsum().values
    cruzamentos = [
        float(ordenado["strike"][i])
        for i in range(1, len(acum))
        if (acum[i - 1] < 0 <= acum[i]) or (acum[i - 1] >= 0 > acum[i])
    ]
    flip = min(cruzamentos, key=lambda k: abs(k - spot)) if cruzamentos else None

    return por_strike, call_wall, put_wall, flip


def estimar_fluxo(calls, puts, ticker, mercado_ativo):
    """
    Net premium estimado por diferença de volume entre ciclos (fotografias),
    com inferência do agressor via posição do último preço entre bid e ask.
    Também acumula o fluxo POR STRIKE (painel de volume imbalance).
    Com mercado fechado, NÃO acumula (evita gráfico vazio/enganoso).
    """
    k_snap, k_serie, k_strike = (f"snap_{ticker}", f"serie_{ticker}",
                                 f"strikes_{ticker}")
    hoje = datetime.now().strftime("%Y%m%d")
    arq = f"fluxo_{ticker}_{hoje}.csv"

    # Recarrega a série do dia do CSV (sobrevive a reinício do painel):
    if k_serie not in st.session_state:
        st.session_state[k_serie] = []
        if os.path.exists(arq):
            try:
                df = pd.read_csv(arq).fillna(0.0)  # saneia NaN antigos
                st.session_state[k_serie] = df.to_dict("records")
            except Exception:
                pass
    if k_strike not in st.session_state:
        st.session_state[k_strike] = {}

    # Fotografia atual: símbolo -> (volume, last, bid, ask, é_call, strike)
    atual = {}
    for df, eh_call in ((calls, True), (puts, False)):
        for _, op in df.iterrows():
            atual[op["contractSymbol"]] = (
                num(op.get("volume")), num(op.get("lastPrice")),
                num(op.get("bid")), num(op.get("ask")),
                eh_call, num(op.get("strike")),
            )

    bull = bear = 0.0
    anterior = st.session_state.get(k_snap)

    if anterior is not None and mercado_ativo:
        for simbolo, (vol, last, bid, ask, eh_call, strike) in atual.items():
            d_vol = vol - anterior.get(simbolo, (0,))[0]
            if d_vol <= 0 or last <= 0:
                continue
            # Filtro de liquidez: spread muito largo (>25% do meio) torna a
            # inferência de agressor pouco confiável — descartamos.
            meio = (bid + ask) / 2 if (bid > 0 and ask > 0) else last
            if meio > 0 and bid > 0 and ask > 0 and (ask - bid) / meio > 0.25:
                continue
            premio = d_vol * last * 100
            comprador = last >= meio
            bullish_op = (eh_call and comprador) or (not eh_call and not comprador)
            if bullish_op:
                bull += premio
            else:
                bear += premio
            st.session_state[k_strike][strike] = (
                st.session_state[k_strike].get(strike, 0.0)
                + (premio if bullish_op else -premio)
            )

    st.session_state[k_snap] = atual

    if mercado_ativo and anterior is not None:
        serie = st.session_state[k_serie]
        ult = serie[-1] if serie else {"bull_acum": 0, "bear_acum": 0, "net_acum": 0}
        serie.append({
            "hora": datetime.now().strftime("%H:%M"),
            "bull_acum": num(ult["bull_acum"]) + bull,
            "bear_acum": num(ult["bear_acum"]) + bear,
            "net_acum": num(ult["net_acum"]) + (bull - bear),
        })
        try:
            pd.DataFrame(serie).to_csv(arq, index=False)
        except Exception:
            pass

    return st.session_state[k_serie], st.session_state[k_strike], bull, bear


def gerar_playbook(spot, vwap_atual, call_wall, put_wall, flip, net_acum,
                   ticker, mercado_ativo, data_sessao):
    """
    Narração em estilo terminal. Regras herdadas da observação das
    ferramentas comerciais (método, não texto): cenário condicional,
    cláusula de invalidação, 'não perseguir' quando colado no alvo.
    """
    L = []
    L.append(f"<span class='titulo'>PLAYBOOK {ticker} · "
             f"{datetime.now():%d/%m/%Y %H:%M}</span>")
    if not mercado_ativo:
        L.append(f"<span class='destaque'>[MERCADO FECHADO]</span> níveis "
                 f"calculados sobre o pregão de {data_sessao} — leitura "
                 f"preparatória para a próxima abertura.")
    L.append("")

    # Regime de gamma:
    if flip is not None:
        if spot > flip:
            L.append(f"REGIME ......: gamma POSITIVO (spot {spot:.2f} > flip "
                     f"{flip:.2f}). Movimentos tendem a ser contidos; muros "
                     f"agem como ímã/barreira.")
        else:
            L.append(f"REGIME ......: gamma NEGATIVO (spot {spot:.2f} < flip "
                     f"{flip:.2f}). Movimentos tendem a ACELERAR; rompimentos "
                     f"ganham força.")
    else:
        L.append("REGIME ......: flip não identificado na banda de ±10% — "
                 "tratar leitura de regime com cautela.")

    # VWAP com zona de equilíbrio (correção da v2):
    if vwap_atual:
        dif_pct = (spot - vwap_atual) / vwap_atual * 100
        if abs(dif_pct) < 0.05:
            L.append(f"VWAP ........: {vwap_atual:.2f} · preço COLADO no VWAP "
                     f"({dif_pct:+.2f}%) → mercado em decisão, sem dono.")
        elif dif_pct > 0:
            L.append(f"VWAP ........: {vwap_atual:.2f} · preço ACIMA "
                     f"({dif_pct:+.2f}%) → compradores no controle.")
        else:
            L.append(f"VWAP ........: {vwap_atual:.2f} · preço ABAIXO "
                     f"({dif_pct:+.2f}%) → vendedores no controle.")

    # Fluxo:
    if net_acum > 0:
        L.append(f"FLUXO .......: {fmt_usd(net_acum)} líquido comprador (estimado).")
    elif net_acum < 0:
        L.append(f"FLUXO .......: {fmt_usd(net_acum)} líquido vendedor (estimado).")
    else:
        L.append("FLUXO .......: sem leitura acumulada nesta sessão.")

    # Distância aos muros:
    if call_wall and put_wall:
        d_call = (call_wall - spot) / spot * 100
        d_put = (spot - put_wall) / spot * 100
        L.append(f"MUROS .......: call wall {call_wall:.0f} ({d_call:+.2f}%) | "
                 f"put wall {put_wall:.0f} ({-d_put:+.2f}%)")
        L.append("")
        L.append("<span class='titulo'>CENÁRIOS (estudo, não recomendação)</span>")

        colado_call = abs(spot - call_wall) / spot < 0.0015
        colado_put = abs(spot - put_wall) / spot < 0.0015

        if colado_call:
            L.append(f"[1] Preço JÁ colado no call wall ({call_wall:.2f}): zona "
                     f"histórica de realização — NÃO PERSEGUIR compra aqui.")
        else:
            L.append(f"[1] SE sustentar acima do VWAP e do put wall "
                     f"({put_wall:.2f}) com fluxo comprador → caminho "
                     f"estatístico aponta o call wall ({call_wall:.2f}) como "
                     f"ímã. Invalidação: perda do VWAP com fluxo vendedor.")
        if colado_put:
            L.append(f"[2] Preço JÁ colado no put wall ({put_wall:.2f}): zona "
                     f"de suporte por hedge — NÃO PERSEGUIR venda aqui.")
        else:
            L.append(f"[2] SE perder o VWAP com fluxo vendedor confirmando → "
                     f"put wall ({put_wall:.2f}) vira alvo/suporte de "
                     f"referência. Invalidação: retomada do VWAP.")

    L.append("")
    L.append("<span class='aviso'>Premissas: dealers vendidos (convenção), "
             "dados gratuitos/atrasados (yfinance), fluxo estimado por "
             "diferença de volume. Ferramenta de estudo — não é recomendação "
             "de investimento.</span>")
    return "<div class='terminal'>" + "\n".join(L) + "</div>"


def cartao(rotulo, valor, sub="", classe=""):
    """Gera o HTML de um cartão de métrica."""
    return (f"<div class='cartao'><div class='rotulo'>{rotulo}</div>"
            f"<div class='valor {classe}'>{valor}</div>"
            f"<div class='sub'>{sub}</div></div>")


# ----------------------------------------------------------------------------
# EXECUÇÃO PRINCIPAL
# ----------------------------------------------------------------------------
hist, calls, puts, venc = buscar_dados(TICKER)

if hist is None or hist.empty or calls is None:
    st.warning("Sem dados no momento (falha do yfinance). Nova tentativa em 60 s.")
    st.stop()

spot = float(hist["Close"].iloc[-1])
vwap = calcular_vwap(hist)
vwap_atual = float(vwap.iloc[-1]) if not vwap.dropna().empty else None

# MERCADO ABERTO OU FECHADO? Critério pela idade do último candle:
# se o dado mais recente tem mais de 20 min, o pregão não está ativo.
ultimo_candle = hist.index[-1]
agora = pd.Timestamp.now(tz=ultimo_candle.tz)
atraso_min = (agora - ultimo_candle).total_seconds() / 60
mercado_ativo = atraso_min < 20
data_sessao = ultimo_candle.strftime("%d/%m/%Y")

por_strike, call_wall, put_wall, flip = calcular_gex(calls, puts, spot, venc,
                                                     TAXA_JUROS)
serie, fluxo_strikes, bull_1c, bear_1c = estimar_fluxo(calls, puts, TICKER,
                                                       mercado_ativo)
net_acum = num(serie[-1]["net_acum"]) if serie else 0.0
bull_acum = num(serie[-1]["bull_acum"]) if serie else 0.0
bear_acum = num(serie[-1]["bear_acum"]) if serie else 0.0

# Deltas do fluxo (variação do net nos últimos 1, 5 e 10 ciclos):
def delta_ciclos(n):
    if len(serie) > n:
        return net_acum - num(serie[-1 - n]["net_acum"])
    return None

d1, d5, d10 = delta_ciclos(1), delta_ciclos(5), delta_ciclos(10)

# --- CABEÇALHO ---
selo = ("<span class='selo selo-aberto'>● MERCADO ABERTO</span>"
        if mercado_ativo else
        f"<span class='selo selo-fechado'>● MERCADO FECHADO · pregão de "
        f"{data_sessao}</span>")
st.markdown(f"## Fluxo de Opções — {TICKER} &nbsp; {selo}",
            unsafe_allow_html=True)
st.caption(f"Atualizado {datetime.now():%H:%M:%S} · último dado do ativo: "
           f"{ultimo_candle:%H:%M} ({atraso_min:.0f} min atrás) · "
           f"vencimento analisado: {venc} · atualização automática a cada 60 s")

# --- CARTÕES DE MÉTRICAS ---
if vwap_atual:
    dif_pct = (spot - vwap_atual) / vwap_atual * 100
    if abs(dif_pct) < 0.05:
        vwap_classe, vwap_sub = "amarelo", "preço colado — equilíbrio"
    elif dif_pct > 0:
        vwap_classe, vwap_sub = "verde", f"preço {dif_pct:+.2f}% acima"
    else:
        vwap_classe, vwap_sub = "vermelho", f"preço {dif_pct:+.2f}% abaixo"
else:
    vwap_classe, vwap_sub = "", ""

net_classe = "verde" if net_acum > 0 else ("vermelho" if net_acum < 0 else "")
net_sub = " · ".join(f"Δ{n}m {fmt_usd(d)}"
                     for n, d in (("1", d1), ("5", d5), ("10", d10))
                     if d is not None) or "aguardando ciclos"

c = st.columns(6)
c[0].markdown(cartao("Spot", f"{spot:.2f}"), unsafe_allow_html=True)
c[1].markdown(cartao("VWAP", f"{vwap_atual:.2f}" if vwap_atual else "—",
                     vwap_sub, vwap_classe), unsafe_allow_html=True)
c[2].markdown(cartao("Call Wall", f"{call_wall:.0f}" if call_wall else "—",
                     f"{(call_wall - spot) / spot * 100:+.2f}% do spot"
                     if call_wall else "", "verde"), unsafe_allow_html=True)
c[3].markdown(cartao("Put Wall", f"{put_wall:.0f}" if put_wall else "—",
                     f"{(put_wall - spot) / spot * 100:+.2f}% do spot"
                     if put_wall else "", "vermelho"), unsafe_allow_html=True)
c[4].markdown(cartao("Gamma Flip", f"{flip:.0f}" if flip else "—",
                     "regime positivo" if (flip and spot > flip)
                     else ("regime negativo" if flip else "")),
              unsafe_allow_html=True)
c[5].markdown(cartao("Net Premium (dia)", fmt_usd(net_acum), net_sub,
                     net_classe), unsafe_allow_html=True)

st.markdown("")

# --- TEMA PADRÃO DOS GRÁFICOS ---
def tema(fig, altura):
    fig.update_layout(
        template="plotly_dark", height=altura,
        paper_bgcolor="#0b0f14", plot_bgcolor="#0f151c",
        margin=dict(t=48, b=28, l=10, r=10),
        legend=dict(orientation="h", y=1.12, x=0),
        font=dict(size=12),
    )
    fig.update_xaxes(gridcolor="#1f2937")
    fig.update_yaxes(gridcolor="#1f2937")
    return fig

col_esq, col_dir = st.columns([3, 2])

with col_esq:
    # GEX por strike:
    if not por_strike.empty:
        faixa = por_strike[(por_strike["strike"] > spot * 0.965)
                           & (por_strike["strike"] < spot * 1.035)]
        fig = go.Figure()
        fig.add_bar(x=faixa["strike"], y=faixa["gex"],
                    marker_color=["#22c55e" if g >= 0 else "#3b82f6"
                                  for g in faixa["gex"]],
                    name="GEX")
        fig.add_vline(x=spot, line_dash="dot", line_color="#e6edf3",
                      annotation_text=f"Spot {spot:.2f}",
                      annotation_font_color="#e6edf3")
        if call_wall:
            fig.add_vline(x=call_wall, line_color="#22c55e",
                          annotation_text="Call Wall",
                          annotation_font_color="#22c55e")
        if put_wall:
            fig.add_vline(x=put_wall, line_color="#ef4444",
                          annotation_text="Put Wall",
                          annotation_font_color="#ef4444")
        if flip:
            fig.add_vline(x=flip, line_dash="dash", line_color="#eab308",
                          annotation_text="Flip",
                          annotation_font_color="#eab308")
        fig.update_layout(title=f"Exposição Gamma por Strike (venc. {venc})")
        fig.update_yaxes(tickformat="~s")
        st.plotly_chart(tema(fig, 380), use_container_width=True)

    # Fluxo acumulado (só com dados reais — nada de gráfico vazio):
    if len(serie) >= 2 and (bull_acum + bear_acum) > 0:
        df_f = pd.DataFrame(serie)
        fig2 = go.Figure()
        fig2.add_scatter(x=df_f["hora"], y=df_f["bull_acum"], fill="tozeroy",
                         name="Comprador (acum.)", line_color="#22c55e")
        fig2.add_scatter(x=df_f["hora"], y=df_f["bear_acum"], fill="tozeroy",
                         name="Vendedor (acum.)", line_color="#ef4444")
        fig2.update_layout(title="Net Premium estimado — acumulado da sessão")
        fig2.update_yaxes(tickprefix="$", tickformat="~s")
        st.plotly_chart(tema(fig2, 300), use_container_width=True)
    elif mercado_ativo:
        st.info("Fluxo de prêmio em construção — precisa de ~2 ciclos "
                "(2 min) com mercado aberto para as primeiras leituras.")
    else:
        st.info("Fluxo de prêmio pausado: mercado fechado. Na próxima "
                "sessão, a acumulação recomeça sozinha.")

with col_dir:
    # Rosca calls x puts:
    total = bull_acum + bear_acum
    if total > 0:
        rotulo = "Comprador" if net_acum >= 0 else "Vendedor"
        cor = "#22c55e" if net_acum >= 0 else "#ef4444"
        fig3 = go.Figure(go.Pie(
            labels=["Fluxo comprador", "Fluxo vendedor"],
            values=[bull_acum, bear_acum], hole=0.68,
            marker_colors=["#22c55e", "#ef4444"],
            textinfo="percent", textfont_size=13,
        ))
        fig3.update_layout(
            title="Balanço do fluxo (sessão)",
            annotations=[dict(text=f"<b>{fmt_usd(net_acum)}</b><br>{rotulo}",
                              showarrow=False, font=dict(size=17, color=cor))],
            showlegend=False,
        )
        st.plotly_chart(tema(fig3, 300), use_container_width=True)

    # Fluxo por strike (volume imbalance) — painel novo:
    if fluxo_strikes:
        df_s = pd.DataFrame(
            [{"strike": k, "net": v} for k, v in fluxo_strikes.items()])
        top = (df_s.reindex(df_s["net"].abs()
                            .sort_values(ascending=False).index)
               .head(12).sort_values("strike"))
        fig5 = go.Figure(go.Bar(
            y=[f"{s:.0f}" for s in top["strike"]], x=top["net"],
            orientation="h",
            marker_color=["#22c55e" if v >= 0 else "#ef4444"
                          for v in top["net"]],
        ))
        fig5.update_layout(title="Fluxo por strike (sessão) — onde o "
                                 "dinheiro está entrando")
        fig5.update_xaxes(tickprefix="$", tickformat="~s")
        st.plotly_chart(tema(fig5, 320), use_container_width=True)

    # Preço x VWAP:
    fig4 = go.Figure()
    fig4.add_scatter(x=hist.index, y=hist["Close"], name="Preço",
                     line=dict(color="#eab308", width=1.6))
    fig4.add_scatter(x=hist.index, y=vwap, name="VWAP",
                     line=dict(color="#a78bfa", width=1.6))
    fig4.update_layout(title=f"Intradiário ({data_sessao}): preço x VWAP")
    st.plotly_chart(tema(fig4, 280), use_container_width=True)

# --- PLAYBOOK (terminal) ---
st.markdown("")
st.markdown(gerar_playbook(spot, vwap_atual, call_wall, put_wall, flip,
                           net_acum, TICKER, mercado_ativo, data_sessao),
            unsafe_allow_html=True)
