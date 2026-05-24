"""
main.py — Dashboard CFRS Route Optimizer (Streamlit)  ·  Tahap 2 Modular
         Cluster First, Route Second: K-Medoids + Hybrid GA/Tabu Search

Jalankan: streamlit run main.py

Modul:
  styles.py        — CSS custom & konstanta warna
  helpers.py       — Konverter DataFrame, builder WA/GMaps, pengecekan GH, markup HTML
  map_view.py      — Builder peta Folium
  tabs_input.py    — Tab 1: Input Pesanan
  tabs_results.py  — Tab 2: Hasil Optimasi
  tabs_map.py      — Tab 3: Peta Rute
  tabs_export.py   — Tab 4: Export & WA
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import pandas as pd
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime

from config import (
    SAMPLE_FLEET, DEPOT, SLOTS,
    CLUSTERING_MAX_ITER, PENALTY_CROSS_EQUITY_WEIGHT,
)
from graphhopper import Location, GraphHopperMatrix
from clustering import KMedoidsCFRS
from routing import HybridTSGA
from traffic import get_gamma

from styles import DASHBOARD_CSS
from helpers import (
    couriers_to_fleet, fleet_to_df, df_to_fleet, check_gh,
)
from tabs_input import render as render_input_tab
from tabs_results import render as render_results_tab
from tabs_map import render as render_map_tab
from tabs_export import render as render_export_tab

# ── Import database (aman jika database.py belum ada) ────────────────────────
def _get_orders_by_date(*args, **kwargs):
    raise RuntimeError("Database module not available")

def _get_all_couriers(*args, **kwargs):
    raise RuntimeError("Database module not available")

def _save_route_session(*args, **kwargs):
    raise RuntimeError("Database module not available")

def _insert_order(*args, **kwargs):
    raise RuntimeError("Database module not available")

def _bulk_insert_orders(*args, **kwargs):
    raise RuntimeError("Database module not available")

def _init_db(*args, **kwargs):
    raise RuntimeError("Database module not available")

try:
    from database import init_db as _init_db                           # type: ignore[no-redef]
    from database import get_orders_by_date as _get_orders_by_date     # type: ignore[no-redef]
    from database import get_all_couriers as _get_all_couriers         # type: ignore[no-redef]
    from database import save_route_session as _save_route_session     # type: ignore[no-redef]
    from database import insert_order as _insert_order                 # type: ignore[no-redef]
    from database import bulk_insert_orders as _bulk_insert_orders     # type: ignore[no-redef]
    _DB_AVAILABLE = True
    _init_db()
except ImportError:
    _DB_AVAILABLE = False

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# ── OPTIMASI SATU KLASTER ────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def _optimize_single_cluster(cluster, all_locs, time_mat, dist_mat,
                              dep_hour, slot_name,
                              max_work_minutes=None, cross_equity_weight=None):
    if not cluster.customer_indices:
        return None
    opt = HybridTSGA(
        cluster=cluster, locations=all_locs,
        base_time_matrix=time_mat, base_dist_matrix=dist_mat,
        departure_hour=dep_hour, depot_idx=0,
        max_work_minutes=max_work_minutes,
        cross_equity_weight=cross_equity_weight,
    )
    r = opt.optimize()
    r["vehicle_type"] = cluster.vehicle_type
    r["load"]         = cluster.total_load
    r["capacity"]     = cluster.capacity
    r["slot"]         = slot_name
    r["arrivals"]     = r.pop("arrival_times")
    full = [0] + r["route"] + [0]
    r["total_km"] = float(sum(
        dist_mat[full[k]][full[k+1]] for k in range(len(full)-1)))
    return r


# ══════════════════════════════════════════════════════════════════════════════
# ── MAIN UI ──────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def main():
    st.set_page_config(
        page_title="CFRS Katering — Route Optimizer",
        page_icon="🍱",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown(DASHBOARD_CSS, unsafe_allow_html=True)

    # ── Hero ─────────────────────────────────────────────────────────────────
    st.markdown("""
    <div class="hero">
      <div class="hero-icon">🍱</div>
      <div>
        <h1>CFRS Route Optimizer</h1>
        <p>Cluster First, Route Second &nbsp;·&nbsp; K-Medoids + Hybrid GA / Tabu Search
           &nbsp;·&nbsp; CDD 180 menit &nbsp;·&nbsp; Multi-slot (Siang & Sore)</p>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # DB status banner
    if _DB_AVAILABLE:
        st.markdown(
            '<div class="db-banner">🟢 Database aktif — pesanan & kurir dibaca dari '
            '<code>cfrs_katering.db</code>.</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="no-db-banner">🔴 <code>database.py</code> tidak ditemukan — '
            'menggunakan SAMPLE_ORDERS / SAMPLE_FLEET dari config.py.</div>',
            unsafe_allow_html=True,
        )

    # ══════════════════════════════════════════════════════════════════════════
    # SIDEBAR
    # ══════════════════════════════════════════════════════════════════════════
    with st.sidebar:
        st.markdown("## ⚙️ Konfigurasi")

        with st.expander("🌐 Server Peta", expanded=False):
            gh_url     = st.text_input("URL GraphHopper", "http://localhost:8989",
                                       placeholder="http://localhost:8989")
            gh_profile = st.selectbox("Profil Kendaraan", ["car", "bike", "foot"])
            if st.button("🔌 Tes Koneksi GH", key="test_gh"):
                if check_gh(gh_url):
                    st.success("✅ GraphHopper terhubung!")
                else:
                    st.error("❌ Tidak terhubung — akan pakai Euclidean fallback.")

        with st.expander("📅 Jadwal & Depot", expanded=False):
            delivery_date = st.date_input(
                "Tanggal Pengiriman",
                value=date.today(),
                min_value=date(2024, 1, 1),
                max_value=date(2027, 12, 31),
                key="main_delivery_date",
            )
            delivery_date_str = delivery_date.strftime("%Y-%m-%d")

            st.markdown("**Slot Aktif:**")
            for slot_name, cfg in SLOTS.items():
                dep_h  = cfg["departure"]
                gamma_ = get_gamma(dep_h)
                emoji  = "☀️" if slot_name == "siang" else "🌙"
                st.caption(f"{emoji} **{cfg['label']}** — "
                           f"{int(dep_h):02d}:{int((dep_h%1)*60):02d}, γ={gamma_:.1f}×")

            st.markdown("---")
            depot_name   = st.text_input("Nama Depot", DEPOT["name"])
            depot_admin  = st.text_input("No. HP Admin", DEPOT.get("phone", ""),
                                         placeholder="628xxxxxxxxx")
            col_lat, col_lon = st.columns(2)
            depot_lat = col_lat.number_input("Lat", value=DEPOT["lat"], format="%.6f")
            depot_lon = col_lon.number_input("Lon", value=DEPOT["lon"], format="%.6f")

        with st.expander("🔧 Parameter", expanded=False):
            max_work_hours = st.number_input(
                "Maks Jam Kerja (jam)", min_value=1.0, max_value=12.0, value=3.0, step=0.5,
                help="Batas waktu operasional kendaraan dari depot"
            )
            col_p1, col_p2 = st.columns(2)
            fair_distance = col_p1.toggle("Fair Distance", value=False,
                                           help="Distribusi jarak merata antar kendaraan")
            use_backup    = col_p2.toggle("Mobil Cadangan", value=True,
                                           help="Aktifkan kendaraan cadangan berkapasitas besar")

        with st.expander("🏎️ Armada", expanded=True):
            fleet_source_options = ["SAMPLE_FLEET (config.py)", "Manual"]
            if _DB_AVAILABLE:
                fleet_source_options = ["Database Kurir", "SAMPLE_FLEET (config.py)", "Manual"]

            fleet_source = st.radio("Sumber", fleet_source_options, index=0,
                                    label_visibility="collapsed")

            if fleet_source == "Database Kurir" and _DB_AVAILABLE:
                db_couriers = _get_all_couriers(active_only=True)
                if db_couriers:
                    base_fleet = couriers_to_fleet(db_couriers)
                else:
                    st.warning("Belum ada kurir aktif di DB.")
                    base_fleet = SAMPLE_FLEET
            elif fleet_source == "SAMPLE_FLEET (config.py)":
                base_fleet = SAMPLE_FLEET
            else:
                # Manual: build from scratch
                n_motor   = st.number_input("Jumlah Motor", 1, 8, 4)
                cap_motor = st.number_input("Kapasitas Motor (box)", 10, 100, 35)
                n_mobil   = st.number_input("Jumlah Mobil", 0, 4, 1)
                base_fleet = [
                    {"id": f"Motor {i+1}", "driver": f"Driver {i+1}",
                     "type": "motor", "capacity": cap_motor, "phone": ""}
                    for i in range(n_motor)
                ]
                base_fleet += [
                    {"id": f"Mobil {i+1}", "driver": "Cadangan",
                     "type": "mobil", "capacity": 999, "phone": ""}
                    for i in range(n_mobil)
                ]

            # Default editor: pakai fleet tersimpan jika ada
            if st.session_state.get("saved_fleet"):
                fleet_df_default = fleet_to_df(st.session_state["saved_fleet"])
            else:
                fleet_df_default = fleet_to_df(base_fleet)

            fleet_df_edited  = st.data_editor(
                fleet_df_default,
                num_rows="dynamic",
                width="stretch",
                column_config={
                    "Plat/ID": st.column_config.TextColumn("Plat/ID", width="small"),
                    "Driver":  st.column_config.TextColumn("Driver"),
                    "Tipe":    st.column_config.SelectboxColumn(
                        "Tipe", options=["motor","mobil"], width="small"),
                    "Box":     st.column_config.NumberColumn("Box", min_value=1, max_value=9999),
                    "No. HP":  st.column_config.TextColumn("No. HP", width="small"),
                },
                key="fleet_editor",
                hide_index=True,
            )
            fleet = df_to_fleet(fleet_df_edited)
            st.session_state["_fleet_count"] = len(fleet)

            if st.button("💾 Simpan Armada", key="save_fleet", width="stretch"):
                st.session_state["saved_fleet"] = fleet
                st.success(f"✅ {len(fleet)} kendaraan tersimpan.")

        with st.expander("📥 Import Pesanan", expanded=False):
            st.caption("Upload CSV atau muat dari sample data:")

            import_csv_sb = st.file_uploader("Upload CSV", type=["csv"], key="sb_csv_import",
                                              label_visibility="collapsed")
            if import_csv_sb:
                st.session_state["_pending_csv"] = import_csv_sb
                st.info("📎 File siap — lihat area import di tab Input Pesanan.")

            if st.button("📦 Muat Data Sample", width="stretch", key="load_sample_sb"):
                st.session_state["_load_sample_trigger"] = True

        st.markdown("---")
        run_btn = st.button("🚀  Optimalkan Rute", width="stretch", type="primary")

    # ══════════════════════════════════════════════════════════════════════════
    # 4 TABS
    # ══════════════════════════════════════════════════════════════════════════
    tab_input, tab_result, tab_map, tab_export = st.tabs([
        "📋 Input Pesanan",
        "📊 Hasil Optimasi",
        "🗺️ Peta Rute",
        "📤 Export & WA",
    ])

    with tab_input:
        render_input_tab(delivery_date_str, delivery_date, _DB_AVAILABLE,
                         _get_orders_by_date, _bulk_insert_orders)

    # ══════════════════════════════════════════════════════════════════════════
    # PROSES OPTIMASI
    # ══════════════════════════════════════════════════════════════════════════
    if run_btn:
        edited_df = st.session_state.get("edited_df", pd.DataFrame())
        if edited_df.empty:
            st.error("Tidak ada data pesanan. Isi tab **Input Pesanan** terlebih dahulu.")
            st.stop()

        depot_loc = Location("depot", depot_name or "Dapur", depot_lat, depot_lon, 0)
        depot_cfg = {"name": depot_name, "lat": depot_lat, "lon": depot_lon,
                     "phone": depot_admin}

        # ── Terapkan parameter sidebar ───────────────────────────────────────
        opt_fleet = [v for v in fleet if use_backup or v.get("type") != "mobil"]
        if not opt_fleet:
            st.error("Armada kosong — aktifkan 'Mobil Cadangan' atau tambah kendaraan.")
            st.stop()

        max_work_minutes = max_work_hours * 60.0
        cross_equity_weight = PENALTY_CROSS_EQUITY_WEIGHT if fair_distance else 0.0

        # Pisahkan order per slot
        slot_orders: dict[str, list] = {s: [] for s in SLOTS}
        for _, row in edited_df.iterrows():
            slot  = str(row.get("delivery_slot") or "siang")
            boxes = int(row.get("boxes") or 1)
            if slot in SLOTS:
                slot_orders[slot].append((row, boxes))
            elif slot == "siang+sore":
                bs = (boxes + 1) // 2
                br = boxes - bs
                slot_orders["siang"].append((row, bs))
                slot_orders["sore"].append((row, br))

        all_results:  dict[str, list]  = {}
        all_locs_map: dict[str, list]  = {}
        gh_proof_map: dict[str, dict]  = {}

        progress    = st.progress(0, "Memulai optimasi per slot …")
        total_slots = len(SLOTS)

        for si, (slot_name, cfg) in enumerate(SLOTS.items()):
            dep_hour = cfg["departure"]
            orders   = slot_orders[slot_name]
            if not orders:
                st.warning(f"Slot **{slot_name}** tidak memiliki pesanan, dilewati.")
                progress.progress((si + 1) / total_slots)
                continue

            st.info(f"☀️ **{cfg['label']}** — {len(orders)} order, "
                    f"berangkat {int(dep_hour):02d}:{int((dep_hour%1)*60):02d}")

            cust_locs = []
            for row, box_qty in orders:
                cust_locs.append(Location(
                    str(row.get("id") or ""),
                    str(row.get("customer") or ""),
                    float(row.get("lat") or 0),
                    float(row.get("lon") or 0),
                    box_qty,
                    phone=str(row.get("phone") or ""),
                ))
            all_locs = [depot_loc] + cust_locs

            # Matriks jarak
            with st.spinner(f"⏳ [{cfg['label']}] Matriks jarak via GraphHopper …"):
                gh_mat = GraphHopperMatrix(base_url=gh_url)
                try:
                    dist_mat, time_mat = gh_mat.get_matrix(all_locs, profile=gh_profile)
                    src = "graphhopper"
                    n_gh_pairs = len(all_locs) ** 2
                except Exception as e:
                    logger.warning("GH matrix gagal: %s — fallback Euclidean", e)
                    dist_mat, time_mat = gh_mat._euclidean_fallback(all_locs)
                    src = "euclidean"
                    n_gh_pairs = 0

            gh_proof_map[slot_name] = {
                "source":       src,
                "matrix_pairs": n_gh_pairs if src == "graphhopper" else 0,
                "haversine":    0 if src == "graphhopper" else len(all_locs)**2,
                "timestamp":    datetime.now().strftime("%Y-%m-%d %H:%M WIB"),
                "profile":      gh_profile,
            }

            if src == "euclidean":
                st.warning(f"⚠️ [{cfg['label']}] GraphHopper tidak tersedia — fallback Euclidean.")

            # Clustering
            with st.spinner(f"🧬 [{cfg['label']}] K-Medoids clustering …"):
                clusterer = KMedoidsCFRS(
                    locations=all_locs, dist_matrix=dist_mat,
                    fleet=opt_fleet, max_iter=CLUSTERING_MAX_ITER,
                )
                clusters = clusterer.run()

            # GA + TS
            slot_results = []
            with st.spinner(f"🔀 [{cfg['label']}] GA + Tabu Search …"):
                active_clusters = [c for c in clusters if c.customer_indices]
                with ThreadPoolExecutor(max_workers=max(1, len(active_clusters))) as executor:
                    futures = {
                        executor.submit(
                            _optimize_single_cluster,
                            c, all_locs, time_mat, dist_mat, dep_hour, slot_name,
                            max_work_minutes, cross_equity_weight,
                        ): c
                        for c in active_clusters
                    }
                    for future in as_completed(futures):
                        r = future.result()
                        if r is not None:
                            slot_results.append(r)

            all_results[slot_name]  = slot_results
            all_locs_map[slot_name] = all_locs
            progress.progress((si + 1) / total_slots)

        progress.empty()
        st.session_state["all_results"]       = all_results
        st.session_state["all_locs_map"]      = all_locs_map
        st.session_state["gh_proof_map"]      = gh_proof_map
        st.session_state["opt_delivery_date"] = delivery_date_str
        st.session_state["opt_depot_cfg"]     = depot_cfg
        st.session_state["fleet_phone_map"]   = {
            v["id"]: {"phone": v.get("phone", ""), "driver": v.get("driver", "")}
            for v in fleet
        }

        total_routes = sum(len(v) for v in all_results.values())
        st.success(f"✅ Optimasi selesai! {total_routes} rute tersebar di "
                   f"{sum(1 for v in all_results.values() if v)} slot.")

        # Simpan ke DB
        if _DB_AVAILABLE:
            with st.expander("💾 Simpan Hasil ke Database", expanded=True):
                st.caption("Simpan rute pengiriman ke database lokal.")
                sv1, sv2 = st.columns([3, 1])
                save_date_v = sv1.date_input("Tanggal simpan", value=delivery_date,
                                              key="save_db_date")
                if sv2.button("💾 Simpan", width="stretch",
                               type="primary", key="save_to_db_btn"):
                    saved_n = 0
                    for slot_name, cfg in SLOTS.items():
                        results_sl = all_results.get(slot_name, [])
                        locs_sl    = all_locs_map.get(slot_name, [])
                        if not results_sl:
                            continue
                        locs_data = [{"name": l.name, "lat": l.lat,
                                      "lon": l.lon, "demand": l.demand, "address": ""}
                                     for l in locs_sl]
                        try:
                            _save_route_session(
                                session_date=save_date_v.strftime("%Y-%m-%d"),
                                slot=slot_name,
                                departure_hr=cfg["departure"],
                                results=results_sl,
                                all_locs_data=locs_data,
                                json_snapshot=json.dumps(
                                    [{"vehicle_id": r["vehicle_id"], "route": r["route"],
                                      "arrivals": r["arrivals"], "feasible": r["feasible"],
                                      "load": r.get("load", 0)} for r in results_sl],
                                    ensure_ascii=False),
                            )
                            saved_n += 1
                        except Exception as e:
                            st.error(f"Gagal slot {slot_name}: {e}")
                    if saved_n > 0:
                        st.success(f"✅ {saved_n} slot berhasil disimpan ke database untuk tanggal {save_date_v}.")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 2 — HASIL OPTIMASI
    # ══════════════════════════════════════════════════════════════════════════
    with tab_result:
        render_results_tab()

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 3 — PETA RUTE
    # ══════════════════════════════════════════════════════════════════════════
    with tab_map:
        render_map_tab(gh_url, gh_profile, delivery_date_str)

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 4 — EXPORT & WA
    # ══════════════════════════════════════════════════════════════════════════
    with tab_export:
        render_export_tab()


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        print("CLI mode: gunakan streamlit run main.py untuk dashboard")
    else:
        main()
