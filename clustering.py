"""
clustering.py — Tahap "Cluster First" menggunakan K-Medoids Termodifikasi
                dengan Himpunan Tabu kapasitas (35 box per motor).

Logika utama:
  1. Tentukan jumlah klaster awal = jumlah motor
  2. Gunakan K-Medoids (bukan K-Means) agar pusat klaster selalu berupa
     lokasi nyata (bukan titik fiktif di tengah sungai / jalan tol)
  3. Terapkan Himpunan Tabu R: tolak penambahan pelanggan jika kapasitas terlampaui
  4. Jika ada pelanggan yang tidak bisa masuk motor manapun → alihkan ke mobil
"""

import numpy as np
import random
import logging
from typing import List, Dict, Tuple, Optional
from copy import deepcopy

from sklearn.cluster import KMeans  # inisialisasi medoid dengan K-Means++

from config import FLEET, COMMON_DUE_DATE_MINUTES, CLUSTERING_LOAD_BIAS
from graphhopper import Location

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
class Cluster:
    """Representasi satu klaster (satu kendaraan + daftar pelanggannya)."""

    def __init__(self, vehicle: Dict, medoid_idx: int):
        self.vehicle_id   = vehicle["id"]
        self.vehicle_type = vehicle["type"]
        self.capacity     = vehicle["capacity"]
        self.medoid_idx   = medoid_idx      # indeks lokasi yang jadi pusat klaster
        self.customer_indices: List[int] = []
        self.total_load   = 0

    def can_add(self, demand: int) -> bool:
        """Cek apakah penambahan pesanan masih dalam batas kapasitas (Tabu Set R)."""
        return self.total_load + demand <= self.capacity

    def add_customer(self, idx: int, demand: int):
        self.customer_indices.append(idx)
        self.total_load += demand

    def remove_customer(self, idx: int, demand: int):
        self.customer_indices.remove(idx)
        self.total_load -= demand

    def __repr__(self):
        return (f"Cluster({self.vehicle_id}, load={self.total_load}/"
                f"{self.capacity}, customers={self.customer_indices})")


