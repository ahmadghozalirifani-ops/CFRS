"""
routing.py — Tahap "Route Second" menggunakan Hibrida Genetic Algorithm + Tabu Search

Alur:
  1. GA (DEAP): bangkitkan populasi rute → PMX crossover & shuffle mutasi →
                evaluasi fitness (penalti CDD 180 menit)
  2. TS: ambil individu terbaik GA → perbaiki lewat pencarian lokal swap
        dengan daftar tabu agar tidak menghitung ulang rute yang sudah gagal
"""

# pyright: reportAttributeAccessIssue=false
# DEAP menggunakan registrasi atribut dinamis (Toolbox.register, creator.create).
# Pylance tidak bisa melacaknya secara statis — warning diabaikan.

import numpy as np
import random
import logging
from copy import deepcopy
from typing import List, Tuple, Dict, Optional, cast

from deap import base, creator, tools

from config import (
    GA_POPULATION_SIZE, GA_GENERATIONS, GA_CROSSOVER_RATE,
    GA_MUTATION_RATE, GA_ELITE_SIZE, GA_PATIENCE,
    TS_MAX_ITERATIONS, TS_TABU_TENURE, TS_NEIGHBORHOOD_SIZE, TS_PATIENCE,
    COMMON_DUE_DATE_MINUTES, SERVICE_TIME_MINUTES,
    PENALTY_LATE, PENALTY_EQUITY_WEIGHT, PENALTY_CROSS_EQUITY_WEIGHT,
)
from graphhopper import Location
from clustering import Cluster
from traffic import get_gamma

logger = logging.getLogger(__name__)


# ─── Tipe alias ───────────────────────────────────────────────────────────────
Chromosome = List[int]   # urutan indeks pelanggan (bukan termasuk depot)


# ─────────────────────────────────────────────────────────────────────────────
class RouteEvaluator:
    """
    Menghitung total waktu perjalanan dan biaya fitness sebuah rute,
    mempertimbangkan kemacetan dan penalti CDD.
    """

    def __init__(
        self,
        locations: List[Location],
        base_time_matrix: np.ndarray,     # menit, dari GraphHopper
        base_dist_matrix: np.ndarray,     # km
        departure_hour: float,
        depot_idx: int = 0,
        completion_target: Optional[float] = None,  # target waktu selesai (menit) dari CDD untuk penalti cross-equity
        max_work_minutes: Optional[float] = None,   # override COMMON_DUE_DATE_MINUTES jika diberikan
        cross_equity_weight: Optional[float] = None,  # override PENALTY_CROSS_EQUITY_WEIGHT jika diberikan
    ):
        self.locations      = locations
        self.base_time      = base_time_matrix
        self.base_dist      = base_dist_matrix
        self.departure_hour = departure_hour
        self.depot_idx      = depot_idx
        self.completion_target = completion_target
        self.cdd             = max_work_minutes if max_work_minutes is not None else COMMON_DUE_DATE_MINUTES
        self.xequity_weight  = cross_equity_weight if cross_equity_weight is not None else PENALTY_CROSS_EQUITY_WEIGHT

    # ──────────────────────────────────────────────────────────────────────────
    def evaluate(self, route: Chromosome) -> Tuple[float, List[float]]:
        """
        Hitung nilai fitness dan waktu kedatangan di setiap titik.

        Returns
        -------
        fitness          : float  — nilai kecil = rute lebih baik
        arrival_times    : list   — u_i waktu tiba (menit) per pelanggan
        """
        if not route:
            return 0.0, []

        full_route = [self.depot_idx] + route + [self.depot_idx]
        arrival_times: List[float] = []
        current_time = 0.0
        total_distance = 0.0
        late_penalty   = 0.0

        for k in range(len(full_route) - 1):
            i = full_route[k]
            j = full_route[k + 1]

            # ── Per-edge traffic: γ dihitung dari jam aktual edge ini dilalui ──
            current_hour = (self.departure_hour + current_time / 60.0) % 24
            travel = float(self.base_time[i][j] * get_gamma(current_hour))
            current_time += travel
            total_distance += self.base_dist[i][j]

            if j != self.depot_idx:
                # ── Constraint: u_i ≤ T (Common Due Date) ─────────────────
                if current_time > self.cdd:
                    late_amount  = current_time - self.cdd
                    late_penalty += PENALTY_LATE + late_amount * 10_000

                arrival_times.append(current_time)
                current_time += SERVICE_TIME_MINUTES   # waktu bongkar muat s_i

        # ── Penalti ketidakadilan intra-route ─────────────────────────────
        equity_penalty = 0.0
        if len(arrival_times) > 1:
            equity_penalty = PENALTY_EQUITY_WEIGHT * float(np.var(arrival_times))

        # ── Penalti cross-vehicle equity ──────────────────────────────────
        cross_penalty = 0.0
        if self.completion_target is not None and arrival_times:
            completion = arrival_times[-1] + SERVICE_TIME_MINUTES
            if completion > self.completion_target:
                cross_penalty = self.xequity_weight * (completion - self.completion_target)

        fitness = float(total_distance + late_penalty + equity_penalty + cross_penalty)
        return fitness, arrival_times

    # ──────────────────────────────────────────────────────────────────────────
    def is_feasible(self, route: Chromosome) -> bool:
        """Kembalikan True jika semua pelanggan tiba sebelum CDD."""
        _, arrivals = self.evaluate(route)
        return all(t <= self.cdd for t in arrivals)


