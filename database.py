"""
database.py — SQLite backend untuk CFRS Katering
Tabel: orders, couriers, routes, route_stops

Fitur:
  - CRUD pesanan (dengan delivery_date agar bisa dilacak maju/mundur)
  - CRUD kurir (plat nomor, nama driver, telepon, tipe kendaraan)
  - Simpan hasil rute optimasi per tanggal
  - Query riwayat & jadwal ke depan
"""

import sqlite3
import json
from pathlib import Path
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

DB_PATH = Path(__file__).parent / "cfrs_katering.db"


# ══════════════════════════════════════════════════════════════════════════════
# ── KONEKSI ──────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


# ══════════════════════════════════════════════════════════════════════════════
# ── DDL (schema) ─────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

DDL = """
-- Kurir/pengemudi
CREATE TABLE IF NOT EXISTS couriers (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    plate         TEXT    NOT NULL UNIQUE,          -- plat nomor
    driver_name   TEXT    NOT NULL,
    phone         TEXT    NOT NULL,                 -- format 628xxx
    vehicle_type  TEXT    NOT NULL DEFAULT 'motor', -- 'motor' | 'mobil'
    vehicle_model TEXT,
    capacity      INTEGER NOT NULL DEFAULT 35,
    cost_per_km   REAL    NOT NULL DEFAULT 1500,
    fixed_cost    REAL    NOT NULL DEFAULT 30000,
    zona          TEXT,
    home_lat      REAL,
    home_lon      REAL,
    is_active     INTEGER NOT NULL DEFAULT 1,       -- 0=nonaktif
    created_at    TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

-- Pesanan
CREATE TABLE IF NOT EXISTS orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    order_code      TEXT    NOT NULL UNIQUE,        -- e.g. "ORD-20240424-001"
    customer        TEXT    NOT NULL,
    phone           TEXT,
    address         TEXT    NOT NULL,
    lat             REAL    NOT NULL,
    lon             REAL    NOT NULL,
    boxes           INTEGER NOT NULL DEFAULT 1,
    delivery_slot   TEXT    NOT NULL DEFAULT 'siang', -- 'siang'|'sore'|'siang+sore'
    delivery_date   TEXT    NOT NULL,               -- ISO YYYY-MM-DD
    notes           TEXT,
    status          TEXT    NOT NULL DEFAULT 'pending',
                                                    -- pending|assigned|delivered|cancelled
    created_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

-- Sesi optimasi (per tanggal + slot)
CREATE TABLE IF NOT EXISTS route_sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_date  TEXT    NOT NULL,                 -- ISO YYYY-MM-DD
    slot          TEXT    NOT NULL,                 -- 'siang'|'sore'
    departure_hr  REAL    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    json_snapshot TEXT                              -- snapshot raw JSON hasil
);

-- Rute per kurir (dalam satu sesi)
CREATE TABLE IF NOT EXISTS route_results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    INTEGER NOT NULL REFERENCES route_sessions(id) ON DELETE CASCADE,
    courier_id    INTEGER REFERENCES couriers(id),
    vehicle_id    TEXT    NOT NULL,                 -- plate / id kendaraan
    total_km      REAL,
    total_box     INTEGER,
    feasible      INTEGER NOT NULL DEFAULT 1,
    fitness       REAL,
    wa_sent       INTEGER NOT NULL DEFAULT 0,       -- 1=sudah dikirim ke WA
    wa_sent_at    TEXT
);

-- Titik-titik stop dalam satu rute
CREATE TABLE IF NOT EXISTS route_stops (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    route_result_id INTEGER NOT NULL REFERENCES route_results(id) ON DELETE CASCADE,
    stop_order      INTEGER NOT NULL,
    order_id        INTEGER REFERENCES orders(id),
    customer_name   TEXT    NOT NULL,
    address         TEXT    NOT NULL,
    lat             REAL    NOT NULL,
    lon             REAL    NOT NULL,
    boxes           INTEGER NOT NULL DEFAULT 1,
    arrival_min     REAL,
    on_time         INTEGER NOT NULL DEFAULT 1
);

-- Indeks
CREATE INDEX IF NOT EXISTS idx_orders_date   ON orders(delivery_date);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_sessions_date ON route_sessions(session_date, slot);
"""


def init_db():
    """Inisialisasi schema. Aman dipanggil berkali-kali (idempotent)."""
    with _get_conn() as conn:
        conn.executescript(DDL)