# ─────────────────────────────────────────────────────────────────────────────
class KMedoidsCFRS:
    """
    K-Medoids termodifikasi untuk Cluster First dengan batasan kapasitas kendaraan.

    Parameters
    ----------
    locations      : list of Location  — indeks 0 = dapur/depot
    dist_matrix    : np.ndarray (N×N)  — matriks jarak GraphHopper (km)
    fleet          : list of dict      — konfigurasi armada dari config.py
    max_iter       : int               — maks iterasi K-Medoids
    """

    def __init__(
        self,
        locations: List[Location],
        dist_matrix: np.ndarray,
        fleet: Optional[List[Dict]] = None,
        max_iter: int = 100,
    ):
        self.locations   = locations
        self.dist        = dist_matrix
        self.fleet       = fleet or FLEET
        self.max_iter    = max_iter

        # Pisahkan armada motor dan mobil
        self.motors = [v for v in self.fleet if v["type"] == "motor"]
        self.trucks = [v for v in self.fleet if v["type"] == "mobil"]

        # Indeks pelanggan (bukan depot → indeks 0 dikecualikan)
        self.customer_indices = list(range(1, len(locations)))

    # ──────────────────────────────────────────────────────────────────────────
    def run(self) -> List[Cluster]:
        """
        Jalankan algoritma K-Medoids dan kembalikan daftar Cluster.
        """
        n_motor = len(self.motors)
        customers = self.customer_indices[:]

        # ── Inisialisasi medoid dengan K-Means++ (bukan random) ─────────
        if len(customers) < n_motor:
            raise ValueError("Jumlah pelanggan lebih sedikit dari jumlah motor.")

        # Ekstrak koordinat pelanggan untuk clustering
        coords = np.array([
            [self.locations[i].lat, self.locations[i].lon]
            for i in customers
        ])
        km = KMeans(
            n_clusters=n_motor,
            init="k-means++",
            n_init=10,
            max_iter=50,
            random_state=42,
        )
        km.fit(coords)

        # Untuk setiap centroid K-Means, cari pelanggan terdekat sebagai medoid
        medoid_indices = []
        for center in km.cluster_centers_:
            dists = np.linalg.norm(coords - center, axis=1)
            nearest_local = int(np.argmin(dists))
            medoid_indices.append(customers[nearest_local])

        # Pastikan tidak ada duplikat medoid
        if len(set(medoid_indices)) < n_motor:
            # Fallback: random jika K-Means menghasilkan duplikat
            medoid_indices = random.sample(customers, n_motor)

        clusters = self._build_clusters(medoid_indices, customers)

        logger.info(f"K-Medoids mulai: {n_motor} motor klaster, "
                    f"{len(customers)} pelanggan")

        # ── Iterasi K-Medoids ──────────────────────────────────────────────
        for iteration in range(self.max_iter):
            improved = False

            # Coba ganti setiap medoid dengan pelanggan lain di klaster-nya
            for c in clusters:
                best_medoid  = c.medoid_idx
                best_cost    = self._cluster_cost(c)

                for candidate in c.customer_indices:
                    if candidate == c.medoid_idx:
                        continue
                    old_medoid   = c.medoid_idx
                    c.medoid_idx = candidate
                    new_cost     = self._cluster_cost(c)
                    if new_cost < best_cost:
                        best_cost   = new_cost
                        best_medoid = candidate
                        improved    = True
                    else:
                        c.medoid_idx = old_medoid   # kembalikan

                c.medoid_idx = best_medoid

            # Realokasi pelanggan ke medoid terdekat (dengan cek kapasitas)
            clusters = self._reallocate(clusters, customers)

            if not improved:
                logger.debug(f"K-Medoids konvergen pada iterasi {iteration + 1}")
                break

        # ── Workload Rebalancing: seimbangkan beban antar motor ────────────
        clusters = self._rebalance_workload(clusters)

        # ── Pelanggan yang tidak muat di motor → alihkan ke mobil ─────────
        unassigned = self._find_unassigned(clusters, customers)
        if unassigned:
            clusters = self._assign_to_trucks(clusters, unassigned)

        self._log_summary(clusters)
        return clusters

    # ──────────────────────────────────────────────────────────────────────────
    def _build_clusters(self, medoid_indices: List[int], customers: List[int]) -> List[Cluster]:
        """Buat klaster dari medoid awal, lalu alokasikan pelanggan."""
        clusters = []
        for motor, medoid in zip(self.motors, medoid_indices):
            clusters.append(Cluster(motor, medoid))
        return self._reallocate(clusters, customers)

    # ──────────────────────────────────────────────────────────────────────────
    def _cluster_cost(self, cluster: Cluster) -> float:
        """Total jarak semua pelanggan ke medoid klaster (fungsi biaya intra-klaster)."""
        if not cluster.customer_indices:
            return 0.0
        m = cluster.medoid_idx
        return sum(self.dist[m][j] for j in cluster.customer_indices)

    # ──────────────────────────────────────────────────────────────────────────
    def _reallocate(
        self, clusters: List[Cluster], customers: List[int]
    ) -> List[Cluster]:
        """
        Realokasi setiap pelanggan ke klaster yang medoid-nya paling dekat,
        dengan mematuhi batasan kapasitas (Himpunan Tabu R).
        """
        # Reset klaster (pertahankan medoid dan kendaraan)
        for c in clusters:
            c.customer_indices = []
            c.total_load = 0

        # Urutkan pelanggan dari yang paling "sulit ditempatkan" (demand terbesar)
        sorted_customers = sorted(
            customers,
            key=lambda i: self.locations[i].demand,
            reverse=True,
        )

        unassigned = []
        for idx in sorted_customers:
            demand = self.locations[idx].demand

            # Cari klaster motor terdekat yang masih ada ruang
            # Load-aware: klaster yang sudah berat "tampak lebih jauh"
            motor_clusters = [c for c in clusters
                              if c.vehicle_type == "motor"]
            motor_clusters.sort(key=lambda c:
                self.dist[c.medoid_idx][idx] *
                (1.0 + CLUSTERING_LOAD_BIAS * c.total_load / max(1, c.capacity)))

            placed = False
            for c in motor_clusters:
                if c.can_add(demand):          # Cek Tabu Set R
                    c.add_customer(idx, demand)
                    placed = True
                    break

            if not placed:
                unassigned.append(idx)

        # Tambahkan medoid ke klaster-nya sendiri (jika belum ada)
        for c in clusters:
            if c.medoid_idx not in c.customer_indices:
                demand = self.locations[c.medoid_idx].demand
                if c.can_add(demand):
                    c.add_customer(c.medoid_idx, demand)

        # Simpan unassigned di atribut sementara untuk diproses nanti
        self._unassigned_buffer = unassigned
        return clusters

    # ──────────────────────────────────────────────────────────────────────────
    def _rebalance_workload(self, clusters: List[Cluster]) -> List[Cluster]:
        """
        Post-clustering workload rebalancing antar motor.
        HANYA pindahkan pelanggan yang LEBIH DEKAT ke medoid target
        (gain > 0) — ini memperbaiki "misclassification" dari alokasi awal
        sekaligus menyeimbangkan beban, tanpa menambah tumpang tindih rute.
        """
        motor_clusters = [c for c in clusters if c.vehicle_type == "motor"]
        if len(motor_clusters) < 2:
            return clusters

        loads = [c.total_load for c in motor_clusters]
        avg_load = sum(loads) / len(loads)
        if avg_load == 0:
            return clusters
        std_load = float(np.std(loads))
        cv = std_load / avg_load

        if cv < 0.25:
            logger.debug("Workload sudah seimbang (CV=%.3f < 0.25)", cv)
            return clusters

        logger.info(
            "Workload rebalancing: CV=%.3f (threshold 0.25), "
            "loads=%s, avg=%.1f",
            cv, loads, avg_load,
        )

        max_iter = 100
        for iteration in range(max_iter):
            motor_clusters.sort(key=lambda c: c.total_load, reverse=True)
            moved = False

            for donor in motor_clusters:
                donor_surplus = donor.total_load - avg_load
                if donor_surplus <= 0:
                    continue

                # Cari pelanggan yang "salah klaster":
                # lebih dekat ke medoid receiver daripada ke medoid donor (gain > 0)
                best_candidate = None
                best_gain = -999.0
                best_receiver = None

                for idx in donor.customer_indices:
                    if idx == donor.medoid_idx:
                        continue
                    d_to_donor = self.dist[donor.medoid_idx][idx]
                    demand = self.locations[idx].demand

                    for receiver in motor_clusters:
                        if receiver is donor:
                            continue
                        if avg_load - receiver.total_load <= 0:
                            continue
                        if not receiver.can_add(demand):
                            continue
                        d_to_receiver = self.dist[receiver.medoid_idx][idx]
                        gain = d_to_donor - d_to_receiver
                        # HANYA pindahkan jika lebih dekat ke target (gain > 0)
                        # Ini memastikan TIDAK ADA tumpang tindih tambahan
                        if gain > 0 and gain > best_gain:
                            best_gain = gain
                            best_candidate = idx
                            best_receiver = receiver

                if best_candidate is None or best_receiver is None:
                    continue

                # Eksekusi move
                idx = best_candidate
                receiver = best_receiver
                demand = self.locations[idx].demand

                if receiver.can_add(demand):
                    donor.remove_customer(idx, demand)
                    receiver.add_customer(idx, demand)
                    moved = True
                    logger.debug(
                        "  Rebalance: #%d (%s) %s(%d) -> %s(%d), gain=%.1f km",
                        idx, self.locations[idx].name,
                        donor.vehicle_id, donor.total_load,
                        receiver.vehicle_id, receiver.total_load,
                        best_gain,
                    )
                    break

            if not moved:
                logger.info(
                    "Workload rebalancing: tidak ada pelanggan 'salah klaster' "
                    "yang bisa dipindahkan (CV=%.3f)", cv
                )
                break

            # Re-evaluasi CV
            loads = [c.total_load for c in motor_clusters]
            avg_load = sum(loads) / len(motor_clusters)
            if avg_load == 0:
                break
            std_load = float(np.std(loads))
            cv = std_load / avg_load
            if cv < 0.25:
                logger.info("Workload seimbang (CV=%.3f)", cv)
                break

        logger.info("Workload rebalancing selesai: loads=%s, CV=%.3f", loads, cv)
        return clusters

    # ──────────────────────────────────────────────────────────────────────────
    def _find_unassigned(
        self, clusters: List[Cluster], customers: List[int]
    ) -> List[int]:
        assigned = set()
        for c in clusters:
            assigned.update(c.customer_indices)
        return [i for i in customers if i not in assigned]

    # ──────────────────────────────────────────────────────────────────────────
    def _assign_to_trucks(
        self, clusters: List[Cluster], unassigned: List[int]
    ) -> List[Cluster]:
        """
        Pelanggan yang tidak muat di motor dialihkan ke klaster mobil.
        Jika belum ada klaster mobil, buat baru.
        """
        truck_clusters = [c for c in clusters if c.vehicle_type == "mobil"]

        if not truck_clusters:
            # Buat klaster baru untuk setiap mobil yang tersedia
            for truck in self.trucks:
                depot_or_first = unassigned[0] if unassigned else 0
                tc = Cluster(truck, medoid_idx=depot_or_first)
                clusters.append(tc)
                truck_clusters.append(tc)

        for idx in unassigned:
            demand = self.locations[idx].demand
            for tc in truck_clusters:
                if tc.can_add(demand):
                    tc.add_customer(idx, demand)
                    logger.info(
                        f"Pelanggan #{idx} ({self.locations[idx].name}) "
                        f"dialihkan ke {tc.vehicle_id} (demand={demand})"
                    )
                    break
            else:
                logger.warning(
                    f"Pelanggan #{idx} ({self.locations[idx].name}) "
                    f"tidak bisa ditempatkan di armada manapun! "
                    f"Demand={demand}, pertimbangkan tambah kendaraan."
                )

        return clusters

    # ──────────────────────────────────────────────────────────────────────────
    def _log_summary(self, clusters: List[Cluster]):
        logger.info("=" * 55)
        logger.info("HASIL CLUSTER FIRST")
        logger.info("=" * 55)
        for c in clusters:
            names = [self.locations[i].name for i in c.customer_indices]
            logger.info(
                f"  {c.vehicle_id:12s} | load {c.total_load:3d}/{c.capacity} box"
                f" | {len(c.customer_indices)} pelanggan: {names}"
            )
        logger.info("=" * 55)