# ─────────────────────────────────────────────────────────────────────────────
class GeneticAlgorithm:
    """
    GA berbasis DEAP untuk optimasi rute (permutasi pelanggan).
    PMX crossover + shuffle mutation + tournament selection.
    """

    def __init__(self, customers: List[int], evaluator: RouteEvaluator):
        self.customers = customers
        self.evaluator = evaluator
        self.n = len(customers)

    def _eval_wrapper(self, individual: List[int]) -> Tuple[float]:
        """Konversi indeks posisional (0..n-1) → indeks pelanggan → fitness."""
        route = [self.customers[i] for i in individual]
        fitness, _ = self.evaluator.evaluate(route)
        return (fitness,)

    def run(self) -> Chromosome:
        """Jalankan GA DEAP dan kembalikan kromosom (indeks pelanggan)."""
        if self.n <= 1:
            return self.customers[:]

        # ── Setup DEAP types ─────────────────────────────────────────
        if "FitnessMin_VRP" not in creator.__dict__:
            creator.create("FitnessMin_VRP", base.Fitness, weights=(-1.0,))
        if "Individual_VRP" not in creator.__dict__:
            creator.create("Individual_VRP", list, fitness=creator.FitnessMin_VRP)

        tb = base.Toolbox()
        # Individu = permutasi indeks posisional [0, 1, 2, ..., n-1]
        # (PMX membutuhkan indeks array sebagai nilai)
        tb.register("indices", random.sample, range(self.n), self.n)
        tb.register(
            "individual",
            tools.initIterate,
            creator.Individual_VRP,
            tb.indices,
        )
        tb.register(
            "population",
            tools.initRepeat,
            list,
            tb.individual,
        )

        tb.register("mate", tools.cxPartialyMatched)
        tb.register(
            "mutate",
            tools.mutShuffleIndexes,
            indpb=GA_MUTATION_RATE / 2.0,
        )
        tb.register("select", tools.selTournament, tournsize=5)
        tb.register("evaluate", self._eval_wrapper)

        pop = tb.population(n=GA_POPULATION_SIZE)
        hof = tools.HallOfFame(maxsize=1)

        # Inisialisasi statistik
        stats = tools.Statistics(lambda ind: ind.fitness.values[0])
        stats.register("min", np.min)
        stats.register("avg", np.mean)
        stats.register("max", np.max)

        # Evaluasi populasi awal
        for ind in pop:
            ind.fitness.values = tb.evaluate(ind)

        hof.update(pop)
        best_chromosome = list(hof[0])
        best_fitness = hof[0].fitness.values[0]
        stagnation = 0

        for gen in range(GA_GENERATIONS):
            # ── Seleksi + cloning (hindari mutasi in-place parent) ──
            selected = tb.select(pop, k=GA_POPULATION_SIZE)
            offspring = [deepcopy(ind) for ind in selected]

            # ── Elitisme ────────────────────────────────────────────
            elite = tools.selBest(pop, k=GA_ELITE_SIZE)
            for k in range(GA_ELITE_SIZE):
                offspring[k] = deepcopy(elite[k])

            # ── Crossover ───────────────────────────────────────────
            for k in range(GA_ELITE_SIZE, GA_POPULATION_SIZE, 2):
                if k + 1 < GA_POPULATION_SIZE and random.random() < GA_CROSSOVER_RATE:
                    c1, c2 = tb.mate(offspring[k], offspring[k + 1])
                    offspring[k] = c1
                    offspring[k + 1] = c2

            # ── Mutasi ──────────────────────────────────────────────
            for k in range(GA_ELITE_SIZE, GA_POPULATION_SIZE):
                if random.random() < GA_MUTATION_RATE:
                    tb.mutate(offspring[k])
                    del offspring[k].fitness.values

            # ── Evaluasi ────────────────────────────────────────────
            for ind in offspring:
                if not ind.fitness.valid:
                    ind.fitness.values = tb.evaluate(ind)

            pop = offspring
            hof.update(pop)
            gen_fitness = hof[0].fitness.values[0]

            if gen_fitness < best_fitness:
                best_chromosome = list(hof[0])
                best_fitness = gen_fitness
                stagnation = 0
            else:
                stagnation += 1

            if stagnation >= GA_PATIENCE:
                logger.debug(
                    "  GA DEAP berhenti pada gen %d (stagnasi %d)",
                    gen + 1, stagnation,
                )
                break

            if gen % 50 == 0:
                record = stats.compile(pop)
                logger.debug(
                    "  GA gen %4d | min=%.2f avg=%.2f max=%.2f",
                    gen, record["min"], record["avg"], record["max"],
                )

        logger.info("  GA DEAP selesai | best fitness = %.2f", best_fitness)
        # Konversi indeks posisional → indeks pelanggan
        return [self.customers[i] for i in best_chromosome]


