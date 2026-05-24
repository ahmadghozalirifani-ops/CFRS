"""
styles.py — CSS custom dan konstanta warna untuk dashboard Streamlit CFRS.
"""

VEHICLE_COLORS = [
    "#FF6B6B", "#2EC4B6", "#4361EE", "#FFB703",
    "#9C27B0", "#00BCD4", "#FF5722", "#607D8B",
]

DASHBOARD_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: #FAFBFE; color: #1a1a2e; }

/* ── hero ───────────────────────────────────────────────────── */
.hero {
    background: #FFFFFF;
    border: 1px solid #E5E7EB; 
    border-radius: 16px;
    padding: 24px 32px; 
    margin-bottom: 20px;
    display: flex; 
    align-items: center; 
    gap: 20px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.03);
    border-left: 6px solid #4361EE;
}
.hero-icon { font-size: 2.8rem; }
.hero h1   { font-size: 1.85rem; font-weight:700; color:#1a1a2e; margin:0 0 4px 0; }
.hero p    { color:#6b7280; margin:0; font-size:.9rem; }

/* ── banners ────────────────────────────────────────────────── */
.db-banner {
    background:#ECFDF5; border:1px solid #A7F3D0; border-radius:10px;
    padding:9px 16px; font-size:.84rem; color:#065F46; margin-bottom:10px;
}
.no-db-banner {
    background:#FEF2F2; border:1px solid #FECACA; border-radius:10px;
    padding:9px 16px; font-size:.84rem; color:#991B1B; margin-bottom:10px;
}

/* ── kpi cards ──────────────────────────────────────────────── */
.kpi-card {
    background:#FFFFFF; border:1px solid #E5E7EB;
    border-radius:12px; padding:16px 20px; text-align:center;
    box-shadow: 0 2px 12px rgba(0,0,0,0.04);
}
.kpi-val { font-size:1.9rem; font-weight:700; font-family:'JetBrains Mono',monospace; color: #1a1a2e; }
.kpi-lbl { font-size:.74rem; color:#6b7280; text-transform:uppercase; letter-spacing:.08em; font-weight: 600; }

/* ── route / driver card ────────────────────────────────────── */
.route-card {
    background:#FFFFFF; border:1px solid #E5E7EB; border-radius:12px;
    padding:16px 20px; margin-bottom:14px; overflow:hidden; position:relative;
    box-shadow: 0 4px 15px rgba(0,0,0,0.03);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.route-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 25px rgba(0,0,0,0.06);
}
.route-card-header {
    display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;
}
.route-card-title { font-size:1.05rem; font-weight:700; color: #1a1a2e; }
.route-badge {
    display:inline-block; padding:4px 12px; border-radius:20px;
    font-size:.72rem; font-weight:700; font-family:'JetBrains Mono',monospace;
}
.badge-ok   { background:#ECFDF5; color:#059669; border:1px solid #A7F3D0; }
.badge-late { background:#FEF2F2; color:#DC2626; border:1px solid #FECACA; }
.badge-gh   { background:#EFF6FF; color:#2563EB; border:1px solid #BFDBFE; }

/* ── utilization bar ────────────────────────────────────────── */
.util-bar-wrap { background:#F3F4F6; border-radius:6px; height:8px; overflow:hidden; margin:8px 0 4px; }
.util-bar-fill { height:8px; border-radius:6px; transition:.3s; }

/* ── meta row ───────────────────────────────────────────────── */
.meta-row {
    display:flex; gap:20px; flex-wrap:wrap; font-size:.78rem; color:#6b7280;
    margin-top:6px;
}
.meta-item b { color:#1a1a2e; }

/* ── GH proof box ───────────────────────────────────────────── */
.gh-proof {
    background:#EFF6FF; border:1px solid #BFDBFE; border-radius:10px;
    padding:12px 18px; font-size:.8rem; color:#1E40AF;
    font-family:'JetBrains Mono',monospace; margin-top:16px;
}
.gh-proof-row { display:flex; gap:24px; flex-wrap:wrap; }
.gh-proof-item { color:#6b7280; }
.gh-proof-item b { color:#1E40AF; }

/* ── pending import box ─────────────────────────────────────── */
.import-pending {
    background:#ECFDF5; border:1px solid #A7F3D0; border-radius:10px;
    padding:14px 18px; margin-top:12px;
}
.import-pending h5 { margin:0 0 6px 0; color:#065F46; }

/* ── wa preview ─────────────────────────────────────────────── */
.wa-preview {
    background:#F0FDF4; border:1px solid #BBF7D0; border-radius:10px;
    padding:14px 16px; font-family:'JetBrains Mono',monospace; font-size:.74rem;
    line-height:1.65; color:#166534; white-space:pre-wrap; word-break:break-all;
    max-height:300px; overflow-y:auto;
}

/* ── sidebar ────────────────────────────────────────────────── */
section[data-testid="stSidebar"] { background:#F0F2F8; border-right:1px solid #E5E7EB; }

/* ── run button ─────────────────────────────────────────────── */
.stButton>button {
    background:linear-gradient(135deg,#4361EE,#7209B7);
    color:#fff; border:none; border-radius:10px;
    font-weight:600; transition:.2s;
    box-shadow: 0 4px 12px rgba(67, 97, 238, 0.3);
}
.stButton>button:hover { opacity:.9; transform:translateY(-1px); box-shadow: 0 6px 16px rgba(67, 97, 238, 0.4); }
div[data-testid="stDataFrame"] { background:#FFFFFF; border-radius:10px; box-shadow: 0 2px 10px rgba(0,0,0,0.03); }

/* ── section divider label ──────────────────────────────────── */
.sec-label {
    font-size:.7rem; text-transform:uppercase; letter-spacing:.1em;
    color:#9CA3AF; font-weight:700; margin: 10px 0 6px;
}

/* ── st.expander ────────────────────────────────────────────── */
div[data-testid="stExpander"] {
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 10px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.02);
}
</style>
"""
