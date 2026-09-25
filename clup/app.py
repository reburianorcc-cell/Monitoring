"""CLUP module embedded in the authenticated SOCOCA Monitoring Portal."""
import streamlit as st

from .config import APP_TITLE
from .dashboard_store import delete_dashboard, list_dashboards, load_history, save_dashboard, supabase_configured
from .data_loader import load_all, load_sococa_exports, parse_table_upload
from evacuation.styles import apply_styles
from .views import locational_clearance, overview, reclassification

apply_styles()

if not st.session_state.get("admin_authenticated"):
    st.error("Please sign in through the SOCOCA Monitoring Portal.")
    st.stop()
if not supabase_configured():
    st.error("Supabase is not configured for CLUP Monitoring.")
    st.info("Use the same [supabase] URL and secret/service key configured for the Incident Dashboard.")
    st.stop()

username = st.session_state.get("admin_username") or "unknown"
role = st.session_state.get("admin_role") or "operator"
assigned_dashboard = st.session_state.get("assigned_dashboard")

try:
    dashboards = list_dashboards(username, role, assigned_dashboard)
except Exception as error:
    st.error(f"Unable to load CLUP dashboard data: {error}")
    st.stop()

def go(page_name):
    st.session_state.clup_page = page_name

with st.sidebar:
    pages = [("Overview", ":material/home:"), ("Locational Clearance", ":material/location_on:"), ("Land-Use Reclassification", ":material/swap_horiz:"), ("Data Upload", ":material/cloud_upload:")]
    if st.session_state.get("clup_page") not in [item[0] for item in pages]:
        st.session_state.clup_page = "Overview"
    for name, icon in pages:
        st.button(name, icon=icon, use_container_width=True, type="primary" if st.session_state.clup_page == name else "secondary", on_click=go, args=(name,), key=f"nav_clup_{name.casefold().replace(' ', '_').replace('-', '_')}")

page = st.session_state.clup_page
title_col, selector_col = st.columns([1.7, 1])
selected_dashboard = None
if dashboards:
    names = sorted(dashboards)
    current = st.session_state.get("clup_selected_dashboard")
    with selector_col:
        selected_dashboard = st.selectbox("📊 Selected dashboard", names, index=names.index(current) if current in names else 0, key="clup_dashboard_selector")
        st.session_state.clup_selected_dashboard = selected_dashboard
        st.caption(f"Source: {dashboards[selected_dashboard]['source_name']}")
elif role == "operator":
    st.warning("Your assigned dashboard has no CLUP data yet. Open Data Upload to add it.")

display_location = "CLUP"
display_region = "PLANNING & DEVELOPMENT"
if selected_dashboard:
    selected_master = dashboards[selected_dashboard].get("master")
    if selected_master is not None and not selected_master.empty:
        if "Province" in selected_master:
            provinces = selected_master["Province"].dropna().astype(str).str.strip()
            provinces = provinces[provinces.ne("")]
            if not provinces.empty:
                display_location = provinces.iloc[0]
        if display_location == "CLUP" and "Municipality" in selected_master:
            municipalities = selected_master["Municipality"].dropna().astype(str).str.strip()
            municipalities = municipalities[municipalities.ne("")]
            if not municipalities.empty:
                display_location = municipalities.iloc[0]
        if "Region" in selected_master:
            regions = selected_master["Region"].dropna().astype(str).str.strip()
            regions = regions[regions.ne("")]
            if not regions.empty:
                display_region = f"{regions.iloc[0]} · PLANNING & DEVELOPMENT"

with title_col:
    heading = f"{display_location} CLUP Monitoring Dashboard" if display_location != "CLUP" else APP_TITLE
    st.markdown(
        f"<div class='page-heading'><span class='eyebrow'>{display_region}</span>"
        f"<h1>{heading}</h1><p>Monitor approved land-use areas, locational clearances "
        f"and land-use reclassification activity for {display_location}.</p></div>",
        unsafe_allow_html=True,
    )

def require_dashboard():
    if not selected_dashboard:
        st.info("No CLUP dashboard data is stored yet. Open **Data Upload** to add the first workbook.")
        st.stop()
    return dashboards[selected_dashboard]

