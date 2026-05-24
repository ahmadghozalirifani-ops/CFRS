"""
tabs_map.py — Tab 3: Peta Rute untuk dashboard CFRS.
"""

import streamlit as st
from streamlit_folium import st_folium
from datetime import date

from config import SLOTS
from styles import VEHICLE_COLORS
from map_view import build_map
from helpers import html_kpi_card


def render(gh_url: str, gh_profile: str, delivery_date_str: str):
    """Render Tab 3: Peta Rute — filter slot/kendaraan, Folium map per slot."""
    if "all_results" not in st.session_state:
        st.info("👈 Jalankan optimasi terlebih dahulu untuk melihat peta rute.")
        return

    all_r    = st.session_state["all_results"]
    locs_map = st.session_state["all_locs_map"]

    available_slots = [s for s in SLOTS if all_r.get(s)]
    if not available_slots:
        st.warning("Tidak ada slot dengan hasil optimasi.")
        return

    fc1, fc2 = st.columns([2, 3])
    sel_slot = fc1.selectbox(
        "Filter Slot",
        ["Semua"] + available_slots,
        format_func=lambda s: SLOTS[s]["label"] if s != "Semua" else "☀️🌙 Semua Slot",
    )

    if sel_slot == "Semua":
        cand_results = [r for v in all_r.values() for r in v]
    else:
        cand_results = all_r.get(sel_slot, [])

    all_vids = [r["vehicle_id"] for r in cand_results]
    sel_vids = fc2.multiselect(
        "Filter Kendaraan",
        all_vids,
        default=all_vids,
        placeholder="Pilih kendaraan …",
    )

    st.markdown("")

    slots_to_render = available_slots if sel_slot == "Semua" else [sel_slot]

    for slot_name in slots_to_render:
        results  = all_r.get(slot_name, [])
        all_locs = locs_map[slot_name]
        dep_hour = SLOTS[slot_name]["departure"]
        slot_lbl = SLOTS[slot_name]["label"]

        visible = [r for r in results if r["vehicle_id"] in sel_vids]
        if not visible:
            continue

        st.markdown(f"### 🗺️ {slot_lbl}")

        # Legenda — bangun color map dari urutan di results (konsisten dgn build_map)
        vid_to_color = {}
        for ri, rr in enumerate(results):
            vid_to_color[rr["vehicle_id"]] = VEHICLE_COLORS[ri % len(VEHICLE_COLORS)]

        leg_cols = st.columns(min(len(visible), 4))
        for idx_r, r in enumerate(visible):
            color = vid_to_color.get(r["vehicle_id"], "#888888")
            vc = "🏍️" if r.get("vehicle_type") == "motor" else "🚗"
            with leg_cols[idx_r % len(leg_cols)]:
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:8px;'
                    f'padding:6px 10px;background:#FFFFFF;border:1px solid #E5E7EB;border-radius:8px;'
                    f'margin-bottom:4px;box-shadow:0 2px 4px rgba(0,0,0,0.02)">'
                    f'<div style="width:12px;height:12px;background:{color};'
                    f'border-radius:50%"></div>'
                    f'<span style="font-size:.82rem;color:#1a1a2e;font-weight:500;">{vc} {r["vehicle_id"]}'
                    f' — {r["load"]}📦 · {r.get("total_km",0):.1f}km</span></div>',
                    unsafe_allow_html=True,
                )

        map_date = date.fromisoformat(st.session_state.get("opt_delivery_date", delivery_date_str))
        fmap = build_map(all_locs, results, dep_hour,
                         gh_url=gh_url, gh_profile=gh_profile,
                         filter_vehicles=sel_vids,
                         delivery_date=map_date)
        st.markdown('<div style="background:#FFFFFF; padding:10px; border-radius:12px; border:1px solid #E5E7EB; box-shadow:0 4px 12px rgba(0,0,0,0.03); margin-bottom:16px;">', unsafe_allow_html=True)
        st_folium(fmap, use_container_width=True, height=520, returned_objects=[])
        st.markdown('</div>', unsafe_allow_html=True)

        rsum1, rsum2, rsum3 = st.columns(3)
        rsum1.markdown(html_kpi_card(f"{sum(r.get('total_km',0) for r in visible):.1f} km", "Total Jarak", "#4361EE"), unsafe_allow_html=True)
        rsum2.markdown(html_kpi_card(str(sum(len(r["route"]) for r in visible)), "Total Stop", "#2EC4B6"), unsafe_allow_html=True)
        rsum3.markdown(html_kpi_card(str(sum(r["load"] for r in visible)), "Total Box", "#7209B7"), unsafe_allow_html=True)

        st.markdown("---")
