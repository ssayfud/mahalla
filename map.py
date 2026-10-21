"""Build an interactive HTML map from mahalla.xlsx.

Run with:
    python map.py

Install the spreadsheet dependencies once with:
    python -m pip install pandas openpyxl

The generated HTML uses Leaflet and OpenStreetMap tiles from the internet.
"""

from pathlib import Path
import json
import math

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
EXCEL_FILE = BASE_DIR / "mahalla.xlsx"
OUTPUT_FILE = BASE_DIR / "mahalla_map.html"
SHEET_NAME = 0

LAT_COL = "MAHALLA_LAT"
LON_COL = "MAHALLA_LON"
NAME_COL = "NAME_UZ"
DISTRICT_COL = "DISTR_NAME"
STATUS_COL = "MAHALLA_STATUS"
SCORE_COL = "MAHALLA_MATCH_SCORE"
ALT_NAME_COL = "NAME_EN"
MATCHED_NAME_COL = "MAHALLA_MATCHED_NAME"


def clean_text(value: object) -> str:
    """Convert spreadsheet values to safe, readable strings."""
    if pd.isna(value):
        return ""
    return str(value).strip()


def main() -> None:
    if not EXCEL_FILE.exists():
        raise FileNotFoundError(f"Excel file not found: {EXCEL_FILE}")

    data = pd.read_excel(EXCEL_FILE, sheet_name=SHEET_NAME)
    missing = [column for column in (LAT_COL, LON_COL) if column not in data.columns]
    if missing:
        raise ValueError(f"Missing coordinate columns: {', '.join(missing)}")

    data[LAT_COL] = pd.to_numeric(data[LAT_COL], errors="coerce")
    data[LON_COL] = pd.to_numeric(data[LON_COL], errors="coerce")
    points = data.dropna(subset=[LAT_COL, LON_COL]).copy()
    points = points[
        points[LAT_COL].between(-90, 90) & points[LON_COL].between(-180, 180)
    ]
    if points.empty:
        raise ValueError("No valid latitude/longitude pairs were found.")

    if DISTRICT_COL in points.columns:
        points["_district"] = points[DISTRICT_COL].map(clean_text)
    else:
        points["_district"] = "District not specified"
    points.loc[points["_district"] == "", "_district"] = "District not specified"

    # Compact arrays keep the generated HTML reasonably small.
    records = []
    for _, row in points.iterrows():
        records.append(
            [
                round(float(row[LAT_COL]), 7),
                round(float(row[LON_COL]), 7),
                clean_text(row.get(NAME_COL, "Mahalla")) or "Mahalla",
                row["_district"],
                clean_text(row.get(STATUS_COL)),
                clean_text(row.get(SCORE_COL)),
                [
                    clean_text(row.get(ALT_NAME_COL)),
                    clean_text(row.get(MATCHED_NAME_COL)),
                ],
            ]
        )

    districts = sorted(points["_district"].unique(), key=str.casefold)
    center_lat = float(points[LAT_COL].mean())
    center_lon = float(points[LON_COL].mean())
    payload = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    # Prevent spreadsheet text from terminating the inline script element.
    payload = payload.replace("</", "<\\/")
    options = "\n".join(
        f'<option value="{district.replace("&", "&amp;").replace(chr(34), "&quot;").replace("<", "&lt;").replace(">", "&gt;")}">'
        f'{district.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")}</option>'
        for district in districts
    )

    html = f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Mahalla coordinates</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <style>
    html, body {{ height: 100%; margin: 0; font-family: Arial, sans-serif; }}
    #map {{ height: 100%; width: 100%; background: #f1f4f6; }}
    .panel {{ position: absolute; z-index: 1000; top: 12px; left: 58px;
      background: white; padding: 12px 14px; border-radius: 7px;
      box-shadow: 0 1px 7px #0003; min-width: 230px; }}
    .panel label {{ display: block; font-size: 13px; font-weight: 600; margin-bottom: 6px; }}
    .panel select {{ width: 100%; padding: 7px; font-size: 14px; }}
    .panel input {{ width: 100%; box-sizing: border-box; padding: 7px; font-size: 14px;
      margin-bottom: 9px; border: 1px solid #b9c3d0; border-radius: 4px; }}
    #suggestions {{ display: none; max-height: 260px; overflow-y: auto; margin: -7px 0 10px;
      border: 1px solid #d5dce5; border-radius: 4px; background: white; }}
    .suggestion {{ display: block; width: 100%; border: 0; border-bottom: 1px solid #edf0f4;
      background: white; text-align: left; padding: 8px 10px; cursor: pointer; }}
    .suggestion:hover, .suggestion:focus {{ background: #f0f5fb; outline: none; }}
    .suggestion-name {{ display: block; font-size: 13px; color: #172b4d; }}
    .suggestion-detail {{ display: block; font-size: 11px; color: #697789; margin-top: 2px; }}
    #summary {{ color: #526174; font-size: 12px; margin-top: 7px; }}
    .leaflet-popup-content {{ line-height: 1.5; }}
  </style>
</head>
<body>
  <div id="map"></div>
  <div class="panel">
    <label for="search">Search mahalla or district</label>
    <input id="search" type="search" placeholder="Type a name…" autocomplete="off">
    <div id="suggestions" role="listbox" aria-label="Matching mahallas and districts"></div>
    <label for="district">Filter by district</label>
    <select id="district">
      <option value="__all__">All districts ({len(districts)})</option>
      {options}
    </select>
    <div id="summary">Loading coordinates…</div>
  </div>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const points = {payload};
    const map = L.map('map', {{ preferCanvas: true }}).setView([{center_lat}, {center_lon}], 6);
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    }}).addTo(map);

    const renderer = L.canvas({{ padding: 0.5 }});
    const pointLayer = L.featureGroup().addTo(map);
    const districtSelect = document.getElementById('district');
    const searchInput = document.getElementById('search');
    const suggestionsBox = document.getElementById('suggestions');
    const summary = document.getElementById('summary');
    const esc = (value) => String(value).replace(/[&<>"']/g, ch => ({{
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }}[ch]));
    const cyrillicToLatin = {{
      'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'yo','ж':'j',
      'з':'z','и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o',
      'п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f','х':'x','ц':'ts',
      'ч':'ch','ш':'sh','щ':'shch','ъ':'','ы':'i','ь':'','э':'e','ю':'yu',
      'я':'ya','ў':"o'",'ғ':"g'",'қ':'q','ҳ':'h'
    }};
    function normalizeSearch(value) {{
      return Array.from(String(value).toLocaleLowerCase()
        .replace(/[ʻʼ’‘`´]/g, "'")
        .normalize('NFKD').replace(/[\\u0300-\\u036f]/g, ''))
        .map(ch => cyrillicToLatin[ch] ?? ch)
        .join('').replace(/\\s+/g, ' ').trim();
    }}

    function updateSuggestions(searchTerm) {{
      const query = normalizeSearch(searchTerm);
      suggestionsBox.replaceChildren();
      if (!query) {{ suggestionsBox.style.display = 'none'; return; }}

      const matches = [];
      const seen = new Set();
      for (const [lat, lon, name, district, status, score, aliases] of points) {{
        const districtKey = `district|${{district}}`;
        if (!seen.has(districtKey) && normalizeSearch(district).includes(query)) {{
          seen.add(districtKey);
          matches.push({{ kind: 'District', name: district, district, rank: normalizeSearch(district).startsWith(query) ? 0 : 1 }});
        }}
        const mahallaKey = `mahalla|${{name}}|${{district}}`;
        const searchableNames = [name, ...aliases].map(normalizeSearch);
        if (!seen.has(mahallaKey) && searchableNames.some(value => value.includes(query))) {{
          seen.add(mahallaKey);
          matches.push({{ kind: 'Mahalla', name, district, rank: searchableNames.some(value => value.startsWith(query)) ? 0 : 1 }});
        }}
      }}

      matches.sort((a, b) => a.rank - b.rank || a.name.localeCompare(b.name));
      const shown = matches;
      for (const item of shown) {{
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'suggestion';
        button.setAttribute('role', 'option');
        const nameLine = document.createElement('span');
        nameLine.className = 'suggestion-name';
        nameLine.textContent = item.name;
        const detailLine = document.createElement('span');
        detailLine.className = 'suggestion-detail';
        detailLine.textContent = item.kind === 'District' ? 'District' : `Mahalla · ${{item.district}}`;
        button.append(nameLine, detailLine);
        button.addEventListener('mousedown', event => event.preventDefault());
        button.addEventListener('click', () => {{
          if (item.kind === 'District') {{
            districtSelect.value = item.district;
            searchInput.value = '';
          }} else {{
            districtSelect.value = item.district;
            searchInput.value = item.name;
          }}
          suggestionsBox.style.display = 'none';
          refreshPoints();
        }});
        suggestionsBox.append(button);
      }}
      suggestionsBox.style.display = shown.length ? 'block' : 'none';
    }}

    function showPoints(selectedDistrict, searchTerm = '') {{
      pointLayer.clearLayers();
      let visible = 0;
      const matchingLocations = [];
      const query = normalizeSearch(searchTerm);
      for (const [lat, lon, name, district, status, score, aliases] of points) {{
        if (selectedDistrict !== '__all__' && district !== selectedDistrict) continue;
        const searchableNames = [name, district, ...aliases].map(normalizeSearch);
        if (query && !searchableNames.some(value => value.includes(query))) continue;
        visible++;
        matchingLocations.push([lat, lon]);
        const lines = [`<b>${{esc(name)}}</b>`, `District: ${{esc(district)}}`];
        if (status) lines.push(`Coordinate status: ${{esc(status)}}`);
        if (score) lines.push(`Match score: ${{esc(score)}}`);
        L.circleMarker([lat, lon], {{
          renderer, radius: 4, color: '#ffffff', weight: 0.7,
          fillColor: '#e4572e', fillOpacity: 0.88
        }}).bindPopup(lines.join('<br>')).bindTooltip(esc(name)).addTo(pointLayer);
      }}
      summary.textContent = `${{visible.toLocaleString()}} of ${{points.length.toLocaleString()}} mahallas`;
      if (query || selectedDistrict !== '__all__') {{
        if (matchingLocations.length) map.fitBounds(L.latLngBounds(matchingLocations).pad(0.12));
      }}
    }}

    let searchTimer;
    function refreshPoints() {{ showPoints(districtSelect.value, searchInput.value); }}
    districtSelect.addEventListener('change', refreshPoints);
    searchInput.addEventListener('input', () => {{
      updateSuggestions(searchInput.value);
      clearTimeout(searchTimer);
      searchTimer = setTimeout(refreshPoints, 180);
    }});
    searchInput.addEventListener('keydown', event => {{
      if (event.key === 'Escape') suggestionsBox.style.display = 'none';
    }});
    document.addEventListener('click', event => {{
      if (!suggestionsBox.contains(event.target) && event.target !== searchInput) {{
        suggestionsBox.style.display = 'none';
      }}
    }});
    showPoints('__all__', '');
    const bounds = L.latLngBounds(points.map(p => [p[0], p[1]]));
    if (bounds.isValid()) map.fitBounds(bounds.pad(0.04));
  </script>
</body>
</html>'''

    OUTPUT_FILE.write_text(html, encoding="utf-8")
    print(f"Created {OUTPUT_FILE.name} with {len(records):,} coordinates in {len(districts):,} districts.")
    print("Open the HTML in a browser with internet access to load the map and tiles.")


if __name__ == "__main__":
    main()
