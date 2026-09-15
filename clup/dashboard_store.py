from __future__ import annotations

from datetime import date, datetime
import math

import pandas as pd
import streamlit as st
from supabase import Client, create_client


DATE_COLUMNS = {
    "master": ["Planning Period From", "Planning Period To"],
    "locational": ["Date Applied", "Date Issued"],
    "reclassification": ["Date Applied", "Date Approved"],
}


def supabase_configured() -> bool:
    settings = st.secrets.get("supabase", {})
    return bool(settings.get("url") and (settings.get("secret_key") or settings.get("service_key") or settings.get("key")))


@st.cache_resource(show_spinner=False)
def get_client() -> Client:
    if not supabase_configured():
        raise RuntimeError("Supabase is not configured. Add the URL and service-role key to Streamlit Secrets.")
    settings = st.secrets["supabase"]
    key = settings.get("secret_key") or settings.get("service_key") or settings.get("key")
    return create_client(settings["url"], key)


def _records(frame: pd.DataFrame) -> list[dict]:
    if frame is None or frame.empty:
        return []
    clean = frame.copy()
    for column in clean.columns:
        if pd.api.types.is_datetime64_any_dtype(clean[column]):
            clean[column] = clean[column].dt.strftime("%Y-%m-%dT%H:%M:%S")
    clean = clean.astype(object).where(pd.notna(clean), None)

    def json_value(value):
        if value is None:
            return None
        if isinstance(value, (pd.Timestamp, datetime, date)):
            return value.isoformat()
        if hasattr(value, "item"):
            value = value.item()
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return value

    return [
        {column: json_value(value) for column, value in row.items()}
        for row in clean.to_dict(orient="records")
    ]


def _frame(rows, kind: str) -> pd.DataFrame:
    frame = pd.DataFrame(rows or [])
    for column in DATE_COLUMNS[kind]:
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
    return frame


def list_dashboards(username: str, role: str, assigned_dashboard: str | None = None) -> dict:
    query = get_client().table("clup_dashboards").select("*").order("name")
    if role == "operator":
        if not assigned_dashboard:
            return {}
        query = query.eq("name", assigned_dashboard)
    rows = query.execute().data or []
    return {
        row["name"]: {
            "master": _frame(row.get("master_data"), "master"),
            "locational": _frame(row.get("locational_data"), "locational"),
            "reclassification": _frame(row.get("reclassification_data"), "reclassification"),
            "source_name": row.get("source_name") or "Database",
        }
        for row in rows
    }


def save_dashboard(name: str, dashboard: dict, username: str, section: str) -> None:
    payload = {
        "name": name,
        "source_name": dashboard.get("source_name"),
        "master_data": _records(dashboard.get("master")),
        "locational_data": _records(dashboard.get("locational")),
        "reclassification_data": _records(dashboard.get("reclassification")),
        "updated_by": username,
    }
    get_client().table("clup_dashboards").upsert(payload, on_conflict="name").execute()
    get_client().table("clup_upload_history").insert({
        "username": username,
        "dashboard_name": name,
        "section": section,
        "source_name": dashboard.get("source_name"),
    }).execute()


def delete_dashboard(name: str, username: str) -> None:
    """Delete one stored dashboard and keep an audit entry."""
    client = get_client()
    client.table("clup_dashboards").delete().eq("name", name).execute()
    client.table("clup_upload_history").insert({
        "username": username,
        "dashboard_name": name,
        "section": "Deleted Dashboard",
        "source_name": None,
    }).execute()


def load_history() -> pd.DataFrame:
    rows = get_client().table("clup_upload_history").select("created_at,username,dashboard_name,section,source_name").order("created_at", desc=True).limit(200).execute().data or []
    return pd.DataFrame(rows)
