"""
map_view.py — Builder peta Folium untuk visualisasi rute hasil optimasi CFRS.
"""

import folium
from datetime import date, datetime, timedelta
from typing import List

from graphhopper import Location
from styles import VEHICLE_COLORS
from helpers import fetch_route_geometry


def build_map(
    locations: List[Location],
    results: list,
    dep_hour: float,
    gh_url: str = "http://localhost:8989",
    gh_profile: str = "car",
    filter_vehicles: list | None = None,   # None = semua
    delivery_date: date | None = None,     # untuk ETA display
) -> folium.Map:
    depot = locations[0]
    m = folium.Map(location=[depot.lat, depot.lon], zoom_start=13,
                   tiles="CartoDB positron")
    d = delivery_date or date.today()
    dep_dt = datetime(d.year, d.month, d.day, int(dep_hour), int((dep_hour % 1) * 60))

    folium.Marker(
        [depot.lat, depot.lon],
        popup=folium.Popup(f"<b>🍱 {depot.name}</b><br>DEPOT", max_width=200),
        tooltip="Dapur (Depot)",
        icon=folium.Icon(color="black", icon="home", prefix="fa"),
    ).add_to(m)

    for idx_r, r in enumerate(results):
        vid = r["vehicle_id"]
        if filter_vehicles and vid not in filter_vehicles:
            continue

        color    = VEHICLE_COLORS[idx_r % len(VEHICLE_COLORS)]
        route    = r["route"]
        arrivals = r["arrivals"]

        if not route:
            continue

        road_coords = fetch_route_geometry(gh_url, gh_profile, depot, locations, route)
        if road_coords:
            folium.PolyLine(
                [[c[1], c[0]] for c in road_coords],
                color=color, weight=4, opacity=0.85,
                tooltip=vid,
                dash_array=None if r["feasible"] else "8 4",
            ).add_to(m)
        else:
            coords = [[depot.lat, depot.lon]]
            for ci in route:
                coords.append([locations[ci].lat, locations[ci].lon])
            coords.append([depot.lat, depot.lon])
            folium.PolyLine(coords, color=color, weight=4, opacity=0.85,
                            tooltip=vid, dash_array=None if r["feasible"] else "8 4").add_to(m)

        for stop_idx, (ci, arr) in enumerate(zip(route, arrivals)):
            loc       = locations[ci]
            eta       = dep_dt + timedelta(minutes=arr)
            late_flag = " ⚠️ TERLAMBAT" if arr > 180 else ""
            popup_html = f"""
            <div style="font-family:'Segoe UI',sans-serif;min-width:190px">
              <div style="background:{color};color:#fff;padding:6px 10px;
                          border-radius:4px 4px 0 0;font-weight:700">
                {vid} — Stop #{stop_idx+1}
              </div>
              <div style="padding:8px 10px;border:1px solid #eee;border-top:none;
                          border-radius:0 0 4px 4px">
                <b>{loc.name}</b><br>
                📦 Demand : {loc.demand} box<br>
                ⏱ Tiba   : {arr:.1f} menit{late_flag}<br>
                🕐 ETA    : {eta.strftime('%H:%M')}
              </div>
            </div>"""
            icon_html = f"""
            <div style="background:{color};color:#fff;border-radius:50%;
                        width:26px;height:26px;display:flex;align-items:center;
                        justify-content:center;font-weight:700;font-size:12px;
                        border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.35)">
              {stop_idx+1}
            </div>"""
            folium.Marker(
                [loc.lat, loc.lon],
                popup=folium.Popup(popup_html, max_width=230),
                tooltip=f"{vid} | Stop {stop_idx+1} | {loc.name}",
                icon=folium.DivIcon(html=icon_html, icon_size=(26, 26), icon_anchor=(13, 13)),
            ).add_to(m)

    all_lats = [l.lat for l in locations]
    all_lons = [l.lon for l in locations]
    m.fit_bounds([[min(all_lats)-.005, min(all_lons)-.005],
                  [max(all_lats)+.005, max(all_lons)+.005]])
    return m
