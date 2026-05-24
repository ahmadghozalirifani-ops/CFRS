"""
tabs_results.py — Tab 2: Hasil Optimasi untuk dashboard CFRS.
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta

from config import SLOTS, COMMON_DUE_DATE_MINUTES, SERVICE_TIME_MINUTES
from helpers import html_kpi_card, html_route_card, html_gh_proof
from styles import VEHICLE_COLORS


def render():
    """Render Tab 2: Hasil Optimasi — global KPI, per-slot results, route cards, GH proof."""
    if "all_results" not in st.session_state:
        st.info("👈 Isi data pesanan lalu tekan **🚀 Optimalkan Rute** di sidebar.")
        return

    all_r      = st.session_state["all_results"]
    locs_map   = st.session_state["all_locs_map"]
    gh_proof   = st.session_state.get("gh_proof_map", {})
    opt_date   = st.session_state.get("opt_delivery_date", "")
    depot_cfg  = st.session_state.get("opt_depot_cfg", {})

    if opt_date:
        st.caption(f"Hasil optimasi untuk **{opt_date}**")

    # ── Global KPI ────────────────────────────────────────────────────
    all_routes_flat = [r for v in all_r.values() for r in v]
    g_total_km   = sum(r.get("total_km", 0) for r in all_routes_flat)
    g_total_box  = sum(r["load"] for r in all_routes_flat)
    g_feasible   = sum(1 for r in all_routes_flat if r["feasible"])
    g_routes     = len(all_routes_flat)
    g_customers  = sum(len(r["route"]) for r in all_routes_flat)
    g_cap        = sum(r["capacity"] for r in all_routes_flat)
    g_eff        = (g_total_box / g_cap * 100) if g_cap > 0 else 0

    sub_overview, sub_detail = st.tabs(["📊 Ringkasan", "🚛 Detail Rute"])

    with sub_overview:
        gk1, gk2, gk3, gk4 = st.columns(4)
        for col, val, lbl, color in [
            (gk1, f"{g_total_km:.1f} km",     "Total Jarak",       "#4361EE"),
            (gk2, f"{g_eff:.1f}%",             "Efisiensi Kapasitas","#FFB703"),
            (gk3, f"{g_feasible}/{g_routes}", "Rute Feasible",     "#2EC4B6"),
            (gk4, g_customers,               "Pelanggan Terlayani","#7209B7"),
        ]:
            col.markdown(html_kpi_card(val, lbl, color), unsafe_allow_html=True)
            
        st.markdown("<br>", unsafe_allow_html=True)

        # ── Summary Table ────────────────────────────────────────────────
        summary_data = []
        for slot_name, cfg in SLOTS.items():
            results = all_r.get(slot_name, [])
            if not results: continue
            feas_c  = sum(1 for r in results if r["feasible"])
            box_tot = sum(r["load"] for r in results)
            customers = sum(len(r["route"]) for r in results)
            km_tot = sum(r.get('total_km',0) for r in results)
            summary_data.append({
                "Slot": cfg['label'],
                "Rute Feasible": f"{feas_c}/{len(results)}",
                "Total Box": box_tot,
                "Pelanggan": customers,
                "Total Jarak": f"{km_tot:.1f} km",
            })
        if summary_data:
            st.markdown("#### 📈 Ringkasan per Slot")
            st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)

        st.markdown("<br>", unsafe_allow_html=True)
        
        # ── GH Proofs ────────────────────────────────────────────────────
        for slot_name, proof in gh_proof.items():
            if proof:
                with st.expander(f"📡 Bukti GraphHopper — {slot_name.upper()}", expanded=False):
                    st.markdown(html_gh_proof(slot_name, proof), unsafe_allow_html=True)

    with sub_detail:
        slot_options = ["Semua"] + [cfg['label'] for cfg in SLOTS.values()]
        selected_slot = st.selectbox("Filter Slot", slot_options)
        
        # ── Per slot ──────────────────────────────────────────────────────
        for slot_name, cfg in SLOTS.items():
            if selected_slot != "Semua" and selected_slot != cfg['label']:
                continue
                
            results = all_r.get(slot_name, [])
            if not results:
                continue
            all_locs = locs_map[slot_name]
            dep_hour = cfg["departure"]
            tab2_date = date.fromisoformat(opt_date) if opt_date else date.today()
            dep_dt   = datetime(tab2_date.year, tab2_date.month, tab2_date.day,
                                int(dep_hour), int((dep_hour % 1) * 60))

            slot_emoji = "☀️" if slot_name == "siang" else "🌙"
            st.markdown(f"### {slot_emoji} {cfg['label']}")

            for idx_r, r in enumerate(sorted(results, key=lambda x: x["vehicle_id"])):
                color  = VEHICLE_COLORS[idx_r % len(VEHICLE_COLORS)]
                vid    = r["vehicle_id"]
                dep_str = f"{int(dep_hour):02d}:{int((dep_hour % 1) * 60):02d}"
                done_min = (max(r["arrivals"]) + SERVICE_TIME_MINUTES
                            if r["arrivals"] else 0)
                max_arr = max(r["arrivals"]) if r["arrivals"] else 0

                st.markdown(
                    html_route_card(
                        vid=vid,
                        vehicle_type=r.get("vehicle_type", "motor"),
                        color=color,
                        feasible=r["feasible"],
                        load=r["load"],
                        capacity=r["capacity"],
                        dep_str=dep_str,
                        done_min=done_min,
                        n_stops=len(r["route"]),
                        total_km=r.get("total_km", 0),
                        max_arr=max_arr,
                    ),
                    unsafe_allow_html=True,
                )

                if r["route"]:
                    with st.expander(f"📋 Detail Stop — {vid}", expanded=False):
                        rows_t = []
                        for stop, (ci, arr) in enumerate(zip(r["route"], r["arrivals"])):
                            loc = all_locs[ci]
                            eta = dep_dt + timedelta(minutes=arr)
                            rows_t.append({
                                "#":        stop + 1,
                                "Pelanggan": loc.name,
                                "📦 Box":    loc.demand,
                                "⏱ Menit":  f"{arr:.1f}",
                                "🕐 ETA":    eta.strftime("%H:%M"),
                                "Status":    "✅ On Time"
                                             if arr <= COMMON_DUE_DATE_MINUTES
                                             else "⚠️ Terlambat",
                                "📍 GMaps":  f"https://maps.google.com/?q={loc.lat},{loc.lon}",
                            })
                        st.dataframe(
                            pd.DataFrame(rows_t),
                            width="stretch",
                            hide_index=True,
                            column_config={
                                "📍 GMaps": st.column_config.LinkColumn("📍 GMaps"),
                            },
                        )

            st.markdown("---")