# ══════════════════════════════════════════════════════════════════════════════
# ── COURIERS ─────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def get_all_couriers(active_only: bool = False) -> List[Dict]:
    with _get_conn() as conn:
        where = "WHERE is_active=1" if active_only else ""
        rows = conn.execute(
            f"SELECT * FROM couriers {where} ORDER BY vehicle_type, driver_name"
        ).fetchall()
    return [dict(r) for r in rows]


def get_courier(courier_id: int) -> Optional[Dict]:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM couriers WHERE id=?", (courier_id,)
        ).fetchone()
    return dict(row) if row else None


def get_courier_by_plate(plate: str) -> Optional[Dict]:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM couriers WHERE plate=?", (plate,)
        ).fetchone()
    return dict(row) if row else None


def upsert_courier(data: Dict) -> int:
    """Insert or update kurir. Return id."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _get_conn() as conn:
        if data.get("id"):
            conn.execute("""
                UPDATE couriers SET
                    plate=?, driver_name=?, phone=?, vehicle_type=?,
                    vehicle_model=?, capacity=?, cost_per_km=?, fixed_cost=?,
                    zona=?, home_lat=?, home_lon=?, is_active=?, updated_at=?
                WHERE id=?
            """, (
                data["plate"], data["driver_name"], data["phone"],
                data.get("vehicle_type", "motor"), data.get("vehicle_model"),
                data.get("capacity", 35), data.get("cost_per_km", 1500),
                data.get("fixed_cost", 30000), data.get("zona"),
                data.get("home_lat"), data.get("home_lon"),
                int(data.get("is_active", 1)), now, data["id"],
            ))
            return data["id"]
        else:
            cur = conn.execute("""
                INSERT INTO couriers
                    (plate, driver_name, phone, vehicle_type, vehicle_model,
                     capacity, cost_per_km, fixed_cost, zona, home_lat, home_lon,
                     is_active, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                data["plate"], data["driver_name"], data["phone"],
                data.get("vehicle_type", "motor"), data.get("vehicle_model"),
                data.get("capacity", 35), data.get("cost_per_km", 1500),
                data.get("fixed_cost", 30000), data.get("zona"),
                data.get("home_lat"), data.get("home_lon"),
                int(data.get("is_active", 1)), now, now,
            ))
            rowid = cur.lastrowid
            assert rowid is not None
            return rowid


def delete_courier(courier_id: int):
    with _get_conn() as conn:
        conn.execute("DELETE FROM couriers WHERE id=?", (courier_id,))


def toggle_courier_active(courier_id: int):
    with _get_conn() as conn:
        conn.execute(
            "UPDATE couriers SET is_active=((is_active+1)%2), updated_at=datetime('now','localtime') WHERE id=?",
            (courier_id,),
        )


# ══════════════════════════════════════════════════════════════════════════════
# ── ORDERS ───────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def _next_order_code(delivery_date: str) -> str:
    """Generate kode unik ORD-YYYYMMDD-NNN."""
    yyyymmdd = delivery_date.replace("-", "")
    with _get_conn() as conn:
        cnt = conn.execute(
            "SELECT COUNT(*) FROM orders WHERE delivery_date=?",
            (delivery_date,),
        ).fetchone()[0]
    return f"ORD-{yyyymmdd}-{cnt+1:03d}"


