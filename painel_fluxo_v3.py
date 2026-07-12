# ============================================================================
# PAINEL DE FLUXO DE OPÇÕES — VERSÃO 4.8 "JANELA DE ABERTURA" (ESTUDO)
# PrumoQuant · https://prumoquant.streamlit.app
# ============================================================================
# NOVIDADES v4.8 — janela operacional do Direcionamento de Abertura (11/07/2026):
#  * O card de Abertura agora RESPEITA O ESTADO REAL DO MERCADO (relógio de NY):
#      - 'ativo'      pregão de ações aberto (09:30-16:00 NY) → sinal válido
#      - 'previa'     15 min antes (09:15-09:30 NY)           → prévia (congela na abertura)
#      - 'referencia' futuros abertos, ações fechadas         → só níveis, sinal NÃO vale
#      - 'aguardando' tudo fechado (sábado etc.)              → "aguardando abertura"
#    Fora de 'ativo'/'previa' o card NÃO emite gatilho nem viés (nada de mandar
#    "comprar em 748" num sábado). Corrige o comportamento reportado no print.
#  * Futuros CME (ES/NQ): domingo 18:00 NY → sexta 17:00 NY, pausa diária 17-18 NY.
#  * Contagem regressiva textual até a próxima abertura no card fora de pregão.
#
# NOVIDADES v3.7 — descoberta do menu "Total·1M·5M" (07/07/2026 fim do dia):
#  D6. AGREGAÇÃO "TOTAL": o gráfico Delta Hedging da Quantico tem um filtro
#      Total·1M·5M (visível no tutorial). "Total" = soma de TODOS os vencimentos
#      com PESO IGUAL. O peso decrescente que a v3.6 usava (1/(1+dias/5))
#      distorcia qual barra era a "maior" → deslocava o ímã (751→753) e cortava
#      a magnitude dos vencimentos distantes. Agora o padrão é soma pura (Total),
#      e o modo ponderado virou opção na barra lateral. NVENC também é ajustável
#      ao vivo (slider), para calibrar contra o terminal deles sem editar código.
#      HIPÓTESE a confirmar com prints reais: Total deve alinhar ímã e magnitude.
#
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
from datetime import datetime, time as dtime, timedelta
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
    /* ===== PrumoQuant — tema clean monocromático (inspirado no terminal Quantico) ===== */
    :root {
        --bg: #0a0d12; --surface: #12161c; --surface2: #161b22;
        --line: #232a33; --line-soft: #1b2129;
        --ink: #e6edf3; --ink-2: #9aa5b1; --ink-3: #6b7580;
        --accent: #d9a441;         /* âmbar, usado com MUITA restrição */
        --up: #3fb950; --down: #f0533f; --bar: #4a90d9;
    }
    .stApp { background: var(--bg); }
    section[data-testid="stSidebar"] { background: #0c1015; border-right: 1px solid var(--line-soft); }
    h1,h2,h3,h4,h5,p,span,label,div { color: var(--ink); }
    .block-container { padding-top: 0.9rem; max-width: 1500px; }

    /* ---- cabeçalho ---- */
    .pq-header { display:flex; justify-content:space-between; align-items:flex-end;
        padding:2px 0 12px 0; margin-bottom:6px; border-bottom:1px solid var(--line); }
    .pq-logo { font-size:1.4rem; font-weight:600; letter-spacing:0.5px; color:var(--ink); }
    .pq-logo .fio { color:var(--accent); }
    .pq-sub { display:block; font-size:0.66rem; color:var(--ink-3);
        letter-spacing:2.5px; text-transform:uppercase; margin-top:3px; font-weight:500; }
    .pq-meta { text-align:right; font-size:0.7rem; color:var(--ink-3); line-height:1.7;
        font-variant-numeric:tabular-nums; }

    .selo { display:inline-block; padding:2px 9px; border-radius:4px; font-size:0.64rem;
        font-weight:600; letter-spacing:1px; border:1px solid var(--line); color:var(--ink-2);
        background:var(--surface); }

    /* ---- abas: linha fina, sem caixinhas ---- */
    .stTabs [data-baseweb="tab-list"] { gap:2px; border-bottom:1px solid var(--line); }
    .stTabs [data-baseweb="tab"] { background:transparent; color:var(--ink-3);
        font-size:0.82rem; font-weight:500; padding:8px 16px; border-radius:0; }
    .stTabs [aria-selected="true"] { color:var(--ink); background:transparent;
        border-bottom:2px solid var(--accent); }

    /* ---- mini-painel dos indicadores ---- */
    .qpanel-head { display:flex; justify-content:space-between; align-items:baseline;
        padding:9px 12px 0 12px; background:var(--surface); border:1px solid var(--line);
        border-bottom:0; border-radius:6px 6px 0 0; }
    .qpanel-title { font-size:0.74rem; font-weight:600; color:var(--ink); letter-spacing:0.3px; }
    .qpanel-tk { font-size:0.72rem; color:var(--ink-3); font-variant-numeric:tabular-nums; }
    .qpanel-tk b { color:var(--ink); font-weight:600; }
    .qpanel-sub { display:flex; gap:16px; flex-wrap:wrap; padding:3px 12px 7px 12px;
        background:var(--surface); border-left:1px solid var(--line); border-right:1px solid var(--line);
        font-size:0.7rem; color:var(--ink-3); font-variant-numeric:tabular-nums; }
    .up { color:var(--up) !important; } .down { color:var(--down) !important; }

    /* ---- QUADRO do direcionamento (a assinatura da tela: clean, monocromático) ---- */
    .sinal-box { background:var(--surface); border:1px solid var(--line);
        border-radius:8px; padding:22px 26px; margin:6px 0 4px 0; }
    .sinal-titulo { font-size:0.66rem; letter-spacing:2.5px; text-transform:uppercase;
        color:var(--ink-3); font-weight:600; margin-bottom:3px; }
    .sinal-meta { font-size:0.72rem; color:var(--ink-3); margin-bottom:16px;
        font-variant-numeric:tabular-nums; }
    .sinal-linha { font-size:1.0rem; line-height:1.85; color:var(--ink); font-weight:400; }
    .vies-dir { font-size:1.05rem; margin:8px 0 12px 0; color:var(--ink); }
    .vies-rot { font-size:0.7rem; letter-spacing:1.5px; text-transform:uppercase;
        color:var(--ink-3); font-weight:600; }
    .vies-dir-v { font-size:1.2rem; font-weight:700; letter-spacing:1px; color:var(--ink); }
    .acao-abertura { border:1px solid var(--ink-3); border-radius:8px;
        padding:14px 18px; margin:6px 0 14px 0; background:rgba(255,255,255,0.02); }
    .acao-rot { font-size:0.68rem; letter-spacing:2px; text-transform:uppercase;
        color:var(--ink-3); font-weight:600; margin-right:10px; }
    .acao-big { font-size:1.55rem; font-weight:800; letter-spacing:1px; }
    .vies-forca { font-size:0.8rem; color:var(--ink-2); }
    .sinal-linha .acao { font-weight:600; letter-spacing:0.5px; }
    .sinal-nivel { font-weight:600; color:var(--ink); font-variant-numeric:tabular-nums; }
    .sinal-ctx { font-size:0.8rem; color:var(--ink-2); margin-top:14px;
        padding-top:12px; border-top:1px solid var(--line-soft); }
    .sinal-nota { font-size:0.7rem; color:var(--ink-3); margin-top:8px; line-height:1.5; }
    .sinal-veto { color:var(--ink); font-weight:500; }

    /* ---- cartões ---- */
    .cartao { background:var(--surface); border:1px solid var(--line); border-radius:6px;
        padding:11px 13px 9px 13px; height:100%; }
    .cartao .rotulo { font-size:0.62rem; letter-spacing:1.5px; text-transform:uppercase;
        color:var(--ink-3); margin-bottom:3px; font-weight:500; }
    .cartao .valor { font-size:1.15rem; font-weight:600; color:var(--ink);
        font-variant-numeric:tabular-nums; }
    .cartao .sub { font-size:0.68rem; color:var(--ink-3); margin-top:2px; }

    .disciplina { font-size:0.76rem; color:var(--ink-2); padding:6px 0 0 0; }
    .disciplina b { color:var(--accent); font-weight:600; }

    .setup-linha { font-size:0.8rem; padding:8px 14px; border-radius:6px;
        background:var(--surface); border:1px solid var(--line); margin:2px 0 8px 0;
        color:var(--ink-2); }
    .setup-linha b { font-weight:600; color:var(--ink); }

    /* ---- régua Volume Imbalance ---- */
    .fluxobar-wrap { background:var(--surface); border:1px solid var(--line);
        border-radius:6px; padding:10px 14px 12px 14px; margin:2px 0 8px 0; }
    .fluxobar-top { display:flex; justify-content:space-between; flex-wrap:wrap; gap:4px;
        font-size:0.72rem; color:var(--ink-3); margin-bottom:7px; }
    .fluxobar { display:flex; height:6px; border-radius:3px; overflow:hidden; background:var(--line); }
    .fluxobar .verde-seg { background:var(--up); } .fluxobar .verm-seg { background:var(--down); }
    .fluxobar-sub { display:flex; justify-content:space-between; flex-wrap:wrap; gap:4px;
        font-size:0.72rem; color:var(--ink-3); margin-top:7px; font-variant-numeric:tabular-nums; }
    .verde { color:var(--up) !important; } .vermelho { color:var(--down) !important; }
    .amarelo { color:var(--ink-2) !important; }

    /* ---- placar do Bell (acertos/erros) ---- */
    .placar { display:flex; gap:10px; margin:4px 0 10px 0; flex-wrap:wrap; }
    .placar .cel { flex:1; min-width:80px; background:var(--surface); border:1px solid var(--line);
        border-radius:6px; padding:10px 12px; text-align:center; }
    .placar .cel .n { font-size:1.5rem; font-weight:600; font-variant-numeric:tabular-nums; }
    .placar .cel .l { font-size:0.62rem; letter-spacing:1.5px; text-transform:uppercase;
        color:var(--ink-3); margin-top:2px; }

    /* cartão terminal antigo — neutralizado para o tema clean */
    .terminal { background:var(--surface); border:1px solid var(--line); border-radius:6px;
        padding:16px 20px; font-family:'Consolas','Courier New',monospace; font-size:0.84rem;
        line-height:1.7; color:var(--ink-2); white-space:pre-wrap; margin-bottom:12px; }
    .terminal .titulo { color:var(--ink); font-weight:600; }
    .terminal .aviso { color:var(--ink-3); font-size:0.72rem; }
    .terminal .destaque { color:var(--ink); font-weight:600; }
    .terminal .neg { color:var(--ink-2); font-weight:500; }
    .alerta-vermelho { border:1px solid var(--line) !important; background:var(--surface2) !important; }
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
# PERSISTÊNCIA — SUPABASE (Fase 2.3) — registro de sinais para histórico/acerto
# ----------------------------------------------------------------------------
# Credenciais SÓ nos Secrets do Streamlit (SUPABASE_URL, SUPABASE_KEY), como o
# token Tradier. REGRA DE OURO: se não houver credenciais, TUDO cai no
# session_state (comportamento anterior). O painel NUNCA depende do banco.
import json as _json

def _supabase_creds():
    try:
        url = str(st.secrets.get("SUPABASE_URL", "") or "").strip()
        key = str(st.secrets.get("SUPABASE_KEY", "") or "").strip()
    except Exception:
        url = os.environ.get("SUPABASE_URL", "").strip()
        key = os.environ.get("SUPABASE_KEY", "").strip()
    return (url, key) if (url and key) else (None, None)

def supabase_ativo():
    url, key = _supabase_creds()
    return bool(url and key)

def _sb_headers(key):
    return {"apikey": key, "Authorization": f"Bearer {key}",
            "Content-Type": "application/json", "Prefer": "return=representation"}

def supabase_insert(tabela, linha):
    """Insere uma linha. Retorna (ok, erro). Nunca levanta exceção para a UI."""
    url, key = _supabase_creds()
    if not url:
        return False, "sem credenciais"
    try:
        r = requests.post(f"{url}/rest/v1/{tabela}", headers=_sb_headers(key),
                          data=_json.dumps(linha), timeout=8)
        if r.status_code in (200, 201):
            return True, None
        return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, f"falha de rede: {e}"

def supabase_select(tabela, filtro=""):
    """Lê linhas (filtro PostgREST opcional). Retorna (lista, erro)."""
    url, key = _supabase_creds()
    if not url:
        return [], "sem credenciais"
    try:
        r = requests.get(f"{url}/rest/v1/{tabela}{filtro}",
                         headers=_sb_headers(key), timeout=8)
        if r.status_code == 200:
            return r.json(), None
        return [], f"HTTP {r.status_code}"
    except Exception as e:
        return [], f"falha de rede: {e}"

def supabase_update(tabela, id_col, id_val, campos):
    """Atualiza uma linha por id (ex: gravar resultado no fechamento)."""
    url, key = _supabase_creds()
    if not url:
        return False, "sem credenciais"
    try:
        r = requests.patch(f"{url}/rest/v1/{tabela}?{id_col}=eq.{id_val}",
                           headers=_sb_headers(key), data=_json.dumps(campos), timeout=8)
        return (r.status_code in (200, 204)), None
    except Exception as e:
        return False, f"falha de rede: {e}"

def _stats_do_historico(linhas):
    """Placar (win/loss/be/taxa) a partir de linhas com campo 'resultado'."""
    win = sum(1 for r in linhas if r.get("resultado") == "WIN")
    loss = sum(1 for r in linhas if r.get("resultado") == "LOSS")
    be = sum(1 for r in linhas if r.get("resultado") == "BE")
    dec = win + loss
    taxa = f"{100*win/dec:.0f}%" if dec else "—"
    return {"win": win, "loss": loss, "be": be, "taxa": taxa,
            "total": len(linhas), "avaliados": dec}

def ps_marca_ja_registrada(tk, lado, dia):
    """Evita gravar a mesma marca (tk/lado/dia) duas vezes. A flag de sessão é o
    caminho rápido; a fonte da verdade é o BANCO (sobrevive a reload/reabertura —
    sem isso, reabrir o painel no mesmo dia duplicaria o registro)."""
    chave = f"ps_reg_{tk}_{lado}_{dia}"
    if st.session_state.get(chave):
        return True
    linhas, err = supabase_select(
        "ps_marcas", f"?dia=eq.{dia}&tk=eq.{tk}&lado=eq.{lado}&select=id")
    if err is None and linhas:
        st.session_state[chave] = True
        return True
    st.session_state[chave] = True
    return False

def registrar_ps_marca_banco(tk, ps, hora_ny, dia_iso, nivel_spx):
    """Grava uma marca PS no Supabase (uma vez por tk/lado/dia). Silencioso se
    o banco não estiver configurado — o session_state continua sendo a verdade
    da sessão. O banco é o histórico ENTRE dias."""
    if not supabase_ativo() or ps is None or not ps.get("acende"):
        return
    if ps_marca_ja_registrada(tk, ps["lado"], dia_iso):
        return
    supabase_insert("ps_marcas", {
        "dia": dia_iso, "hora_ny": hora_ny, "tk": tk, "lado": ps["lado"],
        "nivel": round(float(ps["nivel"]), 2),
        "nivel_spx": round(float(nivel_spx), 1) if nivel_spx else None,
        "forca": ps["forca_txt"], "risco": ps["risco"],
        "net_dir": round(float(ps.get("net_dir", 0)), 0), "resultado": None})

def registrar_bell_sinal_banco(tk, sig, dia_iso, hora_ny):
    """Grava o sinal de abertura no Supabase, UMA vez por tk/dia, quando o sinal
    é congelado (na janela de abertura). Silencioso se o banco não existir."""
    if not supabase_ativo() or not sig or sig.get("veto"):
        return
    chave = f"bell_reg_{tk}_{dia_iso}"
    if st.session_state.get(chave):
        return
    # fonte da verdade é o banco: evita duplicar se o painel for reaberto no dia
    linhas, err = supabase_select(
        "bell_sinais", f"?dia=eq.{dia_iso}&tk=eq.{tk}&select=id")
    if err is None and linhas:
        st.session_state[chave] = True
        return
    st.session_state[chave] = True
    vd = sig.get("vies_dir") or {}
    g_compra = g_venda = None
    for acao, nivel, _ in sig.get("linhas", []):
        if nivel and nivel != "—":
            try:
                if acao == "Comprar":
                    g_compra = float(nivel)
                elif acao == "Vender":
                    g_venda = float(nivel)
            except ValueError:
                pass
    supabase_insert("bell_sinais", {
        "dia": dia_iso, "hora_ny": hora_ny, "tk": tk,
        "direcao": vd.get("direcao"), "votos": vd.get("votos"),
        "gatilho_compra": g_compra, "gatilho_venda": g_venda, "resultado": None})

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

st.sidebar.markdown("---")
st.sidebar.caption("Calibração vs Quantico")
MODO_AGREGACAO = st.sidebar.radio(
    "Agregação de vencimentos",
    ["Total (soma pura — como o menu deles)", "Ponderado (0DTE dominante)"],
    help="O gráfico da Quantico tem o filtro Total·1M·5M. 'Total' soma todos os "
         "vencimentos com peso igual (tende a alinhar o ímã e a magnitude com eles). "
         "'Ponderado' dá mais peso ao 0DTE (mais sensível ao dia).")
NVENC_UI = st.sidebar.slider(
    "Vencimentos somados (NVENC)", min_value=1, max_value=8, value=6,
    help="Quantos vencimentos mais próximos entram no GEX e no Time Pressure. "
         "Suba se a magnitude do SPY ficar baixa; desça se o carregamento pesar.")
PESO_PONDERADO = MODO_AGREGACAO.startswith("Ponderado")

st.sidebar.markdown("---")
st.sidebar.caption("PS · Pad Special (trava de crédito)")
st.sidebar.caption("Limiares de NET (fluxo agressor) que graduam o risco da parede. "
                   "Ajuste ao vivo contra a Quantico.")
PS_NET_CONF = st.sidebar.slider("NET confiável até (M)", 0.5, 3.0, 1.5, 0.1,
    help="Abaixo disso a parede banca a reversão — trava de crédito tranquila.")
PS_NET_ATEN = st.sidebar.slider("NET atenção até (M)", 1.0, 4.0, 2.5, 0.1,
    help="Pressão média sobre a parede.")
PS_NET_FORT = st.sidebar.slider("NET forte até (M)", 2.0, 8.0, 4.0, 0.1,
    help="Forte: pode furar ou colar no teto/fundo (foi a sexta). Acima disso, vetada.")
PS_THRESHOLDS = (PS_NET_CONF * 1e6, PS_NET_ATEN * 1e6, PS_NET_FORT * 1e6)

st.sidebar.markdown("---")
st.sidebar.caption("Alertas de NET extremo")
st.sidebar.caption("Régua validada em 3 dias reais: ~3M parede segura no fio · >4M muito "
                   "forte · 6–8M brutal (05/06, IPO SpaceX). Recalibrar pela escala real.")
ALERTA_NET_1 = st.sidebar.slider("Alerta forte a partir de (M)", 2.0, 8.0, 4.0, 0.5,
    help="NET (compra ou venda) acima disso: fluxo muito forte, paredes sofrem.")
ALERTA_NET_2 = st.sidebar.slider("Alarme máximo a partir de (M)", 3.0, 12.0, 5.0, 0.5,
    help="Acima disso: fluxo brutal (tipo 05/06), paredes tendem a romper.")
NET_DIVISOR = st.sidebar.slider(
    "Divisor de escala do NET", 1.0, 20.0, 1.0, 0.5,
    help="Calibração vs Quantico (segunda, lado a lado): se o nosso NET operacional "
         "ainda rodar N× maior que o deles no mesmo minuto, ajuste o divisor até "
         "as escalas baterem. O NET operacional já é 0DTE + janela ±10%.")


def disparar_alertas_net(tk, net_dir, t1, t2, dia_iso):
    """Alerta de NET extremo (pedido do operador; calibrado nos dias 26/06, 09/06
    e 05/06-SpaceX). Popup (st.toast) no MÁXIMO 2 vezes por nível/ativo/dia; o
    banner persiste enquanto a condição durar. Retorna o html do banner ou ''.
    net_dir None (pregão fechado) → sem alerta (não há fluxo ao vivo)."""
    if net_dir is None:
        return ""
    mag = abs(num(net_dir))
    if mag < t1:
        return ""
    nivel = 2 if mag >= t2 else 1
    lado = "COMPRA" if net_dir > 0 else "VENDA"
    rot = "🚨 ALARME MÁXIMO" if nivel == 2 else "⚠ ALERTA FORTE"
    msg = (f"{rot} · {tk}: NET {fmt_usd(net_dir)} ({lado}) — fluxo "
           f"{'brutal: paredes tendem a ROMPER' if nivel == 2 else 'muito forte: paredes sob pressão'}. "
           f"Não vender trava contra essa direção.")
    chave = f"net_alert_{tk}_{nivel}_{dia_iso}"
    vezes = st.session_state.get(chave, 0)
    if vezes < 2:
        try:
            st.toast(msg, icon="🚨" if nivel == 2 else "⚠️")
        except Exception:
            pass
        st.session_state[chave] = vezes + 1
    cor = "#f0533f" if nivel == 2 else "#d9a441"
    fundo = "rgba(240,83,63,0.12)" if nivel == 2 else "rgba(217,164,65,0.08)"
    return (f'<div style="border:1px solid {cor};background:{fundo};'
            f'color:var(--ink);border-radius:8px;padding:10px 16px;margin:6px 0;'
            f'font-weight:600;font-size:0.9rem">{msg}</div>')

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
if supabase_ativo():
    st.sidebar.caption("🗄️ Registro Supabase: ativo (histórico persistente).")
else:
    st.sidebar.caption("🗄️ Registro Supabase: desligado (sem histórico entre dias).")
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

@st.cache_data(ttl=12, show_spinner=False)
def buscar_dados(ticker, nvenc=6):
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
    NVENC = max(1, int(nvenc))
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

@st.cache_data(ttl=3600, show_spinner=False)
def atr_diario_ref(ticker):
    """ATR(14) e fechamento do dia ANTERIOR (D-1), congelados — a régua do PS.
    Wilder RMA de 14 períodos sobre o True Range diário. Retorna
    (atr_ref, close_ancora) no espaço do próprio ETF (SPY/QQQ). Cache de 1h:
    o valor só muda quando vira o dia. Fallback silencioso → (None, None)."""
    try:
        h = yf.Ticker(ticker).history(period="40d", interval="1d", prepost=False)
        if h is None or h.empty or len(h) < 16:
            return None, None
        hi, lo, cl = h["High"], h["Low"], h["Close"]
        prev_close = cl.shift(1)
        tr = pd.concat([(hi - lo).abs(),
                        (hi - prev_close).abs(),
                        (lo - prev_close).abs()], axis=1).max(axis=1)
        # Wilder RMA(14) = EMA com alpha 1/14
        atr = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
        # D-1 = último DIA COMPLETO antes de hoje (por DATA, não por posição):
        # em pregão aberto a última linha é o dia parcial → D-1 é a anterior;
        # em fim de semana/pré-mercado a última linha JÁ é o último dia completo.
        # Usar iloc[-2] cegamente pegaria quinta em vez de sexta num sábado.
        hoje_ny = datetime.now(ZoneInfo("America/New_York")).date()
        mask_passado = [d.date() < hoje_ny for d in h.index]
        if not any(mask_passado):
            return None, None
        atr_p = atr[mask_passado]
        cl_p = cl[mask_passado]
        atr_ref = float(atr_p.iloc[-1]) if pd.notna(atr_p.iloc[-1]) else None
        close_ancora = float(cl_p.iloc[-1]) if pd.notna(cl_p.iloc[-1]) else None
        return atr_ref, close_ancora
    except Exception:
        return None, None

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

def calcular_gex(calls, puts, spot, venc_str, r, ponderar=False):
    """GEX por strike — dollar-gamma PLENO (Γ·OI·100·S²) somado sobre MÚLTIPLOS
    vencimentos (D5). Cada opção usa o T do seu próprio vencimento. Se ponderar=True,
    aplica peso 1/(1+dias/5) (0DTE dominante); se False (padrão), soma pura 'Total'
    como o menu Total·1M·5M do terminal Quantico — alinha ímã e magnitude com eles."""
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
            peso = (1.0 / (1.0 + dias / 5.0)) if ponderar else 1.0
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

def calcular_time_pressure(calls, puts, spot, venc_str, r, ponderar=False):
    """Time Pressure por strike (1.8): charm/dia × OI × 100 × S, somado sobre
    múltiplos vencimentos (D5) com T individual. peso condicional igual ao GEX.
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
            peso = (1.0 / (1.0 + dias / 5.0)) if ponderar else 1.0
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

def calcular_fluxo_institucional(calls, puts, spot, venc_str=None):
    """Classificação pelos terços do spread, com duas calibrações Quantico:
    — Descoberta 3 (FILTRO Q): exclui último/abertura > 2,0 ou < 0,05.
    — Descoberta 2 (NOTIONAL): notional do subjacente (volume·100·S) para a
      escala B dos painéis Institutional Flow Q (multi-vencimento, INTOCADO).
    — NET OPERACIONAL (v5.4, correção de escala): além do total multi-venc,
      calcula comp_op/vend_op APENAS do vencimento mais próximo (0DTE) e na
      janela 0,90–1,10·S. É esse NET que alimenta PS, alertas e régua — o
      Volume Imbalance da Quantico é intraday/0DTE; somar 6 vencimentos e
      ITM profundo inflava nosso NET 10–50× (QQQ chegou a $94,7M).
    bull = call comprada OU put vendida · bear = put comprada OU call vendida."""
    comp = vend = 0.0
    comp_op = vend_op = 0.0
    mapa = {}
    for df, tipo in ((calls, "call"), (puts, "put")):
        if df is None or df.empty:
            continue
        tem_venc = "venc_opt" in df.columns
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
            # este contrato entra no NET OPERACIONAL? (0DTE + janela ±10%)
            eh_0dte = (not tem_venc) or (venc_str is None) or \
                      (row.get("venc_opt") == venc_str)
            na_janela = (spot * 0.90 <= k <= spot * 1.10)
            operacional = eh_0dte and na_janela
            spread = ask - bid
            terco_baixo = bid + spread / 3.0
            terco_alto = ask - spread / 3.0
            premio = ultimo * vol * 100
            notional = vol * 100 * spot           # ← escala B (Descoberta 2)
            entrada = mapa.setdefault(k, {"bull": 0.0, "bear": 0.0, "ntl": 0.0})
            if ultimo >= terco_alto:      # negociado perto do ask = agressão compradora
                if tipo == "call":
                    comp += premio; entrada["bull"] += premio; entrada["ntl"] += notional
                    if operacional: comp_op += premio
                else:
                    vend += premio; entrada["bear"] += premio; entrada["ntl"] -= notional
                    if operacional: vend_op += premio
            elif ultimo <= terco_baixo:   # negociado perto do bid = agressão vendedora
                if tipo == "call":
                    vend += premio; entrada["bear"] += premio; entrada["ntl"] -= notional
                    if operacional: vend_op += premio
                else:
                    comp += premio; entrada["bull"] += premio; entrada["ntl"] += notional
                    if operacional: comp_op += premio
    linhas = [{"strike": k, "bull": v["bull"], "bear": v["bear"],
               "net": v["bull"] - v["bear"], "notional": v["ntl"]}
              for k, v in mapa.items()]
    if not linhas:
        return comp, vend, pd.DataFrame(
            columns=["strike", "bull", "bear", "net", "notional"]), comp_op, vend_op
    dff = pd.DataFrame(linhas).sort_values("strike").reset_index(drop=True)
    return comp, vend, dff, comp_op, vend_op

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


def _bell_placar():
    """Placar do PrumoQuant Bell (acertos/erros/breakeven). Lê do Supabase se
    configurado (histórico entre dias); senão, do session_state. NÃO inventa
    números — mostra zeros e explica enquanto não houver dados."""
    fonte_banco = False
    registros = []
    if supabase_ativo():
        linhas, err = supabase_select("bell_sinais", "?select=resultado")
        if not err:
            registros = linhas
            fonte_banco = True
    if not fonte_banco:
        try:
            registros = st.session_state.get("bell_registros", [])
        except Exception:
            registros = []
    win = sum(1 for r in registros if r.get("resultado") == "WIN")
    loss = sum(1 for r in registros if r.get("resultado") == "LOSS")
    be = sum(1 for r in registros if r.get("resultado") == "BE")
    total_dec = win + loss
    taxa = f"{100*win/total_dec:.0f}%" if total_dec else "—"
    if not registros:
        if supabase_ativo():
            nota = ("Banco conectado, ainda sem sinais gravados. O primeiro sinal é "
                    "congelado na próxima abertura (09:30 NY) e aparece aqui. A "
                    "avaliação de acerto (até 10h) entra no fechamento — registramos "
                    "TODOS os sinais, inclusive os que não deram certo.")
        else:
            nota = ("Registro persistente não configurado (SUPABASE_URL/KEY nos "
                    "Secrets). Sem isso o placar zera ao recarregar. Com o banco, o "
                    "sinal é congelado às 09:30 NY e avaliado até 10h00.")
    else:
        origem = "banco" if fonte_banco else "sessão"
        nota = (f"{total_dec} sinais avaliados · {be} no zero a zero (origem: {origem}). "
                f"Taxa considera só os que fecharam com resultado (exclui breakeven).")
    return {"win": win, "loss": loss, "be": be, "taxa": taxa, "nota": nota}


def _futuros_abertos(wd, tt):
    """Futuros de índice CME (ES/NQ): domingo 18:00 NY → sexta 17:00 NY,
    com pausa diária 17:00–18:00 NY nos dias úteis."""
    if wd == 5:                      # sábado: fechado
        return False
    if wd == 6:                      # domingo: abre 18:00
        return tt >= dtime(18, 0)
    if wd == 4:                      # sexta: fecha 17:00
        return tt < dtime(17, 0)
    if dtime(17, 0) <= tt < dtime(18, 0):   # seg–qui: pausa diária
        return False
    return True


def _proxima_abertura_txt(agora_ny):
    """Texto curto de quanto falta para a próxima abertura do pregão de ações."""
    d = agora_ny
    cand = d.replace(hour=9, minute=30, second=0, microsecond=0)
    if d.time() >= dtime(9, 30) or d.weekday() >= 5:
        cand = cand + timedelta(days=1)
    while cand.weekday() >= 5:
        cand = cand + timedelta(days=1)
    delta = cand - d
    horas = int(delta.total_seconds() // 3600)
    mins = int((delta.total_seconds() % 3600) // 60)
    if horas >= 24:
        return "abre em ~%dd %dh" % (horas // 24, horas % 24)
    return "abre em ~%dh %dmin" % (horas, mins)


def estado_janela_abertura(agora_ny):
    """Estado operacional do Direcionamento de Abertura (relógio de NY).
    Fases: 'ativo' (pregão aberto) · 'previa' (15 min antes) ·
    'referencia' (futuros abertos, ações fechadas) · 'aguardando' (tudo fechado).
    Só 'ativo' e 'previa' têm mostrar_sinal=True — nas outras o card não exibe
    gatilho/viés operacional, só referência."""
    wd, tt = agora_ny.weekday(), agora_ny.time()
    abertura, fechamento, prep_ini = dtime(9, 30), dtime(16, 0), dtime(9, 15)
    if wd < 5 and abertura <= tt < fechamento:
        return {"fase": "ativo", "mostrar_sinal": True,
                "rotulo": "pregão aberto", "nota": "", "countdown": ""}
    if wd < 5 and prep_ini <= tt < abertura:
        faltam = (datetime.combine(agora_ny.date(), abertura,
                                   tzinfo=agora_ny.tzinfo) - agora_ny)
        mins = max(0, int(faltam.total_seconds() // 60))
        return {"fase": "previa", "mostrar_sinal": True,
                "rotulo": "prévia de abertura",
                "nota": ("Prévia — faltam ~%d min para a abertura. O sinal só se "
                         "congela às 09:30 NY (10:30 BR); até lá os níveis ainda "
                         "podem mudar." % mins),
                "countdown": ""}
    if _futuros_abertos(wd, tt):
        return {"fase": "referencia", "mostrar_sinal": False,
                "rotulo": "futuros abertos · ações fechadas",
                "nota": ("Futuros negociando, mas o pregão de ações está fechado — "
                         "os níveis servem de referência, o sinal de abertura ainda "
                         "não é válido. Ele se congela na próxima abertura, 09:30 NY."),
                "countdown": _proxima_abertura_txt(agora_ny)}
    return {"fase": "aguardando", "mostrar_sinal": False,
            "rotulo": "mercado fechado",
            "nota": ("Mercado fechado. O Direcionamento de Abertura será congelado "
                     "na próxima abertura, 09:30 NY (10:30 BR)."),
            "countdown": _proxima_abertura_txt(agora_ny)}


# ----------------------------------------------------------------------------
# PS (PAD SPECIAL) — régua de exaustão para trava de crédito vertical (SPX)
# ----------------------------------------------------------------------------
# Duas trilhas por dia: PS Mínima (Put Credit Special, fundo) e PS Máxima
# (Call Credit Special, teto). Obrigatórios: preço testando a parede de Delta
# Hedging + risco de NET não-vetado. Bônus: VWAP na penúltima/última banda e ATR
# do dia consumido. O selo de risco vem do NET DIRECIONAL (limiares do operador).
# Marcas do dia não se apagam; guarda a melhor mínima e a melhor máxima; avalia
# acerto no fim do dia (definição A: segurou até o fechamento, tolerância ~0,1%).
PS_TOL_PAREDE = 0.0015   # 0,15% = "preço encostado na parede"
PS_TOL_ACERTO = 0.0010   # 0,10% = furo tolerado que ainda conta como acerto


def ps_selo_risco(net_dir, lado, thresholds):
    """Classifica o risco da PS pelo NET DIRECIONAL do momento.
    net_dir: NET com sinal (+ comprador líquido, − vendedor líquido).
    lado: 'teto' (Call Credit) ou 'fundo' (Put Credit).
    A pressão que importa é a que empurra CONTRA a trava (na direção da
    continuação): no teto, fluxo comprador; no fundo, fluxo vendedor."""
    t_conf, t_aten, t_forte = thresholds
    pressao = max(net_dir, 0.0) if lado == "teto" else max(-net_dir, 0.0)
    if pressao <= t_conf:
        return "confiavel", "confiável"
    if pressao <= t_aten:
        return "atencao", "atenção"
    if pressao <= t_forte:
        return "arriscada", "arriscada — pode furar ou colar"
    return "vetada", "vetada — rompimento provável"


def ps_vwap_banda(spot, vwap, sigma, lado):
    """Quantas bandas (σ) o preço está esticado na direção do lado. Bônus ≥ 2σ."""
    if vwap is None or sigma is None or sigma <= 0:
        return 0.0
    d = (spot - vwap) / sigma if lado == "teto" else (vwap - spot) / sigma
    return max(d, 0.0)


def ps_atr_consumido(spot, ancora_close, atr_ref, lado):
    """Fração do ATR do dia já consumida na direção do lado.
    ancora_close = fechamento de D-1; atr_ref = ATR(14) congelado de D-1."""
    if not atr_ref or atr_ref <= 0 or ancora_close is None:
        return 0.0
    if lado == "teto":
        return max(spot - ancora_close, 0.0) / atr_ref
    return max(ancora_close - spot, 0.0) / atr_ref


def avaliar_ps(lado, nivel, extremo_pos_marca):
    """Definição A de acerto. Teto: acertou se o preço não superou nivel*(1+TOL)
    desde a marca. Fundo: não perdeu nivel*(1−TOL). extremo_pos_marca = maior alta
    (teto) ou menor baixa (fundo) observada APÓS a marca. → 'WIN'|'LOSS'|'ABERTO'."""
    if extremo_pos_marca is None:
        return "ABERTO"
    if lado == "teto":
        return "LOSS" if extremo_pos_marca > nivel * (1 + PS_TOL_ACERTO) else "WIN"
    return "LOSS" if extremo_pos_marca < nivel * (1 - PS_TOL_ACERTO) else "WIN"


def detectar_ps(lado, spot, b_gex, vwap, sigma, net_dir,
                ancora_close, atr_ref, thresholds):
    """Detecta candidata PS no lado ('teto'/'fundo'). Obrigatórios: (1) parede de
    Delta Hedging na direção com preço encostado (±PS_TOL_PAREDE); (2) NET não
    'vetado'. Bônus: VWAP ≥ 2σ; ATR consumido ≥ 0,70. Retorna dict ou None."""
    parede = b_gex.get("maior_pos") if lado == "teto" else b_gex.get("maior_neg")
    if parede is None or abs(spot - parede) / spot > PS_TOL_PAREDE:
        return None
    if net_dir is None:            # pregão fechado → sem leitura de fluxo, PS aguarda
        return None
    nivel_risco, txt_risco = ps_selo_risco(net_dir, lado, thresholds)
    if nivel_risco == "vetada":
        return {"lado": lado, "nivel": parede, "acende": False,
                "risco": nivel_risco, "risco_txt": txt_risco,
                "forca": 0, "forca_txt": "vetada", "bonus": [], "net_dir": net_dir}
    bandas = ps_vwap_banda(spot, vwap, sigma, lado)
    atr_frac = ps_atr_consumido(spot, ancora_close, atr_ref, lado)
    bonus = []
    if bandas >= 2.0:
        bonus.append("VWAP %.1fσ" % bandas)
    if atr_frac >= 0.70:
        bonus.append("ATR %.0f%%" % (atr_frac * 100))
    forca = 2 + len(bonus)
    forca_txt = {2: "base", 3: "moderado", 4: "forte"}.get(forca, "base")
    return {"lado": lado, "nivel": parede, "acende": True,
            "risco": nivel_risco, "risco_txt": txt_risco,
            "forca": forca, "forca_txt": forca_txt, "bonus": bonus,
            "bandas": bandas, "atr_frac": atr_frac, "net_dir": net_dir}


def ps_registrar_marca(tk, ps, spot, hora_ny):
    """Guarda/atualiza a melhor marca do dia por lado (não apaga a anterior).
    'Melhor' = mais extrema (maior nível no teto, menor no fundo). As marcas ficam
    em session_state['ps_marcas'][tk][lado]. Guarda também o extremo do preço
    observado após a marca, para a avaliação de acerto no fim do dia."""
    if ps is None or not ps.get("acende"):
        return
    raiz = st.session_state.setdefault("ps_marcas", {})
    porativo = raiz.setdefault(tk, {})
    lado = ps["lado"]
    atual = porativo.get(lado)
    nova = (atual is None or
            (lado == "teto" and ps["nivel"] > atual["nivel"]) or
            (lado == "fundo" and ps["nivel"] < atual["nivel"]))
    if nova:
        porativo[lado] = {"nivel": ps["nivel"], "hora": hora_ny,
                          "forca_txt": ps["forca_txt"], "risco": ps["risco"],
                          "risco_txt": ps["risco_txt"], "bonus": list(ps["bonus"]),
                          "net_dir": ps["net_dir"], "extremo": spot}


def ps_atualizar_extremos(tk, spot):
    """A cada refresh, atualiza o extremo do preço após cada marca (para avaliar
    acerto). Teto guarda a MAIOR alta desde a marca; fundo a MENOR baixa."""
    raiz = st.session_state.get("ps_marcas", {})
    porativo = raiz.get(tk, {})
    for lado, m in porativo.items():
        if m.get("extremo") is None:
            m["extremo"] = spot
        elif lado == "teto":
            m["extremo"] = max(m["extremo"], spot)
        else:
            m["extremo"] = min(m["extremo"], spot)


def _forca_indicadores(b_gex, b_tp, b_fluxo, spot):
    """Conta o viés dos 3 indicadores. Cada indicador dá UM voto, na direção do
    seu ímã dominante: compara a distância do ímã de alta (acima) com a do ímã de
    baixa (abaixo) — vence o mais próximo do preço (o que puxa com mais força
    agora). Retorna (alta, baixa) somando no máximo 3."""
    alta = baixa = 0
    for b in (b_gex, b_tp, b_fluxo):
        mp, mn = b.get("maior_pos"), b.get("maior_neg")
        d_alta = (mp - spot) if (mp is not None and mp > spot) else None
        d_baixa = (spot - mn) if (mn is not None and mn < spot) else None
        if d_alta is not None and d_baixa is not None:
            # os dois existem: vota no mais PRÓXIMO (puxão mais forte agora)
            if d_alta <= d_baixa:
                alta += 1
            else:
                baixa += 1
        elif d_alta is not None:
            alta += 1
        elif d_baixa is not None:
            baixa += 1
    return alta, baixa


def direcionamento_abertura(tk, spot, setup, b_gex, b_tp, b_fluxo, comp, vend,
                            veto_ativo=False, r_fut=None, nome_fut=None):
    """Retorna um dict com as linhas do sinal, SEM emoji e SEM cor — o texto é
    monocromático como o Striking Bell. Formato: {'veto':bool, 'linhas':[...],
    'contexto':str}. Cada linha: (acao, nivel, resto). O quadro clean é montado
    na camada de exibição."""
    mp = b_gex.get("maior_pos"); mn = b_gex.get("maior_neg")
    pn = b_gex.get("primeira_neg"); pp = b_gex.get("primeira_pos")
    alta, baixa = _forca_indicadores(b_gex, b_tp, b_fluxo, spot)
    net = comp - vend

    if tk == "QQQ":
        exec_fut, micro, PTS_FIXO = "NQ", "MNQ", 50
    else:
        exec_fut, micro, PTS_FIXO = "ES", "MES", 7

    if veto_ativo:
        return {"tk": tk, "exec": exec_fut, "veto": True, "vies_dir": None,
                "linhas": [], "contexto": "",
                "veto_txt": (f"Operação em {tk} proibida agora — o QQQ aponta baixa "
                             f"sem o SPY confirmar. Sem a permissão do SPY, não se "
                             f"entra no {exec_fut}.")}

    nivel_compra = mn if mn is not None else pn
    nivel_venda = mp if mp is not None else pp
    linhas = []
    if nivel_compra is not None:
        linhas.append(("Comprar", f"{nivel_compra:.0f}",
                       f"no {exec_fut}/{micro}, stop e alvo de {PTS_FIXO} pontos."))
    if nivel_venda is not None and (nivel_compra is None or nivel_venda != nivel_compra):
        linhas.append(("Vender", f"{nivel_venda:.0f}",
                       f"no {exec_fut}/{micro}, stop e alvo de {PTS_FIXO} pontos."))
    if not linhas:
        linhas.append(("Aguardar", "—",
                       f"sem níveis-chave claros no {tk} — esperar o preço definir "
                       f"os muros antes de entrar."))

    # --- VIÉS DIRECIONAL DE ABERTURA (comprado/vendido, sempre dá direção) ---
    # Placar de 4 votos: 3 indicadores (alta/baixa) + o fluxo agressor.
    votos_alta = alta + (1 if net > 0 else 0)
    votos_baixa = baixa + (1 if net < 0 else 0)
    if votos_alta > votos_baixa:
        direcao, votos = "COMPRADO", votos_alta
    elif votos_baixa > votos_alta:
        direcao, votos = "VENDIDO", votos_baixa
    else:
        # empate: desempata pelo fluxo; se fluxo também neutro, usa o gamma
        if net > 0:
            direcao, votos = "COMPRADO", votos_alta
        elif net < 0:
            direcao, votos = "VENDIDO", votos_baixa
        else:
            direcao, votos = ("COMPRADO", votos_alta) if alta >= baixa else ("VENDIDO", votos_baixa)
    # força: quantos dos 4 votos concordam
    if votos >= 4:
        forca = "forte"
    elif votos == 3:
        forca = "moderado"
    else:
        forca = "fraco"
    # AÇÃO DE ABERTURA (regra do operador): 3/4 ou mais = ENTRAR IMEDIATO ao abrir;
    # 2/4 ou menos = AGUARDAR e usar os gatilhos condicionais.
    entrar_imediato = votos >= 3
    acao_abertura = ("ENTRAR " + direcao) if entrar_imediato else "AGUARDAR"
    # detecta contradição indicadores × fluxo (avisa quando o sinal é confuso)
    contradiz = ((alta > baixa and net < 0) or (baixa > alta and net > 0))

    fluxo_txt = ("comprador" if net > 0 else "vendedor") if net != 0 else "neutro"
    vies_dir = {"direcao": direcao, "forca": forca, "votos": votos,
                "contradiz": contradiz, "entrar_imediato": entrar_imediato,
                "acao_abertura": acao_abertura}
    contexto = (f"Placar: {votos}/4 votos {'(entra imediato)' if entrar_imediato else '(fraco — aguardar)'}. "
                f"Indicadores {alta}/3 alta · {baixa}/3 baixa · fluxo {fluxo_txt}.")
    return {"tk": tk, "exec": exec_fut, "veto": False, "vies_dir": vies_dir,
            "linhas": linhas, "contexto": contexto, "veto_txt": ""}

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
def pregao_acoes_aberto(t_ny):
    """True só quando o pregão de AÇÕES está negociando ao vivo (seg–sex 9:30–16:00
    NY). É a condição para o NET operacional refletir fluxo real: fora disso o campo
    'volume' da Tradier traz o acumulado da última sessão inteira, que não é fluxo
    do momento (foi o que gerou o NET fantasma de $24M num domingo)."""
    return t_ny.weekday() < 5 and dtime(9, 30) <= t_ny.time() < dtime(16, 0)


def selo_mercado(t_ny):
    wd, tt = t_ny.weekday(), t_ny.time()
    if wd < 5 and dtime(9, 30) <= tt < dtime(16, 0):
        return '<span class="selo selo-aberto">MERCADO ABERTO</span>'
    if wd < 5 and dtime(4, 0) <= tt < dtime(9, 30):
        return '<span class="selo selo-pre">PRÉ-MERCADO</span>'
    return '<span class="selo selo-fechado">MERCADO FECHADO</span>'

def regua_fluxo_html(comp, vend, fluxo_df=None, net_op=None):
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
    # Linha inferior: NET OPERACIONAL em destaque (0DTE+janela — comparável ao
    # Volume Imbalance da Quantico; é o que o PS e os alertas usam), topo do
    # strike ao lado, e o total multi-venc discreto no fim.
    partes = []
    if net_op is not None:
        cor_op = "verde" if net_op >= 0 else "vermelho"
        partes.append(f'<span class="{cor_op}"><b>NET op: {fmt_usd(net_op)}</b></span>')
    else:
        partes.append('<span style="color:#6b7280"><b>NET op: — (pregão fechado)</b></span>')
    if net_top is not None:
        partes.append(f'<span class="{cor_net}">topo: {fmt_usd(net_top)}</span>')
    partes.append(f'<span style="color:#6b7280">multi-venc {fmt_usd(net_dia)}</span>')
    net_html = " · ".join(partes)
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
                             marker_color=cores, width=0.82))
        fig.add_hline(y=spot, line_dash="dash", line_color="#9ca3af", line_width=1)
    else:
        fig.add_trace(go.Bar(x=df["strike"], y=df[col], marker_color=cores,
                             width=0.82))
        fig.add_vline(x=spot, line_dash="dash", line_color="#9ca3af", line_width=1)
    fig.update_traces(marker_line_width=0)
    fig.update_layout(template="plotly_dark",
                      paper_bgcolor="#0d1117", plot_bgcolor="#0d1117",
                      margin=dict(l=4, r=4, t=4, b=4), height=altura,
                      showlegend=False, bargap=0.15,
                      font=dict(family="ui-monospace, 'Cascadia Code', monospace",
                                size=10, color="#8b98a5"),
                      xaxis=dict(gridcolor="#161d26", zerolinecolor="#232d38",
                                 tickfont=dict(size=9)),
                      yaxis=dict(gridcolor="#161d26", zerolinecolor="#232d38",
                                 tickfont=dict(size=9)))
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
agora_t = agora_ny.time()
# Três ritmos de atualização (NY):
#  - MIOLO da abertura (9h29–9h35): 15s — muros mudam rápido, sinal precisa ser fresco
#  - Janela quente (9h00–9h45): 30s
#  - Resto do pregão: 60s
miolo_abertura = dtime(9, 29) <= agora_t <= dtime(9, 35)
janela_quente = dtime(9, 0) <= agora_t <= dtime(9, 45)
if miolo_abertura:
    intervalo_ms = 15000
elif janela_quente:
    intervalo_ms = 30000
else:
    intervalo_ms = 60000
st_autorefresh(interval=intervalo_ms, key="pq_refresh")

tickers_para_rodar = ["SPY", "QQQ"] if MODO_VISAO == "SPY + QQQ lado a lado" else [TICKER_UNICO]
r_global = taxa_juros_automatica() if USAR_R_AUTO else TAXA_MANUAL
origem_r = "^IRX automático" if (USAR_R_AUTO and r_global is not None) else "manual"
if r_global is None:
    r_global = TAXA_MANUAL

# --- Coleta e derivação por ativo -------------------------------------------
dados_ativos, falhas = {}, {}
for tk in tickers_para_rodar:
    bruto = buscar_dados(tk, NVENC_UI)
    if bruto.get("erro"):
        falhas[tk] = bruto["erro"]
        continue
    spot, hist = bruto["spot"], bruto["hist"]
    calls, puts, venc = bruto["calls"], bruto["puts"], bruto["venc"]
    if spot is None or venc is None or calls is None or calls.empty:
        falhas[tk] = " · ".join(bruto["erros"]) if bruto["erros"] else \
            "cadeia de opções indisponível no momento"
        continue

    por_strike, cw, pw, flip, dominio, v_hoje = calcular_gex(calls, puts, spot, venc, r_global, PESO_PONDERADO)
    b_gex = identificar_barras_chave(por_strike, spot, "gex")
    tp_df = calcular_time_pressure(calls, puts, spot, venc, r_global, PESO_PONDERADO)
    b_tp = identificar_barras_chave(tp_df, spot, "tp")
    comp, vend, fluxo_df, comp_op, vend_op = calcular_fluxo_institucional(
        calls, puts, spot, venc)
    b_fluxo = identificar_barras_chave(fluxo_df, spot, "notional")

    vwap_val = sigma_val = None
    if hist is not None and not hist.empty:
        _, vwap_ser, sigma_ser = calcular_vwap(hist)
        if not vwap_ser.empty and pd.notna(vwap_ser.iloc[-1]):
            vwap_val = float(vwap_ser.iloc[-1])
            sigma_val = float(sigma_ser.iloc[-1]) if pd.notna(sigma_ser.iloc[-1]) else 0.0

    setup = detectar_setup(b_gex, spot, flip, dominio, cw, pw)

    # --- PS (Pad Special): régua de exaustão para trava de crédito -----------
    # NET OPERACIONAL (v5.5): só vale com o PREGÃO DE AÇÕES ABERTO. Fora dele, o
    # campo 'volume' da Tradier é o acumulado da última sessão inteira — não é
    # fluxo do momento (gerava NET fantasma tipo $24M num domingo). Fechado → None.
    if pregao_acoes_aberto(agora_ny):
        net_dir_ps = (comp_op - vend_op) / max(NET_DIVISOR, 1.0)
    else:
        net_dir_ps = None
    atr_ref, ancora_close = atr_diario_ref(tk)   # ATR(14) e close de D-1 (congelados)
    ps_teto = detectar_ps("teto", spot, b_gex, vwap_val, sigma_val,
                          net_dir_ps, ancora_close, atr_ref, PS_THRESHOLDS)
    ps_fundo = detectar_ps("fundo", spot, b_gex, vwap_val, sigma_val,
                           net_dir_ps, ancora_close, atr_ref, PS_THRESHOLDS)
    # marca as duas trilhas do dia (não apaga a anterior) e atualiza extremos
    _hora_ny = agora_ny.strftime("%H:%M")
    ps_registrar_marca(tk, ps_teto, spot, _hora_ny)
    ps_registrar_marca(tk, ps_fundo, spot, _hora_ny)
    ps_atualizar_extremos(tk, spot)
    # Persistência entre dias (Fase 2.3): grava a marca no Supabase (silencioso
    # se o banco não estiver configurado). ×10 para o nível SPX quando é SPY.
    _dia_iso = agora_ny.strftime("%Y-%m-%d")
    _fx_spx = (lambda v: v * 10.0) if tk == "SPY" else (lambda v: v)
    if ps_teto and ps_teto.get("acende"):
        registrar_ps_marca_banco(tk, ps_teto, _hora_ny, _dia_iso, _fx_spx(ps_teto["nivel"]))
    if ps_fundo and ps_fundo.get("acende"):
        registrar_ps_marca_banco(tk, ps_fundo, _hora_ny, _dia_iso, _fx_spx(ps_fundo["nivel"]))

    dados_ativos[tk] = dict(spot=spot, prev=bruto["prev"], hist=hist, venc=venc,
                            fonte=bruto["fonte"], por_strike=por_strike, cw=cw,
                            pw=pw, flip=flip, dominio=dominio, dte0=v_hoje,
                            b_gex=b_gex, tp_df=tp_df, b_tp=b_tp, comp=comp,
                            vend=vend, fluxo_df=fluxo_df, b_fluxo=b_fluxo,
                            vwap=vwap_val, sigma=sigma_val, setup=setup,
                            net_dir=net_dir_ps, atr_ref=atr_ref,
                            ancora_close=ancora_close, ps_teto=ps_teto,
                            ps_fundo=ps_fundo)

# --- Alertas de NET extremo (>4M muito forte · 6–8M brutal, dia 05/06) -------
_dia_alerta = agora_ny.strftime("%Y-%m-%d")
alertas_net_html = ""
for _tk_a in dados_ativos:
    alertas_net_html += disparar_alertas_net(
        _tk_a, dados_ativos[_tk_a]["net_dir"],
        ALERTA_NET_1 * 1e6, ALERTA_NET_2 * 1e6, _dia_alerta)

# --- Cabeçalho ---------------------------------------------------------------
fonte_geral = "● Tempo real Tradier" if dados_ativos and all(
    d["fonte"].startswith("Tradier") for d in dados_ativos.values()) else "● Fallback yfinance (~15 min)"
cor_fonte = "#22c55e" if fonte_geral.startswith("● Tempo") else "#fbbf24"
st.markdown(f"""
<div class="pq-header">
    <div>
        <span class="pq-logo">Prumo<span class="fio">Quant</span>
        <small style="font-size:0.8rem;color:#6b7280;">v5.5</small></span>
        <span class="pq-sub">Fluxo de Opções · Delta-Hedging · Estudo</span>
    </div>
    <div class="pq-meta">
        {selo_mercado(agora_ny)}<br>
        <b>NY:</b> {agora_ny.strftime('%H:%M:%S')} · <b>BR:</b> {agora_br.strftime('%H:%M')} ·
        r: {r_global*100:.2f}% ({origem_r}) · ⏱ {intervalo_ms//1000}s<br>
        <span style='color:{cor_fonte}'>{fonte_geral}</span>
    </div>
</div>
""", unsafe_allow_html=True)

# Banner de NET extremo — persiste enquanto a condição durar (topo, sempre visível)
if alertas_net_html:
    st.markdown(alertas_net_html, unsafe_allow_html=True)

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
nomes_abas = ["Delta-Hedging", "Fluxo", "Time Pressure", "Abertura",
              "PS", "SPY×QQQ", "Níveis"]
if MOSTRAR_TV:
    nomes_abas.append("Gráfico TV")
abas = st.tabs(nomes_abas)
ativos_ok = [t for t in tickers_para_rodar if t in dados_ativos]

# ============================== ABA · DELTA-HEDGING (grid) ====================
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

        # Volume Imbalance ABAIXO do trio de gráficos
        st.markdown(regua_fluxo_html(d["comp"], d["vend"], d["fluxo_df"], d["net_dir"]),
                    unsafe_allow_html=True)


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
        st.markdown("---")

# ============================== ABA · FLUXO ===================================
with abas[1]:
    st.caption("Volume Imbalance Flow: prêmio agressor por strike. Verde (direita) = "
               "calls compradas / puts vendidas; vermelho (esquerda) = puts compradas / "
               "calls vendidas. Linhas: branca = spot · azul = ímã (maior+) · roxa = muros.")
    for tk in ativos_ok:
        d = dados_ativos[tk]
        st.markdown(regua_fluxo_html(d["comp"], d["vend"], d["fluxo_df"], d["net_dir"]), unsafe_allow_html=True)
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

# ============================== ABA · TIME PRESSURE ==========================
with abas[2]:
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

# ============================== ABA · ABERTURA (setups) =======================
with abas[3]:
    st.caption("S6 é o mais assertivo · S2 é o mais perigoso e EXIGE confirmação do "
               "SPY · S5 se evita. PrumoQuant Bell (2.3): em construção — sinal "
               "congelado às 9h29:59 NY e avaliado até 10h00 com MAE/MFE.")

    # --- JANELA OPERACIONAL: só emite sinal na abertura/prévia ---------------
    janela = estado_janela_abertura(agora_ny)

    # --- DIRECIONAMENTO DE ABERTURA — quadro clean, monocromático ---
    dias_sem = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
    dia_txt = f"{dias_sem[agora_ny.weekday()]}, {agora_ny.strftime('%d/%m/%Y')}"
    aberto = (janela["fase"] == "ativo")
    meta = (f"{dia_txt} &nbsp;·&nbsp; {agora_ny.strftime('%H:%M')} NY / "
            f"{agora_br.strftime('%H:%M')} BR &nbsp;·&nbsp; {janela['rotulo']}")

    veto_geral = ("SPY" in dados_ativos and "QQQ" in dados_ativos and
                  dados_ativos["QQQ"]["setup"] and
                  dados_ativos["QQQ"]["setup"]["codigo"] == "S2" and
                  (not dados_ativos["SPY"]["setup"] or
                   dados_ativos["SPY"]["setup"]["codigo"] != "S2"))
    ordem_dir = [t for t in ("QQQ", "SPY") if t in ativos_ok]

    corpo = ""
    # Só monta gatilhos/viés quando o sinal é operacionalmente válido
    # (fase 'ativo' ou 'previa'). Fora disso o loop não roda e o card
    # exibe apenas o bloco de estado (AGUARDANDO / referência) mais abaixo.
    for tk in (ordem_dir if janela["mostrar_sinal"] else []):
        d = dados_ativos[tk]
        veto_tk = veto_geral and tk == "QQQ"
        _nf, _pf, _rf = razao_futuro(tk, d["spot"])
        sig = direcionamento_abertura(tk, d["spot"], d["setup"], d["b_gex"],
                                      d["b_tp"], d["b_fluxo"], d["comp"], d["vend"],
                                      veto_ativo=veto_tk, r_fut=_rf, nome_fut=_nf)
        # Registro persistente do Bell (Fase 2.3): congela o sinal no banco na
        # abertura (uma vez por dia). Silencioso se o banco não estiver ligado.
        if janela["fase"] == "ativo":
            registrar_bell_sinal_banco(tk, sig, agora_ny.strftime("%Y-%m-%d"),
                                       agora_ny.strftime("%H:%M"))
        corpo += f'<div class="sinal-titulo" style="margin-top:14px">{tk} · {sig["exec"]}</div>'
        if sig["veto"]:
            corpo += f'<div class="sinal-linha sinal-veto">{sig["veto_txt"]}</div>'
            continue
        # AÇÃO DE ABERTURA EM DESTAQUE MÁXIMO (a resposta no minuto 0)
        vd = sig.get("vies_dir")
        if vd:
            if vd["entrar_imediato"]:
                cor_vies = "var(--up)" if vd["direcao"] == "COMPRADO" else "var(--down)"
                corpo += (f'<div class="acao-abertura" style="border-color:{cor_vies}">'
                          f'<span class="acao-rot">Na abertura:</span> '
                          f'<span class="acao-big" style="color:{cor_vies}">{vd["acao_abertura"]}</span> '
                          f'<span class="vies-forca">({vd["votos"]}/4 · {vd["forca"]})</span></div>')
                aviso_c = ('<div class="sinal-nota">⚠ Indicadores e fluxo discordam — '
                           'sinal imediato menos confiável, confirme o primeiro minuto.</div>'
                           if vd["contradiz"] else "")
                corpo += aviso_c
            else:
                corpo += (f'<div class="acao-abertura" style="border-color:var(--ink-3)">'
                          f'<span class="acao-rot">Na abertura:</span> '
                          f'<span class="acao-big" style="color:var(--ink-2)">AGUARDAR</span> '
                          f'<span class="vies-forca">(só {vd["votos"]}/4 — sinal fraco). '
                          f'Espere o preço tocar um gatilho abaixo.</span></div>')
        for acao, nivel, resto in sig["linhas"]:
            if nivel == "—":
                corpo += f'<div class="sinal-linha">{resto}</div>'
            else:
                corpo += (f'<div class="sinal-linha"><span class="acao">{acao}</span> '
                          f'quando o {tk} atingir e se manter em '
                          f'<span class="sinal-nivel">{nivel}</span> — {resto}</div>')
        corpo += f'<div class="sinal-ctx">{sig["contexto"]}</div>'

    # Bloco de ESTADO fora da janela operacional (aguardando / referência):
    # em vez de gatilho, mostra "AGUARDANDO" + contagem regressiva + nota.
    if not janela["mostrar_sinal"]:
        cd = (" · %s" % janela["countdown"]) if janela["countdown"] else ""
        corpo = (
            '<div class="acao-abertura" style="border-color:var(--ink-3)">'
            '<span class="acao-rot">Na abertura:</span> '
            '<span class="acao-big" style="color:var(--ink-2)">AGUARDANDO</span> '
            '<span class="vies-forca">(%s%s)</span></div>' % (janela["rotulo"], cd))

    # Nota de rodapé conforme a fase.
    if janela["mostrar_sinal"]:
        aviso_fechado = ("" if janela["fase"] == "ativo" else
                         '<div class="sinal-nota">%s</div>' % janela["nota"])
    else:
        aviso_fechado = '<div class="sinal-nota">%s</div>' % janela["nota"]

    st.markdown(
        f'<div class="sinal-box">'
        f'<div class="sinal-titulo">Direcionamento de abertura</div>'
        f'<div class="sinal-meta">{meta}</div>'
        f'{corpo}'
        f'{aviso_fechado}'
        f'<div class="sinal-nota">Leitura condicional de estudo — não é recomendação. '
        f'Sem percentual de confiança (isso exige histórico de sinais, Fase 2.3). '
        f'A decisão e o risco são do operador.</div>'
        f'</div>', unsafe_allow_html=True)

    # --- PLACAR DO PRUMOQUANT BELL (acertos / erros / breakeven) ---
    placar = _bell_placar()
    st.markdown(
        f'<div class="sinal-titulo" style="margin-top:16px">PrumoQuant Bell · histórico</div>'
        f'<div class="placar">'
        f'<div class="cel"><div class="n verde">{placar["win"]}</div><div class="l">Acertos</div></div>'
        f'<div class="cel"><div class="n vermelho">{placar["loss"]}</div><div class="l">Erros</div></div>'
        f'<div class="cel"><div class="n">{placar["be"]}</div><div class="l">Breakeven</div></div>'
        f'<div class="cel"><div class="n">{placar["taxa"]}</div><div class="l">Taxa de acerto</div></div>'
        f'</div>'
        f'<div class="sinal-nota">{placar["nota"]}</div>',
        unsafe_allow_html=True)
    st.markdown("---")

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

# ============================== ABA · PS (PAD SPECIAL) =======================
with abas[4]:
    st.caption("PS · Pad Special — régua de exaustão para trava de crédito vertical "
               "(execução em SPX; leitura no SPY convertido ×10). Duas trilhas por dia: "
               "PS Mínima (Put Credit) no fundo e PS Máxima (Call Credit) no teto. "
               "Obrigatório: preço encostado na parede de Delta Hedging. Bônus: VWAP na "
               "penúltima/última banda + ATR do dia consumido. O selo de risco vem do NET "
               "direcional do momento. As marcas do dia não se apagam e são avaliadas no "
               "fechamento. Ferramenta de ESTUDO — não é recomendação.")

    # Aplicação dupla das zonas PS: mesma zona serve a dois instrumentos.
    st.markdown(
        '<div class="setup-linha" style="border-color:var(--accent)">'
        '<b>Zonas PS = zonas extremas de reversão.</b> A mesma leitura serve a dois usos: '
        '(1) <b>trava de crédito</b> (vender prêmio contra a continuação — tese "não passa daqui"); '
        '(2) <b>scalping profundo</b> (entrar na reversão — comprado no fundo, vendido no teto — '
        'com stop curto). A zona é a mesma; muda o instrumento. O selo de risco vale para os dois: '
        'risco alto = reversão menos provável, cuidado nos dois usos.</div>',
        unsafe_allow_html=True)

    # Aviso de foco: para o PS de SPX, o SPY precisa estar carregado.
    if "SPY" not in dados_ativos:
        st.markdown(
            '<div class="setup-linha alerta-vermelho">Para o PS de <b>SPX</b>, ative o '
            '<b>SPY</b> na barra lateral (modo "SPY + QQQ lado a lado", ou "Um ativo" = SPY). '
            'O PS lê o SPY e converte ×10 para o SPX.</div>', unsafe_allow_html=True)

    _RISCO_COR = {"confiavel": "var(--up)", "atencao": "var(--accent)",
                  "arriscada": "var(--down)", "vetada": "var(--ink-3)"}

    def _bloco_ps_ativo(tk):
        d = dados_ativos.get(tk)
        if not d:
            return
        spx_fator = 10.0  # SPX ≈ SPY × 10 (execução da trava é em SPX)
        conv = (lambda v: v * spx_fator) if tk == "SPY" else (lambda v: v)
        rot_exec = "SPX" if tk == "SPY" else tk
        # cabeçalho do ativo
        atr_txt = ("ATR(14) D-1: %.2f · âncora %.2f" % (d["atr_ref"], d["ancora_close"])
                   if d["atr_ref"] and d["ancora_close"] else "ATR indisponível")
        net = d["net_dir"]
        if net is None:
            net_txt = "NET: — (pregão fechado, sem fluxo ao vivo)"
        else:
            net_txt = ("NET agora: %s (%s)" % (fmt_usd(net),
                       "comprador" if net > 0 else "vendedor" if net < 0 else "neutro"))
        st.markdown("#### %s — leitura para %s &nbsp;"
                    "<span style='font-size:0.72rem;color:#8b98a5'>%s · %s</span>"
                    % (tk, rot_exec, atr_txt, net_txt), unsafe_allow_html=True)

        # duas trilhas: estado AO VIVO (o que está acontecendo neste refresh)
        for lado, ps, titulo, trava in (
                ("teto", d["ps_teto"], "PS Máxima (teto)", "Call Credit Special"),
                ("fundo", d["ps_fundo"], "PS Mínima (fundo)", "Put Credit Special")):
            if ps is None:
                st.markdown('<div class="setup-linha">%s · <b>%s</b> — preço ainda não '
                            'está testando a parede deste lado. Aguardando.</div>'
                            % (titulo, trava), unsafe_allow_html=True)
                continue
            cor = _RISCO_COR.get(ps["risco"], "var(--ink-2)")
            niv_txt = ("%.2f" % ps["nivel"] if tk != "SPY"
                       else "%.2f (SPX ~%.0f)" % (ps["nivel"], conv(ps["nivel"])))
            if not ps["acende"]:
                st.markdown(
                    '<div class="setup-linha" style="border-color:%s">%s · <b>%s</b> '
                    'em <b>%s</b> — <span style="color:%s">%s</span>. '
                    'Fluxo forte demais na direção da continuação; a parede provavelmente '
                    'cede. Não vender a trava contra isso.</div>'
                    % (cor, titulo, trava, niv_txt, cor, ps["risco_txt"]),
                    unsafe_allow_html=True)
                continue
            bonus_txt = (" · " + " · ".join(ps["bonus"])) if ps["bonus"] else ""
            st.markdown(
                '<div class="setup-linha" style="border-color:%s">%s · <b>%s</b> '
                'em <b>%s</b> — força <b>%s</b> (%d/4)%s · risco '
                '<span style="color:%s"><b>%s</b></span>.</div>'
                % (cor, titulo, trava, niv_txt, ps["forca_txt"], ps["forca"],
                   bonus_txt, cor, ps["risco_txt"]),
                unsafe_allow_html=True)

        # marcas do dia (persistentes) + avaliação de acerto
        marcas = st.session_state.get("ps_marcas", {}).get(tk, {})
        if marcas:
            st.markdown('<div class="sinal-titulo" style="margin-top:10px">'
                        'Marcas do dia · avaliação</div>', unsafe_allow_html=True)
            for lado, titulo in (("teto", "PS Máxima"), ("fundo", "PS Mínima")):
                m = marcas.get(lado)
                if not m:
                    continue
                res = avaliar_ps(lado, m["nivel"], m.get("extremo"))
                aberto = (agora_ny.weekday() < 5 and
                          dtime(9, 30) <= agora_ny.time() < dtime(16, 0))
                res_txt = {"WIN": "segurou ✓", "LOSS": "furou ✗",
                           "ABERTO": "em aberto"}.get(res, res)
                if aberto and res == "WIN":
                    res_txt = "segurando (dia em curso)"
                cor_res = {"WIN": "var(--up)", "LOSS": "var(--down)",
                           "ABERTO": "var(--ink-2)"}.get(res, "var(--ink-2)")
                niv_txt = ("%.2f" % m["nivel"] if tk != "SPY"
                           else "%.2f (SPX ~%.0f)" % (m["nivel"], conv(m["nivel"])))
                st.markdown(
                    '<div class="sinal-linha" style="font-size:0.9rem">'
                    '<b>%s</b> marcada %s em <b>%s</b> · força %s · risco na marca: %s · '
                    'resultado: <span style="color:%s"><b>%s</b></span></div>'
                    % (titulo, m["hora"], niv_txt, m["forca_txt"], m["risco_txt"],
                       cor_res, res_txt), unsafe_allow_html=True)
            st.caption("Definição de acerto: a marca 'segurou' se o preço não superou o "
                       "nível além de ~0,1% até o fechamento. As marcas não se apagam; o "
                       "histórico entre dias entra com o registro persistente (Fase 2.3).")
        st.markdown("---")

    for tk in [t for t in ("SPY", "QQQ") if t in dados_ativos]:
        _bloco_ps_ativo(tk)
    if not any(t in dados_ativos for t in ("SPY", "QQQ")):
        st.info("Sem dados de SPY/QQQ no momento para calcular o PS.")

    # --- HISTÓRICO PERSISTENTE DO PS (Supabase · Fase 2.3) ---
    st.markdown('<div class="sinal-titulo" style="margin-top:18px">'
                'PS · histórico persistente (entre dias)</div>', unsafe_allow_html=True)
    if supabase_ativo():
        linhas_ps, err_ps = supabase_select("ps_marcas", "?select=resultado,lado")
        if err_ps:
            st.caption("Banco configurado, mas a leitura falhou agora (%s). O painel "
                       "segue normal; as marcas do dia estão acima." % err_ps)
        else:
            sp = _stats_do_historico(linhas_ps)
            st.markdown(
                '<div class="placar">'
                '<div class="cel"><div class="n verde">%d</div><div class="l">Segurou</div></div>'
                '<div class="cel"><div class="n vermelho">%d</div><div class="l">Furou</div></div>'
                '<div class="cel"><div class="n">%d</div><div class="l">Total marcas</div></div>'
                '<div class="cel"><div class="n">%s</div><div class="l">Taxa de acerto</div></div>'
                '</div>' % (sp["win"], sp["loss"], sp["total"], sp["taxa"]),
                unsafe_allow_html=True)
            st.caption("Acumulado de todas as marcas PS gravadas no banco, dia após dia. "
                       "A avaliação de acerto/erro é feita no fechamento de cada dia.")
    else:
        st.caption("Registro persistente não configurado. Para o PS acumular histórico "
                   "entre dias (e não zerar ao recarregar), adicione SUPABASE_URL e "
                   "SUPABASE_KEY nos Secrets do Streamlit. Sem isso, o painel funciona "
                   "igual; só não guarda histórico entre sessões.")

# ============================== ABA · SPY×QQQ ================================
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

# ============================== ABA · NÍVEIS ================================
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

# ============================== ABA · GRÁFICO TV =============================
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
