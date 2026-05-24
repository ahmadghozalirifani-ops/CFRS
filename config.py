"""
config.py — Konfigurasi global untuk sistem CFRS Katering
Sesuaikan parameter di sini sebelum menjalankan main.py
"""

# ─── GraphHopper ──────────────────────────────────────────────────────────────
GRAPHHOPPER_URL = "http://localhost:8989"   # URL GraphHopper localhost Anda
VEHICLE_PROFILE  = "car"                    # profil kendaraan: "car" atau "bike"

# ─── Armada ───────────────────────────────────────────────────────────────────
FLEET = [
    {"id": "motor_1", "type": "motor", "capacity": 35},
    {"id": "motor_2", "type": "motor", "capacity": 35},
    {"id": "motor_3", "type": "motor", "capacity": 35},
    {"id": "motor_4", "type": "motor", "capacity": 35},
    {"id": "mobil_1", "type": "mobil", "capacity": 999},  # kapasitas mobil tidak dibatasi ketat
]

# ─── Batasan Waktu ────────────────────────────────────────────────────────────
COMMON_DUE_DATE_MINUTES = 180   # batas waktu bersama (CDD) = 3 jam
SERVICE_TIME_MINUTES    = 5     # waktu bongkar muat per pelanggan (menit)

# ─── Slot Pengiriman ─────────────────────────────────────────────────────────
SLOTS = {
    "siang": {"departure": 10.0, "label": "Siang (10:00–13:00)"},
    "sore":  {"departure": 15.0, "label": "Sore (15:00–18:00)"},
}

# ─── Koefisien Kemacetan (Time-Varying) ──────────────────────────────────────
# Format: (jam_mulai, jam_selesai, gamma)
# gamma = 1.0 → lancar; gamma > 1.0 → macet
TRAFFIC_PERIODS = [
    (0,   7,   1.0),   # dini hari – lancar
    (7,   9,   1.5),   # pagi sibuk
    (9,   11,  1.2),
    (11,  13,  1.3),   # jam makan siang
    (13,  16,  1.1),
    (16,  19,  1.6),   # sore sibuk
    (19,  24,  1.0),
]

# ─── Parameter Genetic Algorithm ─────────────────────────────────────────────
GA_POPULATION_SIZE  = 80
GA_GENERATIONS      = 200
GA_CROSSOVER_RATE   = 0.85
GA_MUTATION_RATE    = 0.15
GA_ELITE_SIZE       = 5        # kromosom terbaik yang langsung lolos
GA_PATIENCE         = 40       # early stopping: berhenti jika tak ada perbaikan N generasi

# ─── Parameter Clustering (K-Medoids) ───────────────────────────────────────
CLUSTERING_MAX_ITER  = 150     # maks iterasi K-Medoids
CLUSTERING_LOAD_BIAS = 0.8     # bobot penalti beban: semakin besar → makin seimbang (0 = mati)

# ─── Parameter Tabu Search ───────────────────────────────────────────────────
TS_MAX_ITERATIONS   = 300
TS_TABU_TENURE      = 15       # berapa iterasi sebuah gerakan diingat sebagai tabu
TS_NEIGHBORHOOD_SIZE= 30       # jumlah tetangga dievaluasi per iterasi
TS_PATIENCE         = 60       # early stopping: berhenti jika best global tak membaik N iterasi

# ─── Penalti ─────────────────────────────────────────────────────────────────
PENALTY_LATE        = 1e6      # penalti besar jika melampaui CDD
PENALTY_EQUITY_WEIGHT = 0.3    # bobot ketidakadilan waktu antar-pelanggan (intra-route)
PENALTY_CROSS_EQUITY_WEIGHT = 5000  # penalti deviasi beban antar-kendaraan (cross-vehicle)

# ══════════════════════════════════════════════════════════════════════════════
# ── DEPOT ────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

DEPOT = {
    "name": "Inzan Catering Bantul",
    "lat":  -7.9195,
    "lon":  110.3556,
}

# ══════════════════════════════════════════════════════════════════════════════
# ── SAMPLE DATA (dari data rute 24 april.xlsx) ───────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

_D  = '2026-04-24'
_BW = 5.0    # kg/box
_BV = 0.06   # m³/box

