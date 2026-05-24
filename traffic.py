"""
traffic.py — Kalkulator waktu tempuh dengan koefisien kemacetan dinamis (Time-Varying)
             Rumus: v_p = v_0 / γ_p
"""

import numpy as np

from config import TRAFFIC_PERIODS


def get_gamma(departure_hour: float) -> float:
    """
    Ambil koefisien kemacetan γ berdasarkan jam keberangkatan.

    Parameters
    ----------
    departure_hour : float  — jam dalam format desimal (misal 10.5 = 10:30)

    Returns
    -------
    gamma : float
    """
    h = departure_hour % 24
    for start, end, gamma in TRAFFIC_PERIODS:
        if start <= h < end:
            return gamma
    return 1.0  # default: lancar


def travel_time_adjusted(
    distance_km: float,
    base_time_min: float,
    departure_hour: float,
) -> float:
    """
    Hitung waktu tempuh yang sudah disesuaikan kemacetan.

    Rumus: t_adjusted = base_time × γ_p
    (atau ekuivalen: jarak / (kecepatan_ideal / γ_p))

    Parameters
    ----------
    distance_km    : float — jarak dari GraphHopper (km)
    base_time_min  : float — waktu tempuh ideal dari GraphHopper (menit)
    departure_hour : float — jam keberangkatan (desimal)

    Returns
    -------
    waktu_tempuh_disesuaikan : float (menit)
    """
    gamma = get_gamma(departure_hour)
    return base_time_min * gamma


def adjusted_time_matrix(
    time_matrix: np.ndarray,
    departure_hour: float,
) -> np.ndarray:
    """
    Buat salinan matriks waktu yang sudah dikalikan koefisien γ
    sesuai jam keberangkatan yang diberikan.
    """
    gamma = get_gamma(departure_hour)
    return time_matrix * gamma
