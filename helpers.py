"""
helpers.py — Konverter DataFrame, builder teks WA/GMaps, pengecekan GraphHopper,
             dan generator markup HTML untuk komponen UI dashboard CFRS.
"""

import logging
import requests
import pandas as pd
from datetime import date, datetime, timedelta
from urllib.parse import quote

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# ── Konverter DataFrame ──────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def sample_orders_to_df(orders: list, default_date: str = "") -> pd.DataFrame:
    rows = []
    for o in orders:
        rows.append({
            "id":            o.get("id") or o.get("order_code", ""),
            "customer":      o["customer"],
            "phone":         o.get("phone", ""),
            "address":       o["address"],
            "lat":           o["lat"],
            "lon":           o["lon"],
            "boxes":         o.get("boxes", 1),
            "delivery_slot": o.get("delivery_slot", "siang"),
            "delivery_date": o.get("delivery_date", default_date),
        })
    return pd.DataFrame(rows)


def db_orders_to_df(orders: list) -> pd.DataFrame:
    rows = []
    for o in orders:
        rows.append({
            "id":            o.get("order_code", str(o["id"])),
            "customer":      o["customer"],
            "phone":         o.get("phone", ""),
            "address":       o["address"],
            "lat":           float(o["lat"]),
            "lon":           float(o["lon"]),
            "boxes":         int(o["boxes"]),
            "delivery_slot": o.get("delivery_slot", "siang"),
            "delivery_date": o.get("delivery_date", ""),
        })
    return pd.DataFrame(rows)


def couriers_to_fleet(couriers: list) -> list:
    fleet = []
    for c in couriers:
        fleet.append({
            "id":       c["plate"],
            "type":     c["vehicle_type"],
            "capacity": int(c["capacity"]),
            "driver":   c["driver_name"],
            "phone":    c["phone"],
        })
    return fleet


def fleet_to_df(fleet: list) -> pd.DataFrame:
    """Konversi list fleet dict → DataFrame untuk data_editor sidebar."""
    rows = []
    for v in fleet:
        rows.append({
            "Plat/ID": v.get("id", ""),
            "Driver":  v.get("driver", v.get("id", "")),
            "Tipe":    v.get("type", "motor"),
            "Box":     int(v.get("capacity", 35)),
            "No. HP":  v.get("phone", ""),
        })
    return pd.DataFrame(rows)


def df_to_fleet(df: pd.DataFrame) -> list:
    """Konversi DataFrame editor → list fleet dict (tahan terhadap row kosong)."""
    fleet = []
    for _, row in df.iterrows():
        plat = str(row.get("Plat/ID", "") or "")
        if not plat.strip():
            continue
        fleet.append({
            "id":       plat.strip(),
            "driver":   str(row.get("Driver", plat) or "").strip(),
            "type":     str(row.get("Tipe", "motor") or "motor"),
            "capacity": int(row.get("Box", 35) or 35),
            "phone":    str(row.get("No. HP", "") or ""),
        })
    return fleet


# ══════════════════════════════════════════════════════════════════════════════
# ── Builder Teks WhatsApp & GMaps URL ───────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def build_wa_text(driver_name: str, vehicle_id: str, slot_label: str,
                  dep_time: str, stops: list, depot: dict,
                  total_km: float, delivery_date: str = "",
                  gmaps_full_url: str = "") -> str:
    """Susun teks pesan WA rute untuk satu driver."""
    date_line = f"\n📅 Tanggal   : *{delivery_date}*" if delivery_date else ""
    lines = [
        f"🍱 *Rute Pengiriman — {slot_label}*",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"Halo *{driver_name}*, ini rute kamu hari ini:{date_line}",
        f"",
        f"🚀 Berangkat : *{dep_time} WIB*",
        f"🏠 Depot     : {depot.get('name','Dapur')}",
        f"📦 Total     : {len(stops)} stop · {sum(s.get('demand',0) for s in stops)} box",
        f"🛣️  Estimasi  : {total_km:.1f} km",
        f"",
        f"*Daftar Stop:*",
    ]
    for s in stops:
        eta_str = s.get("eta", "")
        late    = " ⚠️" if not s.get("on_time", True) else ""
        gmaps   = f"https://maps.google.com/?q={s['lat']},{s['lon']}"
        phone   = f"\n   📱 {s['phone']}" if s.get("phone") else ""
        lines.append(
            f"{s['stop']}. *{s['name']}*\n"
            f"   📦 {s.get('demand',0)} box  ⏱ ~{eta_str}{late}{phone}\n"
            f"   📍 {gmaps}"
        )
    if gmaps_full_url:
        lines += [
            "",
            f"🗺️ *Rute Lengkap Google Maps:*",
            f"{gmaps_full_url}",
        ]
    lines += ["", "Selamat bertugas! 💪"]
    return "\n".join(lines)


