import os

import pandas as pd
import plotly.express as px
import streamlit as st
from pymongo import MongoClient


st.set_page_config(
    page_title="Observatorio SECOP",
    page_icon=":mag:",
    layout="wide",
)

st.title("Observatorio SECOP - Contratacion Publica")
st.caption("Contraloria Departamental de Cundinamarca")


def get_secret(name):
    value = os.environ.get(name)
    if value:
        return value
    try:
        return st.secrets.get(name, "")
    except Exception:
        return ""


MONGODB_URI = get_secret("MONGODB_URI")
DATABASE_NAME = get_secret("MONGODB_DB") or "secop_observatorio"

if not MONGODB_URI:
    st.error("Configura MONGODB_URI como variable de entorno o en Streamlit Secrets.")
    st.stop()


@st.cache_resource
def get_db(uri, database_name):
    client = MongoClient(uri, serverSelectionTimeoutMS=8000)
    client.admin.command("ping")
    return client[database_name]


@st.cache_data(ttl=300)
def load_data(_db):
    meta = _db["metadata_pipeline"].find_one({"_id": "pipeline_v1"}) or {}

    contratos_count = _db["contratos_operativos"].count_documents({})
    alertas_count = _db["alertas_revision"].count_documents({})
    entidades_count = _db["entidades_resumen"].count_documents({})
    proveedores_count = _db["proveedores_resumen"].count_documents({})

    temas = list(
        _db["temas_resumen"]
        .find({}, {"_id": 0})
        .sort("contratos", -1)
        .limit(20)
    )

    entidades = list(
        _db["entidades_resumen"]
        .find({}, {"_id": 0})
        .sort("valor_total", -1)
        .limit(15)
    )

    proveedores = list(
        _db["proveedores_resumen"]
        .find({}, {"_id": 0})
        .sort("valor_total", -1)
        .limit(15)
    )

    alertas = list(
        _db["alertas_revision"]
        .find({}, {"_id": 0})
        .sort("indice", -1)
        .limit(100)
    )

    prioridad = list(
        _db["contratos_operativos"].aggregate(
            [
                {"$group": {"_id": "$prioridad.nivel", "contratos": {"$sum": 1}}},
                {"$sort": {"contratos": -1}},
            ]
        )
    )

    return {
        "meta": meta,
        "counts": {
            "contratos": contratos_count,
            "alertas": alertas_count,
            "entidades": entidades_count,
            "proveedores": proveedores_count,
        },
        "temas": temas,
        "entidades": entidades,
        "proveedores": proveedores,
        "alertas": alertas,
        "prioridad": prioridad,
    }


try:
    db = get_db(MONGODB_URI, DATABASE_NAME)
    data = load_data(db)
except Exception as exc:
    st.error(f"No fue posible conectar o leer MongoDB: {exc}")
    st.stop()


meta = data["meta"]
counts = data["counts"]
totales = meta.get("totales", {})

universo = (
    totales.get("contratos_integrados")
    or totales.get("contratos")
    or meta.get("universo_integrado")
    or meta.get("contratos_integrados")
    or 1_551_779
)

adiciones = (
    totales.get("adiciones_representadas")
    or totales.get("adiciones")
    or meta.get("adiciones_representadas")
    or meta.get("adiciones")
    or 10_956_201
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Contratos en MongoDB", f"{counts['contratos']:,}")
c2.metric("Alertas priorizadas", f"{counts['alertas']:,}")
c3.metric("Universo procesado", f"{universo:,}")
c4.metric("Adiciones representadas", f"{adiciones:,}")

st.divider()

left, right = st.columns(2)

with left:
    prioridad = data["prioridad"]
    if prioridad:
        df_prioridad = pd.DataFrame(prioridad)
        df_prioridad["_id"] = df_prioridad["_id"].fillna("sin clasificar")
        fig = px.bar(
            df_prioridad,
            x="_id",
            y="contratos",
            title="Distribucion por nivel de prioridad",
            labels={"_id": "Nivel", "contratos": "Contratos"},
            color="_id",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No hay datos de prioridad.")

with right:
    temas = data["temas"]
    if temas:
        df_temas = pd.DataFrame(temas)
        fig = px.bar(
            df_temas,
            x="contratos",
            y="tema",
            orientation="h",
            title="Contratos por tema detectado",
            labels={"contratos": "Contratos", "tema": "Tema"},
        )
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No hay temas cargados.")


left, right = st.columns(2)

with left:
    entidades = data["entidades"]
    if entidades:
        df_entidades = pd.DataFrame(entidades)
        nombre_col = "entidad" if "entidad" in df_entidades.columns else "nombre"
        fig = px.bar(
            df_entidades,
            x="valor_total",
            y=nombre_col,
            orientation="h",
            title="Top entidades por valor contratado",
            labels={"valor_total": "Valor total COP", nombre_col: "Entidad"},
        )
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No hay resumen de entidades.")

with right:
    proveedores = data["proveedores"]
    if proveedores:
        df_prov = pd.DataFrame(proveedores)
        nombre_col = "nombre" if "nombre" in df_prov.columns else "proveedor_adjudicado"
        fig = px.bar(
            df_prov,
            x="valor_total",
            y=nombre_col,
            orientation="h",
            title="Top proveedores por valor contratado",
            labels={"valor_total": "Valor total COP", nombre_col: "Proveedor"},
        )
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No hay resumen de proveedores.")


st.subheader("Alertas de revision prioritaria")
alertas = data["alertas"]

if alertas:
    df_alertas = pd.DataFrame(alertas)
    columnas = [
        col
        for col in [
            "id_contrato",
            "entidad",
            "proveedor",
            "valor",
            "indice",
            "nivel",
            "temas",
        ]
        if col in df_alertas.columns
    ]
    st.dataframe(df_alertas[columnas], use_container_width=True, height=420)
else:
    st.info("No hay alertas cargadas.")


st.divider()

st.subheader("Nota metodologica")
st.write(
    "El procesamiento completo se realizo en Databricks. Por el limite de "
    "almacenamiento de MongoDB Atlas M0, el dashboard publica una capa "
    "operativa priorizada en MongoDB, conservando en metadata el universo total "
    "procesado y las limitaciones del ejercicio."
)

st.caption(
    f"Base: {DATABASE_NAME} | "
    f"Fecha descarga: {meta.get('fecha_descarga', 'N/A')} | "
    f"Modo: {meta.get('modo_descarga', 'N/A')} | "
    f"Actualizaciones: {meta.get('num_actualizaciones', 0)}"
)