def get_orders_by_date(delivery_date: str) -> List[Dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM orders WHERE delivery_date=? ORDER BY id",
            (delivery_date,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_orders_range(date_from: str, date_to: str) -> List[Dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM orders WHERE delivery_date BETWEEN ? AND ? ORDER BY delivery_date, id",
            (date_from, date_to),
        ).fetchall()
    return [dict(r) for r in rows]


def get_order(order_id: int) -> Optional[Dict]:
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    return dict(row) if row else None


def insert_order(data: Dict) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    code = data.get("order_code") or _next_order_code(data["delivery_date"])
    with _get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO orders
                (order_code, customer, phone, address, lat, lon,
                 boxes, delivery_slot, delivery_date, notes, status,
                 created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            code, data["customer"], data.get("phone", ""),
            data["address"], float(data["lat"]), float(data["lon"]),
            int(data.get("boxes", 1)),
            data.get("delivery_slot", "siang"),
            data["delivery_date"],
            data.get("notes", ""),
            data.get("status", "pending"),
            now, now,
        ))
        rowid = cur.lastrowid
        assert rowid is not None
        return rowid


def update_order(order_id: int, data: Dict):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _get_conn() as conn:
        conn.execute("""
            UPDATE orders SET
                customer=?, phone=?, address=?, lat=?, lon=?,
                boxes=?, delivery_slot=?, delivery_date=?,
                notes=?, status=?, updated_at=?
            WHERE id=?
        """, (
            data["customer"], data.get("phone", ""),
            data["address"], float(data["lat"]), float(data["lon"]),
            int(data.get("boxes", 1)),
            data.get("delivery_slot", "siang"),
            data["delivery_date"],
            data.get("notes", ""),
            data.get("status", "pending"),
            now, order_id,
        ))


def delete_order(order_id: int):
    with _get_conn() as conn:
        conn.execute("DELETE FROM orders WHERE id=?", (order_id,))


def bulk_insert_orders(orders: List[Dict]) -> int:
    """Insert banyak pesanan sekaligus. Return jumlah yang berhasil."""
    count = 0
    for o in orders:
        try:
            insert_order(o)
            count += 1
        except sqlite3.IntegrityError:
            pass  # skip duplikat order_code
    return count


def update_order_status(order_id: int, status: str):
    with _get_conn() as conn:
        conn.execute(
            "UPDATE orders SET status=?, updated_at=datetime('now','localtime') WHERE id=?",
            (status, order_id),
        )


def count_orders_by_date() -> List[Dict]:
    """Ringkasan jumlah pesanan per tanggal (untuk kalender)."""
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT delivery_date,
                   COUNT(*) as total_orders,
                   SUM(boxes) as total_boxes,
                   SUM(CASE WHEN status='delivered' THEN 1 ELSE 0 END) as delivered,
                   SUM(CASE WHEN status='pending'   THEN 1 ELSE 0 END) as pending
            FROM orders
            GROUP BY delivery_date
            ORDER BY delivery_date
        """).fetchall()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
# ── ROUTE SESSIONS ────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def save_route_session(
    session_date: str,
    slot: str,
    departure_hr: float,
    results: List[Dict],
    all_locs_data: List[Dict],
    json_snapshot: Optional[str] = None,
) -> int:
    """Simpan hasil optimasi ke DB. Return session_id."""
    with _get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO route_sessions (session_date, slot, departure_hr, json_snapshot)
            VALUES (?,?,?,?)
        """, (session_date, slot, departure_hr, json_snapshot))
        sid = cur.lastrowid
        assert sid is not None
        session_id = sid

        for r in results:
            # Cari courier_id berdasarkan vehicle_id (plate)
            c_row = conn.execute(
                "SELECT id FROM couriers WHERE plate=?", (r["vehicle_id"],)
            ).fetchone()
            courier_id = c_row["id"] if c_row else None

            rcur = conn.execute("""
                INSERT INTO route_results
                    (session_id, courier_id, vehicle_id, total_km,
                     total_box, feasible, fitness)
                VALUES (?,?,?,?,?,?,?)
            """, (
                session_id, courier_id, r["vehicle_id"],
                r.get("total_km"), r.get("load"),
                int(r.get("feasible", True)), r.get("fitness"),
            ))
            rr_id = rcur.lastrowid

            # Stop-stop
            route_indices = r.get("route", [])
            arrivals      = r.get("arrivals", [])
            for stop_num, (loc_idx, arr) in enumerate(zip(route_indices, arrivals), 1):
                loc = all_locs_data[loc_idx] if loc_idx < len(all_locs_data) else {}
                # Cari order_id
                o_row = conn.execute(
                    "SELECT id FROM orders WHERE customer=? AND delivery_date=?",
                    (loc.get("name", ""), session_date),
                ).fetchone()
                conn.execute("""
                    INSERT INTO route_stops
                        (route_result_id, stop_order, order_id,
                         customer_name, address, lat, lon, boxes,
                         arrival_min, on_time)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                """, (
                    rr_id, stop_num,
                    o_row["id"] if o_row else None,
                    loc.get("name", ""), loc.get("address", ""),
                    loc.get("lat", 0), loc.get("lon", 0),
                    loc.get("demand", 0),
                    float(arr), int(arr <= 180),
                ))
    return session_id


