"""
graphhopper.py — Integrasi GraphHopper API (localhost)
Menghasilkan matriks jarak (km) dan waktu tempuh (menit) antar semua titik.
Fallback: matrix → spt → route → euclidean
"""

import hashlib
import csv
import io
import json
import os
import requests
import numpy as np
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Tuple
from dataclasses import dataclass

from config import GRAPHHOPPER_URL, VEHICLE_PROFILE

logger = logging.getLogger(__name__)

# ── Cache matriks jarak (file-based, deterministic) ─────────────────────────
_CACHE_DIR = Path(__file__).parent / ".matrix_cache"


def _matrix_cache_key(locations: List["Location"], profile: str) -> str:
    """SHA-256 hash dari koordinat terurut + profile — deterministic."""
    pts = sorted((round(loc.lat, 6), round(loc.lon, 6)) for loc in locations)
    payload = json.dumps({"pts": pts, "profile": profile}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _matrix_cache_path(cache_key: str) -> Path:
    return _CACHE_DIR / f"{cache_key}.npz"


def _matrix_cache_load(cache_key: str) -> Tuple[np.ndarray, np.ndarray] | None:
    path = _matrix_cache_path(cache_key)
    if not path.exists():
        return None
    try:
        data = np.load(path)
        logger.info("Matriks dimuat dari cache (%s …)", cache_key[:12])
        return data["dist"], data["time"]
    except Exception:
        return None


def _matrix_cache_save(cache_key: str, dist: np.ndarray, time: np.ndarray):
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _matrix_cache_path(cache_key)
    # np.savez_compressed langsung ke path final (tidak perlu atomic rename)
    np.savez_compressed(path, dist=dist, time=time)
    logger.info("Matriks disimpan ke cache (%s …)", cache_key[:12])


@dataclass
class Location:
    """Representasi satu titik (dapur atau pelanggan)."""
    id: str
    name: str
    lat: float
    lon: float
    demand: int = 0          # jumlah box yang dipesan (0 untuk dapur)
    phone: str = ""          # nomor HP pelanggan


class GraphHopperMatrix:
    """
    Wrapper untuk GraphHopper API.
    Mengembalikan distance_matrix (km) dan time_matrix (menit).
    Mencoba beberapa strategi fallback jika endpoint tidak tersedia.
    """

    def __init__(self, base_url: str = GRAPHHOPPER_URL, profile: str = VEHICLE_PROFILE):
        self.base_url = base_url.rstrip("/")
        self.profile = profile

    def _points_json(self, locations: List[Location]) -> list:
        return [[loc.lon, loc.lat] for loc in locations]

    # ── Strategi 1: Matrix API ──────────────────────────────────────────────

    def _try_matrix(self, locations: List[Location]) -> Tuple[np.ndarray, np.ndarray] | None:
        """POST /matrix — satu panggilan untuk seluruh matriks."""
        payload = {
            "profile": self.profile,
            "from_points": self._points_json(locations),
            "to_points": self._points_json(locations),
            "out_arrays": ["distances", "times"],
            "fail_fast": False,
        }
        try:
            resp = requests.post(
                f"{self.base_url}/matrix",
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            dist = np.array(data["distances"], dtype=float) / 1000.0
            time = np.array(data["times"], dtype=float) / 60_000.0
            np.fill_diagonal(dist, 0.0)
            np.fill_diagonal(time, 0.0)
            return dist, time
        except Exception:
            return None

    # ── Strategi 2: SPT (Shortest Path Tree) ────────────────────────────────

    def _try_spt(self, locations: List[Location]) -> Tuple[np.ndarray, np.ndarray] | None:
        """GET /spt — satu panggilan per titik sumber → N panggilan total.
        GH 11.0 mengembalikan CSV, bukan JSON — di-parse manual."""
        n = len(locations)
        dist = np.zeros((n, n))
        time = np.zeros((n, n))

        for i, src in enumerate(locations):
            params = {
                "profile": self.profile,
                "point": f"{src.lat},{src.lon}",
                "columns": "node_id,distance,time",
            }
            try:
                resp = requests.get(
                    f"{self.base_url}/spt",
                    params=params,
                    timeout=60,
                )
                resp.raise_for_status()
                # GH 11.0 mengembalikan CSV — parse manual
                csv_text = resp.text
                node_data: dict[int, tuple[float, float]] = {}
                reader = csv.reader(io.StringIO(csv_text))
                header = next(reader, [])
                # Cari indeks kolom
                try:
                    id_col = header.index("node_id")
                    dist_col = header.index("distance")
                    time_col = header.index("time")
                except ValueError:
                    logger.warning("SPT CSV tidak memiliki kolom yang diharapkan: %s", header)
                    return None
                for row in reader:
                    if len(row) < 3:
                        continue
                    try:
                        nid = int(row[id_col])
                        d_m = float(row[dist_col])
                        t_ms = float(row[time_col])
                        node_data[nid] = (d_m / 1000.0, t_ms / 60_000.0)
                    except (ValueError, IndexError):
                        continue
                if not node_data:
                    return None

                # Cocokkan dengan semua destinasi (pakai /nearest → node_id)
                for j, dst in enumerate(locations):
                    if i == j:
                        continue
                    params_n = {
                        "profile": self.profile,
                        "point": f"{dst.lat},{dst.lon}",
                    }
                    try:
                        resp_n = requests.get(
                            f"{self.base_url}/nearest",
                            params=params_n,
                            timeout=10,
                        )
                        resp_n.raise_for_status()
                        nearest = resp_n.json()
                        # GH 11.0: /nearest tidak mengembalikan node_id
                        nid = nearest.get("node_id") or nearest.get("id")
                        if nid is None:
                            # GH 11.0 tidak support — SPT tidak bisa digunakan
                            resp.close()
                            resp_n.close()
                            logger.info(
                                "SPT tidak kompatibel: /nearest tidak mengembalikan "
                                "node_id (GH 11.0). Lanjut ke /route."
                            )
                            return None
                        if nid in node_data:
                            d_km, t_min = node_data[nid]
                            dist[i][j] = d_km
                            time[i][j] = t_min
                    except Exception:
                        pass
            except Exception:
                return None

        return dist, time

    # ── Strategi 3: Route point-to-point (paralel) ───────────────────────────

    def _try_route_ptp(self, locations: List[Location]) -> Tuple[np.ndarray, np.ndarray] | None:
        """POST /route — N² panggilan paralel dengan ThreadPoolExecutor."""
        n = len(locations)
        dist = np.zeros((n, n))
        time = np.zeros((n, n))
        base = self.base_url
        profile = self.profile

        def _fetch_one(i: int, j: int) -> Tuple[int, int, float, float] | None:
            """Ambil rute untuk satu pasangan (i,j). Return (i,j,dist_km,time_min)."""
            src = locations[i]
            dst = locations[j]
            try:
                resp = requests.get(
                    f"{base}/route",
                    params={
                        "profile": profile,
                        "point": [f"{src.lat},{src.lon}", f"{dst.lat},{dst.lon}"],
                        "instructions": "false",
                        "calc_points": "false",
                    },
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                path = data.get("paths", [{}])[0]
                d_km = path.get("distance", 0) / 1000.0
                t_min = path.get("time", 0) / 60_000.0
                return (i, j, d_km, t_min)
            except Exception:
                return None

        # Bangun daftar semua pasangan (i,j) dengan i ≠ j
        pairs = [(i, j) for i in range(n) for j in range(n) if i != j]
        logger.info(
            "  /route point-to-point: %d pasangan, paralel 16 thread …",
            len(pairs),
        )

        completed = 0
        max_workers = 16
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_fetch_one, i, j): (i, j) for i, j in pairs}
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    i, j, d_km, t_min = result
                    dist[i][j] = d_km
                    time[i][j] = t_min
                completed += 1
                if completed % 500 == 0:
                    logger.debug("  /route progress: %d/%d", completed, len(pairs))

        return dist, time

    # ── Fallback: Euclidean ─────────────────────────────────────────────────

    @staticmethod
    def _euclidean_fallback(locations: List[Location]) -> Tuple[np.ndarray, np.ndarray]:
        n = len(locations)
        R = 6371.0  # radius bumi (km)
        dist = np.zeros((n, n))
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                lat1, lon1 = np.radians(locations[i].lat), np.radians(locations[i].lon)
                lat2, lon2 = np.radians(locations[j].lat), np.radians(locations[j].lon)
                dlat, dlon = lat2 - lat1, lon2 - lon1
                a = np.sin(dlat/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin(dlon/2)**2
                dist[i][j] = 2 * R * np.arcsin(np.sqrt(a))
        dist *= 1.3  # koreksi jalan
        speed_kmpm = 30.0 / 60.0
        time = dist / speed_kmpm
        logger.warning("Menggunakan matriks EUCLIDEAN (fallback). Akurasi terbatas.")
        return dist, time

    # ── Main ────────────────────────────────────────────────────────────────

    def get_matrix(
        self,
        locations: List[Location],
        profile: str | None = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Dapatkan matriks jarak dan waktu, mencoba beberapa strategi.
        Hasil di-cache berdasarkan hash koordinat + profile (deterministic).
        Returns: distance_matrix (km), time_matrix (menit)
        """
        if profile:
            self.profile = profile

        n = len(locations)
        cache_key = _matrix_cache_key(locations, self.profile)

        # ── Cek cache terlebih dahulu ──────────────────────────────────────
        cached = _matrix_cache_load(cache_key)
        if cached is not None:
            return cached

        logger.info(f"Mengambil matriks untuk {n} titik …")
        result = None

        # Strategi 1: Matrix API
        result = self._try_matrix(locations)
        if result is not None:
            logger.info("Matriks via /matrix OK.")
        else:
            # Strategi 2: SPT (N panggilan)
            logger.info("/matrix tidak tersedia, mencoba /spt …")
            result = self._try_spt(locations)
            if result is not None:
                logger.info("Matriks via /spt OK.")

        if result is None:
            # Strategi 3: Route point-to-point (N² panggilan)
            logger.info("/spt tidak tersedia, mencoba /route point-to-point …")
            result = self._try_route_ptp(locations)
            if result is not None:
                logger.info("Matriks via /route point-to-point OK.")

        if result is None:
            # Strategi 4: Euclidean — TIDAK di-cache (fallback non-deterministik)
            logger.warning("Semua API gagal, fallback ke Euclidean.")
            return self._euclidean_fallback(locations)

        # ── Simpan ke cache ────────────────────────────────────────────────
        dist, time = result
        _matrix_cache_save(cache_key, dist, time)
        return result
