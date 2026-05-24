"""
tabs_input.py — Tab 1: Input Pesanan untuk dashboard CFRS.
"""

import streamlit as st
import pandas as pd

from config import SAMPLE_ORDERS
from helpers import sample_orders_to_df, db_orders_to_df, html_kpi_card


def render(delivery_date_str: str, delivery_date, _DB_AVAILABLE: bool,
           _get_orders_by_date, _bulk_insert_orders):
    """Render Tab 1: Input Pesanan — toolbar, import, data editor, KPI bar."""

    # ── Toolbar ──────────────────────────────────────────────────────────
    tb1, tb2, tb3, tb4, tb5 = st.columns([1.4, 1.4, 1.4, 1.4, 1])
    add_manual_btn  = tb1.button("➕ Tambah Manual",  width="stretch")
    upload_file_btn = tb2.button("📎 Upload File",    width="stretch")
    parse_wa_btn    = tb3.button("📱 Parse WA Text",  width="stretch")
    reload_btn      = tb4.button("🔄 Muat dari DB",   width="stretch",
                                  disabled=not _DB_AVAILABLE)
    clear_btn       = tb5.button("🗑️ Hapus Semua",    width="stretch")

    st.markdown("---")

    # Sumber data pesanan
    order_source_options = ["SAMPLE_ORDERS (config.py)"]
    if _DB_AVAILABLE:
        order_source_options = ["Database", "SAMPLE_ORDERS (config.py)"]

    order_source = st.radio(
        "Sumber data",
        order_source_options,
        index=0,
        horizontal=True,
        label_visibility="collapsed",
    )

    # Populate default_df
    if clear_btn:
        st.session_state["edited_df"] = pd.DataFrame(
            columns=["id","customer","phone","address","lat","lon","boxes","delivery_slot","delivery_date"])

    if reload_btn and _DB_AVAILABLE:
        db_orders = _get_orders_by_date(delivery_date_str)
        if db_orders:
            st.session_state["edited_df"] = db_orders_to_df(db_orders)
            st.success(f"🔄 {len(db_orders)} pesanan dimuat dari DB untuk {delivery_date_str}.")
        else:
            st.warning(f"Tidak ada pesanan di DB untuk {delivery_date_str}.")

    if st.session_state.get("_load_sample_trigger"):
        st.session_state["edited_df"] = sample_orders_to_df(SAMPLE_ORDERS, delivery_date_str)
        st.session_state.pop("_load_sample_trigger")
        st.success("📦 Sample data dimuat.")

    if "edited_df" not in st.session_state:
        if order_source == "Database" and _DB_AVAILABLE:
            db_orders = _get_orders_by_date(delivery_date_str)
            default_df = db_orders_to_df(db_orders) if db_orders else pd.DataFrame(
                columns=["id","customer","phone","address","lat","lon","boxes","delivery_slot","delivery_date"])
        else:
            default_df = sample_orders_to_df(SAMPLE_ORDERS, delivery_date_str)
        st.session_state["edited_df"] = default_df

    # ── Parse WA Text (expander) ─────────────────────────────────────────
    if parse_wa_btn:
        st.session_state["_show_wa_parser"] = True
    if st.session_state.get("_show_wa_parser"):
        with st.expander("📱 Parse Teks WhatsApp", expanded=True):
            st.caption("Tempel teks WA pesanan di bawah. Format baris: "
                       "`Nama | Alamat | lat,lon | N box`")
            wa_raw = st.text_area("Teks WA", height=150,
                                  placeholder="Budi | Jl. Contoh 1 | -7.78,110.39 | 2 box\n...")
            if st.button("✅ Proses WA", key="proc_wa"):
                rows_wa = []
                for line in wa_raw.strip().split("\n"):
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) >= 4:
                        try:
                            lat_str, lon_str = parts[2].split(",")
                            boxes = int(str(parts[3]).replace("box","").strip())
                            rows_wa.append({
                                "id": "", "customer": parts[0], "phone": "",
                                "address": parts[1],
                                "lat": float(lat_str), "lon": float(lon_str),
                                "boxes": boxes, "delivery_slot": "siang",
                                "delivery_date": delivery_date_str,
                            })
                        except Exception:
                            import logging
                            logging.getLogger(__name__).debug("WA parse skip: %s", line[:80])
                if rows_wa:
                    new_df = pd.DataFrame(rows_wa)
                    existing = st.session_state.get("edited_df", pd.DataFrame())
                    combined = pd.concat([existing, new_df], ignore_index=True) \
                               if not existing.empty else new_df
                    st.session_state["edited_df"] = combined
                    st.session_state["_show_wa_parser"] = False
                    st.success(f"✅ {len(rows_wa)} baris diimpor dari WA.")
                    st.rerun()

    # ── Upload CSV (expander) ────────────────────────────────────────────
    pending_csv = st.session_state.get("_pending_csv")
    if upload_file_btn:
        st.session_state["_show_csv_uploader"] = True
    if st.session_state.get("_show_csv_uploader") or pending_csv:
        with st.expander("📎 Import dari File CSV", expanded=True):
            csv_file = st.file_uploader(
                "Pilih CSV (kolom: customer, address, lat, lon, boxes, delivery_slot)",
                type=["csv"], key="tab_csv_upload",
            ) or pending_csv
            csv_date_override = st.date_input("Tanggal override", value=delivery_date,
                                               key="csv_date_ov")
            if csv_file and st.button("📥 Proses CSV", key="proc_csv"):
                try:
                    df_csv = pd.read_csv(csv_file)
                    required = {"customer", "address", "lat", "lon", "boxes"}
                    missing  = required - set(df_csv.columns)
                    if missing:
                        st.error(f"Kolom wajib tidak ditemukan: {missing}")
                    else:
                        csv_date_str = csv_date_override.strftime("%Y-%m-%d")
                        rows_csv = []
                        skipped = 0
                        for _, row in df_csv.iterrows():
                            lat_v = float(row["lat"])
                            lon_v = float(row["lon"])
                            if abs(lat_v) > 90 or abs(lon_v) > 180:
                                skipped += 1
                                continue
                            rows_csv.append({
                                "id":            str(row.get("id", "")),
                                "customer":      str(row["customer"]),
                                "phone":         str(row.get("phone", "")),
                                "address":       str(row["address"]),
                                "lat":           lat_v,
                                "lon":           lon_v,
                                "boxes":         int(row.get("boxes", 1)),
                                "delivery_slot": str(row.get("delivery_slot", "siang")),
                                "delivery_date": csv_date_str,
                            })
                        if skipped:
                            st.warning(f"⏭️ {skipped} baris dilewati — koordinat tidak valid.")
                        new_df   = pd.DataFrame(rows_csv)
                        existing = st.session_state.get("edited_df", pd.DataFrame())
                        combined = pd.concat([existing, new_df], ignore_index=True) \
                                   if not existing.empty else new_df
                        st.session_state["edited_df"] = combined
                        st.session_state.pop("_pending_csv", None)
                        st.session_state["_show_csv_uploader"] = False
                        st.success(f"✅ {len(rows_csv)} baris berhasil diimpor.")
                        st.rerun()
                except Exception as e:
                    st.error(f"Gagal: {e}")

    # ── Tambah Manual (expander) ─────────────────────────────────────────
    if add_manual_btn:
        st.session_state["_show_manual_add"] = True
    if st.session_state.get("_show_manual_add"):
        with st.expander("➕ Tambah Pesanan Manual", expanded=True):
            with st.form("form_manual_add", clear_on_submit=True):
                m1, m2, m3 = st.columns(3)
                m_cust  = m1.text_input("Nama Pelanggan *")
                m_phone = m2.text_input("No. HP", placeholder="628xxx")
                m_addr  = m3.text_input("Alamat")
                m4, m5, m6, m7 = st.columns(4)
                m_lat   = m4.number_input("Lat", value=-7.8, format="%.6f")
                m_lon   = m5.number_input("Lon", value=110.36, format="%.6f")
                m_box   = m6.number_input("Box", min_value=1, value=1)
                m_slot  = m7.selectbox("Slot", ["siang","sore","siang+sore"])
                ok_man  = st.form_submit_button("➕ Tambahkan")
            if ok_man and m_cust:
                if not (-90 <= m_lat <= 90) or not (-180 <= m_lon <= 180):
                    st.error("❌ Koordinat tidak valid — lat [-90..90], lon [-180..180]")
                elif m_box < 1:
                    st.error("❌ Box minimal 1")
                else:
                    new_row = pd.DataFrame([{
                        "id":"", "customer": m_cust, "phone": m_phone,
                        "address": m_addr,
                        "lat": m_lat, "lon": m_lon,
                        "boxes": m_box, "delivery_slot": m_slot,
                        "delivery_date": delivery_date_str,
                    }])
                    existing = st.session_state.get("edited_df", pd.DataFrame())
                    st.session_state["edited_df"] = pd.concat(
                        [existing, new_row], ignore_index=True)
                    st.session_state["_show_manual_add"] = False
                    st.rerun()

    # ── Data Editor ──────────────────────────────────────────────────────
    cur_df   = st.session_state["edited_df"]
    edit_src = f"📂 {delivery_date_str}" if (
        order_source == "Database" and _DB_AVAILABLE
    ) else "📦 SAMPLE_ORDERS / upload"
    
    # ── KPI Bar (Moved Up) ───────────────────────────────────────────────
    if not cur_df.empty:
        total_demand = int(cur_df["boxes"].sum())
        slot_counts  = cur_df["delivery_slot"].value_counts()
        siang_c = int(slot_counts.get("siang", 0)) + int(slot_counts.get("siang+sore", 0))
        sore_c  = int(slot_counts.get("sore",  0)) + int(slot_counts.get("siang+sore", 0))

        # Validasi koordinat
        bad_lat = (cur_df["lat"].abs() > 90).sum()
        bad_lon = (cur_df["lon"].abs() > 180).sum()
        if bad_lat or bad_lon:
            st.warning(f"⚠️ {bad_lat + bad_lon} pesanan memiliki koordinat tidak valid "
                      "(lat ±90°, lon ±180°). Optimasi mungkin gagal.")

        k1, k2, k3, k4 = st.columns(4)
        for col, val, lbl, color in [
            (k1, len(cur_df),  "Pesanan",  "#4361EE"),
            (k2, total_demand, "Total Box", "#7209B7"),
            (k3, f"{siang_c}/{sore_c}", "Siang/Sore", "#FFB703"),
            (k4, st.session_state.get("_fleet_count", "—"), "Armada", "#2EC4B6"),
        ]:
            col.markdown(html_kpi_card(val, lbl, color), unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

    st.caption(f"Sumber: {edit_src} · {len(cur_df)} pesanan")

    edited_df = st.data_editor(
        cur_df,
        num_rows="dynamic",
        width="stretch",
        column_config={
            "id":            st.column_config.TextColumn("ID", width="small"),
            "customer":      st.column_config.TextColumn("Nama Pelanggan"),
            "phone":         st.column_config.TextColumn("📱 HP", width="small"),
            "address":       st.column_config.TextColumn("Alamat"),
            "lat":           st.column_config.NumberColumn("Latitude",  format="%.6f"),
            "lon":           st.column_config.NumberColumn("Longitude", format="%.6f"),
            "boxes":         st.column_config.NumberColumn("📦 Box", min_value=1),
            "delivery_slot": st.column_config.SelectboxColumn(
                "Slot", options=["siang","sore","siang+sore"], width="small"),
            "delivery_date": st.column_config.TextColumn("Tgl Kirim", width="small"),
        },
        key="main_order_editor",
        hide_index=True,
    )
    st.session_state["edited_df"] = edited_df

    # ── Tombol simpan ke DB ───────────────────────────────────────────────
    sb_col1, sb_col2 = st.columns(2)
    if sb_col1.button("💾 Simpan ke Database", width="stretch",
                       disabled=not _DB_AVAILABLE):
        if _DB_AVAILABLE and not edited_df.empty:
            orders_data = []
            for _, row in edited_df.iterrows():
                row_date = str(row.get("delivery_date") or delivery_date_str)
                orders_data.append({
                    "customer":      str(row.get("customer") or ""),
                    "phone":         str(row.get("phone") or ""),
                    "address":       str(row.get("address") or ""),
                    "lat":           float(row.get("lat") or 0),
                    "lon":           float(row.get("lon") or 0),
                    "boxes":         int(row.get("boxes") or 1),
                    "delivery_slot": str(row.get("delivery_slot") or "siang"),
                    "delivery_date": row_date,
                    "notes":         "",
                    "status":        "pending",
                })
            if orders_data:
                count = _bulk_insert_orders(orders_data)
                st.success(f"✅ {count} dari {len(orders_data)} pesanan tersimpan ke DB.")
            else:
                st.warning("Tidak ada data yang valid untuk disimpan.")