# ─────────────────────────────────────────────────────────────────────────────
class TabuSearch:
    """
    Tabu Search untuk penyempurnaan lokal rute terbaik dari GA.
    Menggunakan operator 2-opt dan swap dengan daftar tabu (tenure).
    """

    def __init__(self, initial_route: Chromosome, evaluator: RouteEvaluator):
        self.route     = initial_route[:]
        self.evaluator = evaluator
        self.n         = len(initial_route)
        self.tabu_list: Dict[Tuple, int] = {}  # gerakan → iterasi kadaluarsa

    # ──────────────────────────────────────────────────────────────────────────
    def run(self) -> Chromosome:
        """Jalankan TS dan kembalikan rute final yang dioptimalkan.
        Berhenti lebih awal jika best global tidak membaik selama TS_PATIENCE iterasi."""
        if self.n <= 2:
            return self.route

        current_route   = self.route[:]
        current_fitness, _ = self.evaluator.evaluate(current_route)
        best_route      = current_route[:]
        best_fitness    = current_fitness
        stagnation      = 0  # iterasi tanpa perbaikan global

        for iteration in range(TS_MAX_ITERATIONS):
            # Bersihkan gerakan tabu yang sudah kadaluarsa
            self.tabu_list = {
                move: exp
                for move, exp in self.tabu_list.items()
                if exp > iteration
            }

            # Bangkitkan tetangga (neighborhood)
            neighbors = self._generate_neighbors(current_route)
            best_neighbor      = None
            best_neighbor_fit  = float("inf")
            best_move: Optional[Tuple] = None

            for neighbor, move in neighbors:
                fit, _ = self.evaluator.evaluate(neighbor)

                is_tabu = move in self.tabu_list

                # Kriteria Aspirasi: terima meski tabu jika lebih baik dari best
                if is_tabu and fit >= best_fitness:
                    continue

                if fit < best_neighbor_fit:
                    best_neighbor_fit = fit
                    best_neighbor     = neighbor
                    best_move         = move

            if best_neighbor is None or best_move is None:
                logger.debug(f"  TS iter {iteration}: tidak ada tetangga valid.")
                break

            # Pindah ke tetangga terbaik
            current_route   = best_neighbor
            current_fitness = best_neighbor_fit

            # Masukkan gerakan ke daftar tabu
            self.tabu_list[best_move] = iteration + TS_TABU_TENURE

            # Perbarui solusi terbaik global
            if current_fitness < best_fitness:
                best_route   = current_route[:]
                best_fitness = current_fitness
                stagnation   = 0
            else:
                stagnation += 1

            # Early stopping: tidak ada perbaikan global dalam N iterasi
            if stagnation >= TS_PATIENCE:
                logger.debug(
                    f"  TS berhenti pada iterasi {iteration + 1} "
                    f"(stagnasi {stagnation} iterasi)"
                )
                break

            if iteration % 50 == 0:
                logger.debug(f"  TS iter {iteration:4d} | fitness = {best_fitness:.2f}")

        logger.info(f"  TS selesai | best fitness = {best_fitness:.2f}")
        return best_route

    # ──────────────────────────────────────────────────────────────────────────
    def _generate_neighbors(
        self, route: Chromosome
    ) -> List[Tuple[Chromosome, Tuple]]:
        """Hasilkan tetangga via SWAP dan 2-OPT."""
        neighbors = []
        n = len(route)
        candidates = set()

        # Bangkitkan TS_NEIGHBORHOOD_SIZE gerakan acak
        attempts = 0
        while len(candidates) < TS_NEIGHBORHOOD_SIZE and attempts < TS_NEIGHBORHOOD_SIZE * 5:
            i = random.randint(0, n - 1)
            j = random.randint(0, n - 1)
            if i != j:
                move = (min(i, j), max(i, j))
                candidates.add(move)
            attempts += 1

        for (i, j) in candidates:
            # ── SWAP ──────────────────────────────────────────────────────
            swap_route = route[:]
            swap_route[i], swap_route[j] = swap_route[j], swap_route[i]
            neighbors.append((swap_route, ("swap", i, j)))

            # ── 2-OPT (balik segmen antara i dan j) ───────────────────────
            two_opt = route[:i] + route[i:j+1][::-1] + route[j+1:]
            neighbors.append((two_opt, ("2opt", i, j)))

        return neighbors