def gmaps_route_url(depot: dict, stops: list) -> str:
    if not stops:
        return ""
    origin = f"{depot['lat']},{depot['lon']}"
    dest   = f"{stops[-1]['lat']},{stops[-1]['lon']}"
    wps    = "|".join(f"{s['lat']},{s['lon']}" for s in stops[:-1]) if len(stops) > 1 else ""
    url    = (f"https://www.google.com/maps/dir/?api=1"
              f"&origin={origin}&destination={dest}&travelmode=driving")
    if wps:
        url += f"&waypoints={wps}"
    return url


# ══════════════════════════════════════════════════════════════════════════════
# ── GraphHopper Helpers ─────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def check_gh(gh_url: str) -> bool:
    try:
        r = requests.get(f"{gh_url.rstrip('/')}/health", timeout=3)
        return r.status_code == 200
    except Exception as e:
        logger.warning("GH health check gagal: %s", e)
        return False


def fetch_route_geometry(gh_url: str, profile: str, depot, locations, route) -> list | None:
    points = [f"{depot.lat},{depot.lon}"]
    for ci in route:
        loc = locations[ci]
        points.append(f"{loc.lat},{loc.lon}")
    points.append(f"{depot.lat},{depot.lon}")
    try:
        resp = requests.get(
            f"{gh_url.rstrip('/')}/route",
            params={"profile": profile, "point": points,
                    "instructions": "false", "calc_points": "true",
                    "points_encoded": "false"},
            timeout=30,
        )
        resp.raise_for_status()
        path = resp.json().get("paths", [{}])[0]
        geom = path.get("points")
        if geom and "coordinates" in geom:
            return geom["coordinates"]
    except Exception as e:
        logger.warning("GH route geometry gagal: %s", e)
    return None


# ══════════════════════════════════════════════════════════════════════════════
# ── Markup HTML snippet generators ───────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def html_kpi_card(val, lbl: str, color: str = "#4361EE") -> str:
    return (
        f'<div class="kpi-card" style="border-left: 4px solid {color}">'
        f'<div class="kpi-val">{val}</div>'
        f'<div class="kpi-lbl">{lbl}</div>'
        f'</div>'
    )


def html_route_card(vid: str, vehicle_type: str, color: str,
                    feasible: bool, load: int, capacity: int,
                    dep_str: str, done_min: float, n_stops: int,
                    total_km: float, max_arr: float) -> str:
    vc = "🏍️" if vehicle_type == "motor" else "🚗"
    util_pct = min(100, int(load / capacity * 100)) if capacity > 0 else 0
    util_color = (
        "#2EC4B6" if util_pct < 70 else
        "#FFB703" if util_pct < 90 else "#FF6B6B"
    )
    badge_cls  = "badge-ok" if feasible else "badge-late"
    badge_text = "✅ FEASIBLE" if feasible else "⛔ TERLAMBAT"
    return (
        f'<div class="route-card" style="border-top: 4px solid {color};">'
        f'<div class="route-card-header">'
        f'<span class="route-card-title">'
        f'{vc} {vid}</span>'
        f'<span class="route-badge {badge_cls}">{badge_text}</span>'
        f'</div>'
        f'<div class="util-bar-wrap">'
        f'<div class="util-bar-fill" '
        f'style="width:{util_pct}%;background:{util_color}"></div>'
        f'</div>'
        f'<div style="font-size:.7rem;color:#6b7280;margin-bottom:8px">'
        f'Kapasitas {load}/{capacity} box ({util_pct}%)</div>'
        f'<div class="meta-row">'
        f'<span class="meta-item">⏰ Berangkat <b>{dep_str}</b></span>'
        f'<span class="meta-item">🏁 Selesai <b>+{done_min:.0f}m</b></span>'
        f'<span class="meta-item">📍 <b>{n_stops}</b> stop</span>'
        f'<span class="meta-item">🛣️ <b>{total_km:.1f} km</b></span>'
        f'<span class="meta-item">⏱ Maks <b>{max_arr:.0f}m</b></span>'
        f'</div>'
        f'</div>'
    )


def html_gh_proof(slot_name: str, proof: dict) -> str:
    src_txt = (
        "✅ GraphHopper (jarak nyata)"
        if proof.get("source") == "graphhopper"
        else "⚠️ Euclidean fallback"
    )
    return (
        f'<div class="gh-proof">'
        f'<div style="font-size:.75rem;color:#6b7280;margin-bottom:6px">'
        f'📡 GH PROOF — {slot_name.upper()}</div>'
        f'<div class="gh-proof-row">'
        f'<span class="gh-proof-item">Sumber: <b>{src_txt}</b></span>'
        f'<span class="gh-proof-item">Matrix pairs: '
        f'<b>{proof.get("matrix_pairs",0)}</b></span>'
        f'<span class="gh-proof-item">Haversine: '
        f'<b>{proof.get("haversine",0)}</b></span>'
        f'<span class="gh-proof-item">Profil: '
        f'<b>{proof.get("profile","")}</b></span>'
        f'<span class="gh-proof-item">Timestamp: '
        f'<b>{proof.get("timestamp","")}</b></span>'
        f'</div></div>'
    )