def _o(seq, cust, phone, addr, lat, lon, boxes, slot, notes='', src='excel', hh=7, mm=0):
    """Helper ringkas buat 1 order dict (dari data rute 24 april)."""
    return {
        'id':            f'XL-{_D.replace("-","")}-{seq:03d}',
        'customer':      cust,
        'phone':         phone,
        'address':       addr,
        'lat':           lat,
        'lon':           lon,
        'boxes':         boxes,
        'weight_kg':     round(boxes * _BW, 1),
        'volume_m3':     round(boxes * _BV, 3),
        'delivery_slot': slot,
        'delivery_date': _D,
        'notes':         notes,
        'source':        src,
        'created_at':    f'{_D} {hh:02d}:{mm:02d}:00',
        'geocoded':      1,
    }

S  = 'siang'
R  = 'sore'
SR = 'siang+sore'

SAMPLE_FLEET = [
    {
        'id':            'AB 2665 UG',
        'type':          'motor',
        'capacity':      35,
        'plate':         'AB 2665 UG',
        'driver':        'Jimi',
        'phone':         '6281234567891',
        'model':         'Vario',
        'max_weight':    175.0,
        'max_volume':    2.1,
        'cost_per_km':   1500,
        'fixed_cost':    30000,
        'is_optional':   False,
        'zona':          'utara-timur',
        'zona_tambahan': [],
        'home_lat':      -7.8450,
        'home_lon':      110.3380,
    },
    {
        'id':            'AB 5646 KA',
        'type':          'motor',
        'capacity':      35,
        'plate':         'AB 5646 KA',
        'driver':        'Ruditri',
        'phone':         '6281234567894',
        'model':         'Supra',
        'max_weight':    175.0,
        'max_volume':    2.1,
        'cost_per_km':   1500,
        'fixed_cost':    30000,
        'is_optional':   False,
        'zona':          'utara-selatan',
        'zona_tambahan': [],
        'home_lat':      -7.7920,
        'home_lon':      110.3525,
    },
    {
        'id':            'AB 4271 HI',
        'type':          'motor',
        'capacity':      35,
        'plate':         'AB 4271 HI',
        'driver':        'Fajar',
        'phone':         '6281234567893',
        'model':         'Supra',
        'max_weight':    175.0,
        'max_volume':    2.1,
        'cost_per_km':   1500,
        'fixed_cost':    30000,
        'is_optional':   False,
        'zona':          'utara-barat',
        'zona_tambahan': [],
        'home_lat':      -7.7988,
        'home_lon':      110.3508,
    },
    {
        'id':            'AB 1234 VA',
        'type':          'motor',
        'capacity':      35,
        'plate':         'AB 1234 VA',
        'driver':        'Okta',
        'phone':         '6281234567892',
        'model':         'Vario',
        'max_weight':    175.0,
        'max_volume':    2.1,
        'cost_per_km':   1500,
        'fixed_cost':    30000,
        'is_optional':   False,
        'zona':          'selatan-barat',
        'zona_tambahan': [],
        'home_lat':      -7.8012,
        'home_lon':      110.3508,
    },
    {
        'id':            'AB 9999 ZZ',
        'type':          'mobil',
        'capacity':      150,
        'plate':         'AB 9999 ZZ',
        'driver':        'Admin / Cadangan',
        'phone':         '6281234567895',
        'model':         'Mobil Cadangan',
        'max_weight':    750.0,
        'max_volume':    9.0,
        'cost_per_km':   3000,
        'fixed_cost':    50000,
        'is_optional':   True,
        'zona':          '',
        'zona_tambahan': [],
        'home_lat':      -7.9195,
        'home_lon':      110.3556,
    },
]