# ─────────────────────────────────────────────────────────────────────────────
class HybridTSGA:
    """
    Orkestrator hybrid: jalankan GA → ambil terbaik → perbaiki dengan TS.
    """

    def __init__(
        self,
        cluster: Cluster,
        locations: List[Location],
        base_time_matrix: np.ndarray,
        base_dist_matrix: np.ndarray,
        departure_hour: float,
        depot_idx: int = 0,
        max_work_minutes: Optional[float] = None,
        cross_equity_weight: Optional[float] = None,
    ):
        self.cluster    = cluster
        cap = cluster.capacity if cluster.capacity > 0 else 35
        load_ratio = cluster.total_load / cap
        cdd = max_work_minutes if max_work_minutes is not None else COMMON_DUE_DATE_MINUTES
        completion_target = cdd * max(0.3, load_ratio)
        self.evaluator  = RouteEvaluator(
            locations, base_time_matrix, base_dist_matrix,
            departure_hour, depot_idx, completion_target,
            max_work_minutes=max_work_minutes,
            cross_equity_weight=cross_equity_weight,
        )
        self.customers  = cluster.customer_indices[:]

    # ──────────────────────────────────────────────────────────────────────────
    def optimize(self) -> Dict:
        """
        Kembalikan dictionary hasil optimasi:
        {
          'vehicle_id'   : str,
          'route'        : list[int],   — urutan indeks pelanggan
          'fitness'      : float,
          'arrival_times': list[float], — menit dari keberangkatan
          'feasible'     : bool,
        }
        """
        vid = self.cluster.vehicle_id
        logger.info(f"\n{'='*55}")
        logger.info(f"Route Second: {vid} "
                    f"({len(self.customers)} pelanggan, "
                    f"load={self.cluster.total_load})")

        if not self.customers:
            return {
                "vehicle_id": vid, "route": [],
                "fitness": 0.0, "arrival_times": [], "feasible": True,
            }

        # Tahap 1: GA
        logger.info(f"  Menjalankan GA …")
        ga      = GeneticAlgorithm(self.customers, self.evaluator)
        ga_best = ga.run()

        # Tahap 2: TS
        logger.info(f"  Menjalankan Tabu Search …")
        ts      = TabuSearch(ga_best, self.evaluator)
        ts_best = ts.run()

        fitness, arrivals = self.evaluator.evaluate(ts_best)
        feasible = self.evaluator.is_feasible(ts_best)

        if not feasible:
            logger.warning(
                f"  ⚠  {vid}: rute TIDAK FEASIBLE (ada pelanggan melewati {COMMON_DUE_DATE_MINUTES} menit)"
            )

        return {
            "vehicle_id"   : vid,
            "route"        : ts_best,
            "fitness"      : fitness,
            "arrival_times": arrivals,
            "feasible"     : feasible,
        }