if page == "Overview":
    dashboard = require_dashboard()
    master = dashboard["master"]
    municipalities = sorted(master["Municipality"].dropna().astype(str).unique()) if "Municipality" in master else []
    municipality = st.selectbox("🏛️ Municipality", ["All Municipalities"] + municipalities, key="clup_municipality")
    filtered = master if municipality == "All Municipalities" else master[master["Municipality"] == municipality]
    overview(filtered, dashboard["reclassification"])
elif page == "Locational Clearance":
    locational_clearance(require_dashboard()["locational"])
elif page == "Land-Use Reclassification":
    dashboard = require_dashboard()
    reclassification(dashboard["reclassification"], dashboard["master"])
else:
    st.subheader("Upload CLUP Monitoring Data")
    st.caption("Operators can add or update only their assigned dashboard. Admins can manage all CLUP dashboards.")
    can_create = role in ("super_admin", "admin")
    export_tab, complete_tab, lc_tab, reclass_tab, history_tab = st.tabs([
        "SOCOCA Export Files",
        "Combined CLUP Template",
        "Locational Clearance Records",
        "Land-Use Reclassification Records",
        "Upload History",
    ])
    with export_tab:
        st.caption(
            "Upload the Spot CLUP XLSX, Zone Areas CSV, Locational Clearance CSV, "
            "and Land-Use Reclassification CSV from the same SOCOCA export."
        )
        export_dashboard_name = st.text_input(
            "Dashboard name",
            value=assigned_dashboard or "",
            disabled=role == "operator",
            max_chars=80,
            key="clup_exports_name",
        ).strip()
        spot_upload = st.file_uploader(
            "1. Spot CLUP Monitoring file",
            type=["xlsx", "csv"],
            key="clup_spot_export",
        )
        zone_upload = st.file_uploader(
            "2. Zone Areas Based from Approved",
            type=["csv", "xlsx"],
            key="clup_zone_export",
        )
        locational_upload = st.file_uploader(
            "3. Locational Clearance Records",
            type=["csv", "xlsx"],
            key="clup_locational_export",
        )
        reclassification_upload = st.file_uploader(
            "4. Land-Use Reclassification",
            type=["csv", "xlsx"],
            key="clup_reclassification_export",
        )
        export_files = [spot_upload, zone_upload, locational_upload, reclassification_upload]
        if all(export_files):
            try:
                master, locational, reclass = load_sococa_exports(*export_files)
                total = master["Overall Total Area"].max()
                developed = master["Overall Developed Area"].max()
                remaining = master["Overall Still to Be Developed"].max()
                st.success(
                    f"Validated {len(master)} zoning categories, {len(locational)} clearance "
                    f"records and {len(reclass)} reclassification records. Overall land: "
                    f"{total:,.2f} ha ({developed:,.2f} ha developed; {remaining:,.2f} ha remaining)."
                )
                export_allowed = can_create or bool(
                    assigned_dashboard
                    and export_dashboard_name.casefold() == assigned_dashboard.casefold()
                )
                confirm_exports = st.checkbox(
                    "I confirm that these four files belong to the same CLUP dashboard.",
                    key="clup_confirm_exports",
                )
                if st.button(
                    "Save SOCOCA CLUP exports",
                    type="primary",
                    disabled=not (confirm_exports and export_dashboard_name and export_allowed),
                    key="clup_save_exports",
                ):
                    source_names = ", ".join(file.name for file in export_files)
                    save_dashboard(
                        export_dashboard_name,
                        {
                            "master": master,
                            "locational": locational,
                            "reclassification": reclass,
                            "source_name": source_names,
                        },
                        username,
                        "SOCOCA CLUP Exports",
                    )
                    st.session_state.clup_selected_dashboard = export_dashboard_name
                    st.success(f"Dashboard '{export_dashboard_name}' saved successfully.")
                    st.rerun()
            except Exception as error:
                st.error(f"Unable to read the SOCOCA export files: {error}")
        elif any(export_files):
            st.info("Select all four SOCOCA export files to validate and save the CLUP dashboard.")
    with complete_tab:
        dashboard_name = st.text_input("Dashboard name", value=assigned_dashboard or "", disabled=role == "operator", max_chars=80, key="clup_complete_name").strip()
        complete = st.file_uploader(
            "Complete CLUP Excel or CSV file",
            type=["xlsx", "csv"],
            key="clup_complete_upload",
        )
        if complete:
            try:
                master, locational, reclass = load_all(complete)
                if master.empty:
                    raise ValueError(
                        "No valid CLUP zoning rows were found. Upload the complete CLUP template "
                        "as an XLSX file or as a CSV exported without removing its original columns."
                    )
                st.success(f"Validated {len(master)} zoning rows, {len(locational)} clearance records and {len(reclass)} reclassification records.")
                allowed = can_create or bool(assigned_dashboard and dashboard_name.casefold() == assigned_dashboard.casefold())
                confirm = st.checkbox("I confirm that I want to save this complete CLUP workbook.", key="clup_confirm_complete")
                if st.button("Save complete CLUP data", type="primary", disabled=not (confirm and dashboard_name and allowed), key="clup_save_complete"):
                    save_dashboard(dashboard_name, {"master": master, "locational": locational, "reclassification": reclass, "source_name": complete.name}, username, "Complete CLUP")
                    st.session_state.clup_selected_dashboard = dashboard_name
                    st.success(f"Dashboard '{dashboard_name}' saved successfully.")
                    st.rerun()
            except Exception as error:
                st.error(f"Unable to read the workbook: {error}")
    targets = sorted(dashboards)
    with lc_tab:
        if not targets:
            st.info("Upload a complete CLUP workbook first.")
        else:
            target = st.selectbox("Upload to dashboard", targets, key="clup_lc_target")
            upload = st.file_uploader(
                "Locational Clearance Records (Excel or CSV)",
                type=["xlsx", "csv"],
                key="clup_lc_upload",
            )
            if upload:
                try:
                    preview = parse_table_upload(upload, "locational")
                    if preview.empty:
                        raise ValueError("No valid locational-clearance records were found in the uploaded file.")
                    confirm = st.checkbox("I confirm replacement of the locational-clearance records.", key="clup_confirm_lc")
                    if st.button("Save locational-clearance records", type="primary", disabled=not confirm, key="clup_save_lc"):
                        updated = dict(dashboards[target]); updated["locational"] = preview; updated["source_name"] = upload.name
                        save_dashboard(target, updated, username, "Locational Clearance")
                        st.success("Locational-clearance records saved."); st.rerun()
                except Exception as error:
                    st.error(f"Unable to read the file: {error}")
    with reclass_tab:
        if not targets:
            st.info("Upload a complete CLUP workbook first.")
        else:
            target = st.selectbox("Upload to dashboard", targets, key="clup_reclass_target")
            upload = st.file_uploader(
                "Land-Use Reclassification Records (Excel or CSV)",
                type=["xlsx", "csv"],
                key="clup_reclass_upload",
            )
            if upload:
                try:
                    preview = parse_table_upload(upload, "reclassification")
                    if preview.empty:
                        raise ValueError("No valid land-use reclassification records were found in the uploaded file.")
                    confirm = st.checkbox("I confirm replacement of the reclassification records.", key="clup_confirm_reclass")
                    if st.button("Save reclassification records", type="primary", disabled=not confirm, key="clup_save_reclass"):
                        updated = dict(dashboards[target]); updated["reclassification"] = preview; updated["source_name"] = upload.name
                        save_dashboard(target, updated, username, "Land-Use Reclassification")
                        st.success("Reclassification records saved."); st.rerun()
                except Exception as error:
                    st.error(f"Unable to read the file: {error}")
    with history_tab:
        if role not in ("super_admin", "admin"):
            st.info("Upload history and dashboard deletion are available to administrators.")
        else:
            history = load_history()
            st.dataframe(history, use_container_width=True, hide_index=True) if not history.empty else st.info("No upload history yet.")
            st.divider()
            st.subheader("Delete Dashboard Data")
            if targets:
                delete_target = st.selectbox("Dashboard to delete", targets, key="clup_delete_target")
                confirm_delete = st.checkbox(f"I confirm permanent deletion of '{delete_target}'.", key="clup_confirm_delete")
                if st.button("Delete selected dashboard", type="primary", icon=":material/delete_forever:", disabled=not confirm_delete, key="clup_delete"):
                    delete_dashboard(delete_target, username)
                    st.session_state.pop("clup_selected_dashboard", None)
                    st.success(f"Dashboard '{delete_target}' was deleted.")
                    st.rerun()
            else:
                st.info("There are no dashboards available to delete.")