SAMPLE_ORDERS = [
    _o(  1, "Emanuella",      "", "Jl. Urip Sumoharjo, Gondokusuman",                          -7.7846, 110.3857, 1, S),
    _o(  2, "Hadi",           "", "Galleria Mall, Jl. Urip Sumoharjo No.7, Yogyakarta",        -7.7858, 110.3972, 1, S),
    _o(  3, "Lenemy",         "", "Jl. Colombo, Depok, Sleman",                               -7.7712, 110.3869, 1, S),
    _o(  4, "Chesa",          "", "Jl. Affandi, Condongcatur, Depok",                          -7.7805, 110.3950, 1, S),
    _o(  5, "Allison",        "", "Jl. Affandi, Condongcatur, Depok",                          -7.7795, 110.3955, 2, S),
    _o(  6, "Nur Rizky",      "", "Jl. Kaliurang Tengah (KM 9), Sleman",                      -7.7450, 110.3900, 1, S),
    _o(  7, "Tantri",         "", "RS JIH, Jl. Ring Road Utara No.160, Condongcatur",          -7.7523, 110.4076, 1, S),
    _o(  8, "Faisal",         "", "RS JIH, Jl. Ring Road Utara No.160, Condongcatur",          -7.7520, 110.4080, 1, S),
    _o(  9, "Jessica",        "", "Stadion Maguwoharjo, Jl. Palagan, Depok, Sleman",           -7.7516, 110.4243, 1, S),
    _o( 10, "Faenzo28",       "", "Stadion Maguwoharjo, Jl. Palagan, Depok, Sleman",           -7.7522, 110.4240, 1, S),
    _o( 11, "Ihsan",          "", "Jl. Perumnas, Condongcatur, Depok, Sleman",                 -7.7580, 110.4050, 2, S),
    _o( 12, "Nisrina",        "", "Jl. Perumnas, Condongcatur, Depok, Sleman",                 -7.7585, 110.4055, 1, S),
    _o( 13, "Lely",           "", "Jl. Wahid Hasyim, Condongcatur, Depok",                     -7.7668, 110.4005, 1, S),
    _o( 14, "Vanecia",        "", "Janti, Banguntapan, Bantul",                                -7.7920, 110.4050, 1, S),
    _o( 15, "Fahrul Gozali",  "", "Perumnas Condongcatur, Depok, Sleman",                      -7.7550, 110.4068, 4, S),
    _o( 16, "Soffi",          "", "Stadion Mandala Krida, Jl. Kenari, Umbulharjo",             -7.7993, 110.3983, 1, R),
    _o( 17, "Emanuella",      "", "Jl. Urip Sumoharjo, Gondokusuman",                          -7.7846, 110.3857, 1, R),
    _o( 18, "Hadi",           "", "Galleria Mall, Jl. Urip Sumoharjo No.7",                    -7.7858, 110.3972, 1, R),
    _o( 19, "Lenemy",         "", "Jl. Colombo, Depok, Sleman",                               -7.7712, 110.3869, 1, R),
    _o( 20, "Quensya",        "", "Mrican, Caturtunggal, Depok",                               -7.7831, 110.3942, 1, R),
    _o( 21, "Jethro",         "", "Mrican, Caturtunggal, Depok",                               -7.7835, 110.3945, 1, R),
    _o( 22, "Adrialisa Regina","", "Jl. Wahid Hasyim, Condongcatur, Depok",                     -7.7668, 110.4005, 1, R),
    _o( 23, "Venecia",        "", "Janti / Babarsari, Banguntapan",                            -7.7900, 110.4090, 1, R),
    _o( 24, "Emma Amalia",    "", "Janti / Babarsari, Banguntapan",                            -7.7910, 110.4095, 1, R),
    _o( 25, "Rafael",         "", "Next Hotel, Jl. Solo, Berbah, Sleman",                      -7.7978, 110.4152, 1, R),
    _o( 26, "Lusiana",        "", "Next Hotel, Jl. Solo, Berbah, Sleman",                      -7.7975, 110.4156, 1, R),
    _o( 27, "Winanti",        "", "Maguwoharjo, Depok, Sleman",                                -7.7516, 110.4243, 1, R),
    _o( 28, "Elmo",           "", "Seturan, Depok, Sleman",                                    -7.7745, 110.4090, 1, R),
    _o( 29, "Kintan",         "", "Depan UPN Veteran Yogyakarta, Condongcatur",                -7.7753, 110.4097, 1, R),
    _o( 30, "Faisal",         "", "RS JIH, Jl. Ring Road Utara, Condongcatur",                 -7.7523, 110.4076, 1, R),
    _o( 31, "Tantri",         "", "RS JIH, Jl. Ring Road Utara, Condongcatur",                 -7.7520, 110.4080, 1, R),
    _o( 32, "Imaaci",         "", "Jl. Kaliurang Tengah (KM 9), Sleman",                      -7.7450, 110.3900, 1, R),
    _o( 33, "Allison",        "", "Jl. Affandi, Condongcatur, Depok",                          -7.7800, 110.3960, 2, R),
    _o( 34, "Tito",           "", "Kopiwongso, Ngampilan / Tamansari, Yogyakarta",             -7.8022, 110.3618, 1, S),
    _o( 35, "Ilham",          "", "Lampu Merah Tembi, Timbulharjo, Sewon, Bantul",             -7.8558, 110.3738, 1, S),
    _o( 36, "Fakhira",        "", "UAD Kampus 4, Jl. Ringroad Selatan, Tamanan, Banguntapan",  -7.8504, 110.3874, 1, S),
    _o( 37, "Hadi",           "", "Hotel Gaharu Suite, Gedong Kuning, Banguntapan",            -7.8258, 110.3943, 1, S),
    _o( 38, "Ani",            "", "Kotagede (sebelum pasar), Yogyakarta",                      -7.8201, 110.3927, 1, S),
    _o( 39, "Miftah",         "", "Kotagede, Yogyakarta",                                      -7.8210, 110.3940, 1, S),
    _o( 40, "Alma",           "", "Puskesmas Kotagede, Jl. Kemasan, Kotagede",                 -7.8223, 110.3959, 1, S),
    _o( 41, "Alya",           "", "UAD Kampus 4, Jl. Ringroad Selatan, Tamanan, Banguntapan",  -7.8504, 110.3874, 3, S),
    _o( 42, "Brenda",         "", "DPRD Bantul, Jl. Jend. Sudirman, Bantul Kota",              -7.8872, 110.3318, 4, S),
    _o( 43, "Ramdani",        "", "Berbah, Sleman",                                            -7.8011, 110.4400, 1, S),
    _o( 44, "Ilham",          "", "Lampu Merah Tembi, Timbulharjo, Sewon, Bantul",             -7.8558, 110.3738, 1, R),
    _o( 45, "Fakhira",        "", "UAD Kampus 4, Jl. Ringroad Selatan, Tamanan, Banguntapan",  -7.8504, 110.3874, 1, R),
    _o( 46, "Hadi",           "", "Hotel Gaharu Suite, Gedong Kuning, Banguntapan",            -7.8258, 110.3943, 1, R),
    _o( 47, "Mulki",          "", "Gembira Loka Zoo, Jl. Kebun Raya, Kotagede",                -7.8039, 110.3978, 1, R),
    _o( 48, "Miftah",         "", "Kotagede, Yogyakarta",                                      -7.8210, 110.3940, 1, R),
    _o( 49, "Ratnaningsih",   "", "Kotagede, Yogyakarta",                                      -7.8215, 110.3945, 1, R),
    _o( 50, "Aleeya",         "", "Supermarket Pamela 2, Jl. Kusumanegara, Umbulharjo",        -7.8061, 110.3872, 1, R),
    _o( 51, "Alya",           "", "UAD Kampus 4, Jl. Ringroad Selatan, Tamanan, Banguntapan",  -7.8504, 110.3874, 1, R),
    _o( 52, "Tutik",          "", "Umbulharjo, Yogyakarta",                                    -7.8320, 110.3780, 1, R),
    _o( 53, "Japlin",         "", "Jl. Sabirin, Kotabaru, Gondokusuman, Yogyakarta",           -7.7885, 110.3718, 1, S),
    _o( 54, "Tyas",           "", "RS Hewan UGM, Jl. Fauna, Caturtunggal, Sleman",             -7.7690, 110.3742, 1, S),
    _o( 55, "Diva",           "", "Jl. Kocoran, Kotabaru, Gondokusuman",                       -7.7885, 110.3637, 1, S),
    _o( 56, "Ariana",         "", "Asrama Ratnaningsih 1, Pogung, Sinduadi, Mlati",            -7.7595, 110.3716, 1, S),
    _o( 57, "Tya",            "", "Pogung Baru B23, Sinduadi, Mlati, Sleman",                  -7.7620, 110.3710, 5, S),
    _o( 58, "Elizabeth",      "", "Pogung Baru E20, Sinduadi, Mlati, Sleman",                  -7.7615, 110.3720, 1, S),
    _o( 59, "Galuh",          "", "RSUP Dr. Sardjito, Jl. Kesehatan, Sinduadi",                -7.7690, 110.3731, 1, S),
    _o( 60, "dr Fatimah",     "", "RSUP Dr. Sardjito, Jl. Kesehatan, Sinduadi",                -7.7695, 110.3728, 1, S),
    _o( 61, "Cia",            "", "Apartemen Taman Melati, Sinduadi, Mlati, Sleman",           -7.7572, 110.3698, 1, S),
    _o( 62, "Wulan Dewi",     "", "Villa Bahagia Sejahtera Blok C3, Mlati, Sleman",            -7.7513, 110.3508, 2, S),
    _o( 63, "Nurman Hidayat", "", "PT Kubradental, Jl. Ring Road Barat, Gamping",              -7.8010, 110.3248, 4, S),
    _o( 64, "Putri",          "", "Kos Putri Icha, Sendowo, Sinduadi, Mlati",                  -7.7730, 110.3645, 1, S),
    _o( 65, "Gita",           "", "SD Mutiara Persada, Jl. Wates, Kasihan, Bantul",            -7.8010, 110.3340, 1, S),
    _o( 66, "Bu Tejo",        "", "Wirobrajan, Yogyakarta",                                    -7.7988, 110.3508, 1, S),
    _o( 67, "Japlin",         "", "Jl. Sabirin, Kotabaru, Gondokusuman",                       -7.7885, 110.3718, 1, R),
    _o( 68, "Felicia",        "", "Jl. Kocoran, Sinduadi, Sleman",                             -7.7645, 110.3805, 1, R),
    _o( 69, "Diva",           "", "Jl. Kocoran (beda gang), Sinduadi",                         -7.7645, 110.3805, 1, R),
    _o( 70, "Gita",           "", "Jl. Kocoran Gang Kweni, Sinduadi",                          -7.7645, 110.3805, 1, R),
    _o( 71, "Alma",           "", "Depan Masjid Pogung Baru, Sinduadi, Mlati",                 -7.7618, 110.3718, 1, R),
    _o( 72, "Veodora",        "", "Pogung Baru Blok A, Sinduadi, Mlati, Sleman",               -7.7610, 110.3710, 1, R),
    _o( 73, "Ima",            "", "Jl. Kaliurang KM 6.5, Caturtunggal, Sleman",                -7.7510, 110.3895, 1, R),
    _o( 74, "Puti",           "", "Sendowo, Sinduadi, Mlati, Sleman",                          -7.7730, 110.3645, 1, R),
    _o( 75, "Syifa",          "", "Jl. Gotong Royong, Tegalrejo, Yogyakarta",                  -7.7882, 110.3458, 1, R),
    _o( 76, "Binta",          "", "Jl. Gotong Royong, Tegalrejo, Yogyakarta",                  -7.7885, 110.3461, 1, R),
    _o( 77, "Devi",           "", "Jl. Tambak Bener, Tegalrejo, Yogyakarta",                   -7.7858, 110.3455, 1, R),
    _o( 78, "Devian",         "", "UMY, Jl. Brawijaya (Ring Road Barat), Tamantirto, Kasihan, Bantul", -7.8364, 110.3246, 1, S),
    _o( 79, "Nadya",          "", "Titi Bumi, Gamping, Sleman",                                -7.8096, 110.3185, 3, S),
    _o( 80, "Puti",           "", "ISI Yogyakarta, Jl. Parangtritis KM 6.5, Sewon, Bantul",    -7.8581, 110.3588, 1, R),
    _o( 81, "Hastan",         "", "ISI Yogyakarta, Jl. Parangtritis KM 6.5, Sewon, Bantul",    -7.8583, 110.3590, 1, R),
    _o( 82, "Frisa",          "", "UMY, Jl. Brawijaya, Tamantirto, Kasihan, Bantul",           -7.8364, 110.3246, 1, R),
    _o( 83, "Salsabila",      "", "UMY, Jl. Brawijaya, Tamantirto, Kasihan, Bantul",           -7.8368, 110.3250, 1, R),
    _o( 84, "Aditya",         "", "Bangunjiwo, Kasihan, Bantul",                               -7.8582, 110.3398, 1, R),
    _o( 85, "Sifa",           "", "UMY Ringroad, Tamantirto, Kasihan, Bantul",                 -7.8370, 110.3245, 1, R),
    _o( 86, "Ara",            "", "Jl. Bugisan, Patangpuluhan, Wirobrajan, Yogyakarta",         -7.8080, 110.3453, 1, R),
    _o( 87, "Mala",           "", "Gereja Pugeran, Jl. Sisingamangaraja, Mantrijeron",         -7.8028, 110.3627, 1, R),
    _o( 88, "Winar",          "", "UMY, Jl. Brawijaya, Tamantirto, Kasihan, Bantul",           -7.8372, 110.3247, 1, R),
    _o( 89, "Rika",           "", "Banyumeneng, Gamping, Sleman",                              -7.8096, 110.3062, 1, R),
]
