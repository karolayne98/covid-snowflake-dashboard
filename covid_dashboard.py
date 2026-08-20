"""
Dashboard COVID-19 — Streamlit + Snowflake
Atividade Prática — Ciência de Dados (UNICAMP)
Professor: Francisco Fambrini

Dataset: Our World in Data (OWID) — owid/covid-19-data
Autor: Karolayne Ramos
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from snowflake.snowpark import Session
from cryptography.hazmat.primitives import serialization
from datetime import datetime

# ----------------------------------------------------------------------------
# Configuração da página
# ----------------------------------------------------------------------------
st.set_page_config(
    page_title="Dashboard COVID-19 | OWID + Snowflake",
    page_icon="🦠",
    layout="wide",
)

# ----------------------------------------------------------------------------
# Constantes
# ----------------------------------------------------------------------------
CSV_URL = "https://raw.githubusercontent.com/owid/covid-19-data/master/public/data/owid-covid-data.csv"

# Países analisados nesta atividade (fique à vontade para trocar a lista)
PAISES = ["Brazil", "United States", "India", "Germany", "South Africa", "Japan"]
DATA_INICIO = "2021-01-01"

TABLE_NAME = "COVID_OWID"

# ----------------------------------------------------------------------------
# Parâmetros de conexão com o Snowflake (lidos de st.secrets)
#
# Usamos autenticação por par de chaves (RSA) em vez de usuário+senha, porque
# contas novas do Snowflake exigem MFA para login por senha, o que trava
# conexões automatizadas como esta. Gere as chaves rodando `generate_keys.py`
# uma vez (veja o GUIA.md) antes de usar o dashboard.
# ----------------------------------------------------------------------------
connection_parameters = {
    "user": st.secrets["snowflake"]["user"],
    "account": st.secrets["snowflake"]["account"],
    "warehouse": st.secrets["snowflake"]["warehouse"],
    "database": "TEST_DB",
    "schema": "PUBLIC",
    "role": st.secrets["snowflake"]["role"],
}


def get_session() -> Session:
    """Cria (ou reaproveita) uma sessão Snowpark com o Snowflake, usando a chave privada.

    A chave privada vem de st.secrets (mesmo lugar que user/account/etc), não de
    um arquivo no disco — assim o mesmo secrets.toml funciona tanto rodando local
    quanto no Streamlit Community Cloud, onde não existe arquivo rsa_key.p8 (ele
    nunca é enviado ao GitHub, por segurança).
    """
    private_key_pem = st.secrets["snowflake"]["private_key"].encode()
    p_key = serialization.load_pem_private_key(private_key_pem, password=None)

    private_key_bytes = p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    params = dict(connection_parameters)
    params["private_key"] = private_key_bytes
    return Session.builder.configs(params).create()


# ----------------------------------------------------------------------------
# Sidebar — título e botões de carga
# ----------------------------------------------------------------------------
st.sidebar.title("🦠 COVID-19 Dashboard")
st.sidebar.caption("Dados: Our World in Data (OWID)")
st.sidebar.markdown("---")

if st.sidebar.button("📥 Carregar Dados no Snowflake"):
    with st.spinner("Baixando CSV e enviando para o Snowflake..."):
        # 1) Baixa o CSV público da OWID
        df = pd.read_csv(CSV_URL)

        # 2) Filtra: apenas os países selecionados e a partir da data de início,
        #    removendo agregados de continente/mundo (que não têm 'continent' preenchido)
        df = df[df["location"].isin(PAISES)]
        df = df[df["date"] >= DATA_INICIO]
        df = df.dropna(subset=["continent"])

        # Mantém só as colunas relevantes para o dashboard
        colunas = [
            "location", "continent", "date",
            "total_cases", "new_cases", "total_deaths", "new_deaths",
            "population", "people_vaccinated", "people_fully_vaccinated",
        ]
        df = df[colunas]
        df["date"] = pd.to_datetime(df["date"]).dt.date

        # 3) Conecta ao Snowflake e grava a tabela
        session = get_session()
        session.write_pandas(
            df,
            TABLE_NAME,
            auto_create_table=True,
            overwrite=True,
        )
        session.close()

    st.sidebar.success(f"✅ {len(df)} linhas carregadas na tabela {TABLE_NAME}!")

if st.sidebar.button("📊 Carregar Dashboard"):
    with st.spinner("Lendo dados do Snowflake..."):
        session = get_session()
        df = session.table(TABLE_NAME).to_pandas()
        session.close()

        # Normaliza nomes de coluna (Snowflake devolve em maiúsculas por padrão)
        df.columns = [c.lower() for c in df.columns]
        df["date"] = pd.to_datetime(df["date"])
        st.session_state["covid_df"] = df

    st.sidebar.success("✅ Dashboard atualizado com os dados do Snowflake!")

# ----------------------------------------------------------------------------
# Conteúdo principal
# ----------------------------------------------------------------------------
st.title("🦠 Dashboard COVID-19 — Our World in Data")
st.caption(
    f"Países analisados: {', '.join(PAISES)} · Período: a partir de {DATA_INICIO}"
)

if "covid_df" not in st.session_state:
    st.info(
        "👈 Use os botões na barra lateral: primeiro **Carregar Dados no Snowflake** "
        "(só na primeira vez, ou quando quiser atualizar) e depois **Carregar Dashboard**."
    )
    st.stop()

df = st.session_state["covid_df"].copy()

# ----------------------------------------------------------------------------
# Filtros interativos
# ----------------------------------------------------------------------------
st.subheader("Filtros")
col_f1, col_f2 = st.columns([2, 3])

with col_f1:
    paises_selecionados = st.multiselect(
        "Países", options=sorted(df["location"].unique()), default=sorted(df["location"].unique())
    )

with col_f2:
    data_min, data_max = df["date"].min().date(), df["date"].max().date()
    periodo = st.slider(
        "Período",
        min_value=data_min,
        max_value=data_max,
        value=(data_min, data_max),
        format="DD/MM/YYYY",
    )

df_filtrado = df[
    df["location"].isin(paises_selecionados)
    & (df["date"].dt.date >= periodo[0])
    & (df["date"].dt.date <= periodo[1])
]

if df_filtrado.empty:
    st.warning("Nenhum dado para os filtros selecionados.")
    st.stop()

# ----------------------------------------------------------------------------
# KPIs
# ----------------------------------------------------------------------------
st.markdown("---")
k1, k2, k3 = st.columns(3)

total_casos = df_filtrado.groupby("location")["total_cases"].max().sum()
total_obitos = df_filtrado.groupby("location")["total_deaths"].max().sum()
n_paises = df_filtrado["location"].nunique()

k1.metric("Total de casos (soma dos países)", f"{total_casos:,.0f}".replace(",", "."))
k2.metric("Total de óbitos (soma dos países)", f"{total_obitos:,.0f}".replace(",", "."))
k3.metric("Países analisados", n_paises)

st.markdown("---")

# ----------------------------------------------------------------------------
# Visualizações obrigatórias (em abas)
# ----------------------------------------------------------------------------
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    [
        "📈 Casos ao longo do tempo",
        "⚰️ Óbitos por país",
        "💉 Vacinação",
        "🌍 População x Casos",
        "🗂️ Dados Brutos",
        "🧪 Query SQL (opcional)",
    ]
)

# 1) Evolução de casos novos ao longo do tempo, por país — linha
with tab1:
    st.subheader("Evolução de novos casos por dia")
    fig1 = px.line(
        df_filtrado,
        x="date",
        y="new_cases",
        color="location",
        labels={"date": "Data", "new_cases": "Novos casos", "location": "País"},
    )
    st.plotly_chart(fig1, use_container_width=True)

# 2) Comparação do total de óbitos entre os países — barras
with tab2:
    st.subheader("Total de óbitos por país (no fim do período selecionado)")
    obitos_por_pais = (
        df_filtrado.dropna(subset=["total_deaths"])
        .sort_values("date")
        .groupby("location")
        .tail(1)[["location", "total_deaths"]]
    )
    fig2 = px.bar(
        obitos_por_pais.sort_values("total_deaths", ascending=False),
        x="location",
        y="total_deaths",
        color="location",
        labels={"location": "País", "total_deaths": "Total de óbitos"},
        text_auto=".2s",
    )
    st.plotly_chart(fig2, use_container_width=True)

# 3) Proporção de vacinados (1 dose) por país, na data mais recente — pizza
with tab3:
    st.subheader("Proporção de pessoas vacinadas (1ª dose) — data mais recente disponível")
    vacinados = (
        df_filtrado.dropna(subset=["people_vaccinated"])
        .sort_values("date")
        .groupby("location")
        .tail(1)[["location", "people_vaccinated", "population"]]
    )
    if vacinados.empty:
        st.warning("Sem dados de vacinação para o período/países selecionados.")
    else:
        fig3 = px.pie(
            vacinados,
            names="location",
            values="people_vaccinated",
            labels={"location": "País", "people_vaccinated": "Pessoas vacinadas (1 dose)"},
        )
        st.plotly_chart(fig3, use_container_width=True)

# 4) Relação entre população e total de casos — dispersão
with tab4:
    st.subheader("População x Total de casos")
    pop_casos = (
        df_filtrado.dropna(subset=["total_cases"])
        .sort_values("date")
        .groupby("location")
        .tail(1)[["location", "population", "total_cases"]]
    )
    fig4 = px.scatter(
        pop_casos,
        x="population",
        y="total_cases",
        color="location",
        size="total_cases",
        hover_name="location",
        labels={"population": "População", "total_cases": "Total de casos"},
    )
    st.plotly_chart(fig4, use_container_width=True)

# Dados brutos + exportação
with tab5:
    st.subheader("Dados brutos (filtrados)")
    st.dataframe(df_filtrado, use_container_width=True)
    csv_export = df_filtrado.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Baixar CSV filtrado",
        data=csv_export,
        file_name="covid_filtrado.csv",
        mime="text/csv",
    )

# Desafio opcional — query SQL livre
with tab6:
    st.subheader("Consulta SQL personalizada no Snowflake")
    st.caption(f"A tabela carregada se chama `{TABLE_NAME}`.")
    query = st.text_area(
        "Digite sua consulta SQL",
        value=f"SELECT location, MAX(total_cases) AS total_cases\nFROM {TABLE_NAME}\nGROUP BY location\nORDER BY total_cases DESC;",
        height=120,
    )
    if st.button("▶️ Executar consulta"):
        try:
            session = get_session()
            resultado = session.sql(query).to_pandas()
            session.close()
            st.dataframe(resultado, use_container_width=True)
        except Exception as e:
            st.error(f"Erro ao executar a consulta: {e}")