def get_sessions_by_date(session_date: str) -> List[Dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM route_sessions WHERE session_date=? ORDER BY slot",
            (session_date,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_route_results(session_id: int) -> List[Dict]:
    with _get_conn() as conn:
        rr = conn.execute(
            "SELECT * FROM route_results WHERE session_id=? ORDER BY id",
            (session_id,),
        ).fetchall()
        results = []
        for r in rr:
            rd = dict(r)
            stops = conn.execute(
                "SELECT * FROM route_stops WHERE route_result_id=? ORDER BY stop_order",
                (r["id"],),
            ).fetchall()
            rd["stops"] = [dict(s) for s in stops]
            results.append(rd)
    return results


def mark_wa_sent(route_result_id: int):
    with _get_conn() as conn:
        conn.execute("""
            UPDATE route_results
            SET wa_sent=1, wa_sent_at=datetime('now','localtime')
            WHERE id=?
        """, (route_result_id,))


def get_session_history(limit: int = 90) -> List[Dict]:
    """Riwayat sesi optimasi (untuk timeline)."""
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT s.session_date, s.slot, s.departure_hr, s.created_at,
                   COUNT(rr.id) as n_vehicles,
                   SUM(rr.total_box) as total_boxes,
                   SUM(rr.total_km) as total_km,
                   SUM(rr.feasible) as feasible_count
            FROM route_sessions s
            LEFT JOIN route_results rr ON rr.session_id = s.id
            GROUP BY s.id
            ORDER BY s.session_date DESC, s.slot
            LIMIT ?
        """, (limit,)).fetchall()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
# ── WHATSAPP HELPERS ─────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def build_wa_message(
    courier: Dict,
    stops: List[Dict],
    slot_label: str,
    dep_time: str,
    depot: Dict,
) -> str:
    """
    Buat teks pesan WhatsApp dengan urutan rute + link Google Maps tiap stop.
    """
    nama    = courier.get("driver_name", "Kurir")
    plat    = courier.get("plate", "")
    n_stop  = len(stops)
    total_b = sum(s.get("boxes", 0) for s in stops)

    lines = [
        f"🍱 *RUTE PENGIRIMAN KATERING*",
        f"📅 {slot_label} · Berangkat {dep_time}",
        f"🏍️ *{nama}* ({plat})",
        f"📦 {n_stop} stop · {total_b} box",
        "",
        f"🏠 *START* — {depot.get('name', 'Dapur')}",
        f"   📍 https://maps.google.com/?q={depot.get('lat', 0)},{depot.get('lon', 0)}",
        "─────────────────────────",
    ]

    for i, stop in enumerate(stops, 1):
        lat   = stop.get("lat", 0)
        lon   = stop.get("lon", 0)
        name  = stop.get("customer_name", stop.get("name", ""))
        addr  = stop.get("address", "")
        boxes = stop.get("boxes", stop.get("demand", 0))
        arr   = stop.get("arrival_min", 0)
        flag  = "⚠️" if not stop.get("on_time", True) else "✅"

        phone  = stop.get("phone", "")
        gmaps_url = f"https://maps.google.com/?q={lat},{lon}"
        lines += [
            f"{flag} *Stop {i}* — {name}",
            f"   📦 {boxes} box · ETA +{arr:.0f} mnt",
            f"   📍 {gmaps_url}",
        ]
        if phone:
            lines.append(f"   📱 {phone}")
        if addr:
            lines.append(f"   🏠 {addr[:60]}{'…' if len(addr)>60 else ''}")
        lines.append("")

    # Link rute lengkap Google Maps (waypoints)
    gmaps_full = _build_gmaps_full_url(depot, stops)
    lines += [
        "─────────────────────────",
        f"🗺️ *Rute Lengkap GMaps:*",
        gmaps_full,
        "",
        "_Pesan otomatis dari CFRS Katering_",
    ]
    return "\n".join(lines)


def _build_gmaps_full_url(depot: Dict, stops: List[Dict]) -> str:
    """
    Google Maps Directions URL dengan origin, destination, waypoints.
    Maks 8 waypoint di GMaps (free), lebih dari itu tetap valid di browser.
    Format: origin → waypoints → destination (kembali ke depot).
    """
    origin = f"{depot.get('lat', 0)},{depot.get('lon', 0)}"
    dest   = origin  # kembali ke dapur

    coords = [f"{s.get('lat',0)},{s.get('lon',0)}" for s in stops]
    if not coords:
        return f"https://maps.google.com/?q={origin}"

    if len(coords) == 1:
        waypoints = ""
        destination = coords[0]
    else:
        waypoints   = "|".join(coords[:-1])
        destination = coords[-1]

    url = (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={origin}"
        f"&destination={destination}"
        f"&travelmode=driving"
    )
    if waypoints:
        url += f"&waypoints={waypoints}"
    return url


def build_wa_link(phone: str, message: str) -> str:
    """
    Return URL wa.me yang siap dibuka di browser / diklik.
    phone format: 628xxx (tanpa +, tanpa spasi)
    """
    import urllib.parse
    phone = phone.strip().lstrip("+").replace(" ", "").replace("-", "")
    encoded = urllib.parse.quote(message)
    return f"https://wa.me/{phone}?text={encoded}"


# ══════════════════════════════════════════════════════════════════════════════
# ── INISIALISASI OTOMATIS ─────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

init_db()
