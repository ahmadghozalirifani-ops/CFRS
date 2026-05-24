"""
tabs_export.py — Tab 4: Export & WA untuk dashboard CFRS.
"""

import streamlit as st
import pandas as pd
import json
from datetime import date, datetime, timedelta
from urllib.parse import quote

from config import SLOTS, COMMON_DUE_DATE_MINUTES
from helpers import build_wa_text, gmaps_route_url
from styles import VEHICLE_COLORS


def render():
    """Render Tab 4: Export & WA — download buttons, WA message per driver."""
    if "all_results" not in st.session_state:
        st.info("👈 Jalankan optimasi terlebih dahulu untuk mengekspor hasil.")
        return

    all_r     = st.session_state["all_results"]
    locs_map  = st.session_state["all_locs_map"]
    opt_date  = st.session_state.get("opt_delivery_date", "")
    depot_cfg = st.session_state.get("opt_depot_cfg", {})

    st.markdown("### 📥 Export Data")

    # Build export payload
    export_data = []
    for slot_name in SLOTS:
        for r in all_r.get(slot_name, []):
            locs    = locs_map.get(slot_name, [])
            dep_h   = SLOTS[slot_name]["departure"]
            exp_date = date.fromisoformat(opt_date) if opt_date else date.today()
            dep_dt  = datetime(exp_date.year, exp_date.month, exp_date.day,
                               int(dep_h), int((dep_h % 1) * 60))
            route_list = []
            for s, (ci, arr) in enumerate(zip(r["route"], r["arrivals"])):
                loc = locs[ci]
                eta = dep_dt + timedelta(minutes=arr)
                route_list.append({
                    "stop":        s + 1,
                    "name":        str(loc.name),
                    "lat":         float(loc.lat),
                    "lon":         float(loc.lon),
                    "demand":      int(loc.demand),
                    "arrival_min": round(float(arr), 2),
                    "eta":         eta.strftime("%H:%M"),
                    "on_time":     bool(float(arr) <= COMMON_DUE_DATE_MINUTES),
                })
            exp_f_info = st.session_state.get("fleet_phone_map", {}).get(
                r["vehicle_id"], {})
            export_data.append({
                "date":       opt_date,
                "slot":       slot_name,
                "vehicle_id": str(r["vehicle_id"]),
                "driver":     exp_f_info.get("driver") or r.get("driver", ""),
                "phone":      exp_f_info.get("phone") or r.get("phone", ""),
                "feasible":   bool(r["feasible"]),
                "load":       int(r["load"]),
                "capacity":   int(r["capacity"]),
                "total_km":   round(float(r.get("total_km", 0)), 2),
                "route":      route_list,
            })

    exp1, exp2, exp3, exp4 = st.columns(4)
    exp1.download_button(
        "📊 JSON",
        data=json.dumps(export_data, indent=2, ensure_ascii=False),
        file_name=f"routes_{opt_date}.json",
        mime="application/json",
        width="stretch",
    )

    # CSV ringkasan (satu baris per rute)
    df_summary = pd.DataFrame([{
        "date":       d["date"],
        "slot":       d["slot"],
        "vehicle_id": d["vehicle_id"],
        "driver":     d["driver"],
        "phone":      d["phone"],
        "feasible":   d["feasible"],
        "stops":      len(d["route"]),
        "load":       d["load"],
        "capacity":   d["capacity"],
        "total_km":   d["total_km"],
    } for d in export_data])
    exp2.download_button(
        "📋 CSV Ringkasan",
        data=df_summary.to_csv(index=False).encode(),
        file_name=f"routes_summary_{opt_date}.csv",
        mime="text/csv",
        width="stretch",
    )

    # CSV detail (satu baris per stop)
    detail_rows = []
    for d in export_data:
        for s in d["route"]:
            detail_rows.append({
                "date": d["date"], "slot": d["slot"],
                "vehicle_id": d["vehicle_id"],
                "stop": s["stop"], "customer": s["name"],
                "lat": s["lat"], "lon": s["lon"],
                "boxes": s["demand"], "arrival_min": s["arrival_min"],
                "eta": s["eta"], "on_time": s["on_time"],
            })
    exp3.download_button(
        "📋 CSV Detail",
        data=pd.DataFrame(detail_rows).to_csv(index=False).encode(),
        file_name=f"routes_detail_{opt_date}.csv",
        mime="text/csv",
        width="stretch",
    )

    exp4.info("📄 PDF — coming soon", icon="ℹ️")

    st.markdown("---")

    # ── Pesan WA per Driver ───────────────────────────────────────────
    st.markdown("### 📱 Pesan WhatsApp per Driver")
    st.caption("Klik tombol 'Buka WA' untuk langsung membuka WhatsApp "
               "dengan pesan + link rute Google Maps.")

    phone_map = st.session_state.get("fleet_phone_map", {})

    for slot_name, cfg in SLOTS.items():
        results = all_r.get(slot_name, [])
        if not results:
            continue
        locs     = locs_map.get(slot_name, [])
        dep_h    = cfg["departure"]
        wa_date = date.fromisoformat(opt_date) if opt_date else date.today()
        dep_dt   = datetime(wa_date.year, wa_date.month, wa_date.day,
                            int(dep_h), int((dep_h % 1) * 60))
        dep_time = f"{int(dep_h):02d}:{int((dep_h % 1) * 60):02d}"
        slot_lbl = cfg["label"]
        emoji    = "☀️" if slot_name == "siang" else "🌙"

        st.markdown(f"#### {emoji} {slot_lbl}")

        for idx_r, r in enumerate(results):
            color = VEHICLE_COLORS[idx_r % len(VEHICLE_COLORS)]
            vid   = r["vehicle_id"]
            vc    = "🏍️" if r.get("vehicle_type") == "motor" else "🚗"
            f_info = phone_map.get(vid, {})
            driver_name = f_info.get("driver") or r.get("driver") or vid

            # Build stops list for WA
            stops_wa = []
            for s, (ci, arr) in enumerate(zip(r["route"], r["arrivals"])):
                loc = locs[ci]
                eta = dep_dt + timedelta(minutes=arr)
                stops_wa.append({
                    "stop":    s + 1,
                    "name":    loc.name,
                    "phone":   getattr(loc, 'phone', '') or '',
                    "lat":     loc.lat,
                    "lon":     loc.lon,
                    "demand":  loc.demand,
                    "eta":     eta.strftime("%H:%M"),
                    "on_time": arr <= COMMON_DUE_DATE_MINUTES,
                })

            gmaps_url = gmaps_route_url(depot_cfg, stops_wa)
            wa_phone  = f_info.get("phone") or r.get("phone") or ""
            msg_text  = build_wa_text(
                driver_name, vid, slot_lbl, dep_time,
                stops_wa, depot_cfg, r.get("total_km", 0),
                delivery_date=opt_date,
                gmaps_full_url=gmaps_url,
            )
            wa_url    = (f"https://wa.me/{wa_phone}?text={quote(msg_text)}"
                         if wa_phone else
                         f"https://wa.me/?text={quote(msg_text)}")

            with st.expander(
                f'{vc} **{vid}** — {driver_name}  '
                f'· {len(stops_wa)} stop · {r.get("total_km",0):.1f} km',
                expanded=False,
            ):
                st.markdown(
                    f'<div class="wa-preview">{msg_text}</div>',
                    unsafe_allow_html=True,
                )
                wacol1, wacol2, wacol3 = st.columns(3)
                wacol1.link_button(
                    f"📱 Buka WhatsApp — {driver_name}",
                    wa_url,
                    width="stretch",
                )
                if gmaps_url:
                    wacol2.link_button(
                        "🗺️ Rute Google Maps",
                        gmaps_url,
                        width="stretch",
                        key=f"gmaps_{vid}_{slot_name}",
                    )
                wacol3.download_button(
                    "📋 Salin Teks",
                    data=msg_text,
                    file_name=f"rute_{vid}_{opt_date}.txt",
                    mime="text/plain",
                    width="stretch",
                    key=f"dl_wa_{vid}_{slot_name}",
                )
