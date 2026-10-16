from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import folium
import numpy as np
import pandas as pd
import streamlit as st
from branca.element import Element
from streamlit_folium import st_folium


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
AREAS = [
    "전체 면적",
    "40㎡ 미만",
    "40~60㎡ 미만",
    "60~85㎡ 미만",
    "85~102㎡ 미만",
    "102㎡ 이상",
]
BASIS_IDS = {"행정자료": "원자료 중위소득", "신용자료": "보정 중위소득"}
METRICS = {
    "가격소득비율 (PIR)": "pir",
    "아파트 중위 거래가격": "price",
    "중위 가구소득": "income",
    "아파트 거래 건수": "transactions",
}
CORAL = ["#fff1ec", "#fecaca", "#f87171", "#e11d48", "#881337"]
NO_DATA = "#d8e0de"

st.set_page_config(page_title="시군구 주거부담 지도", page_icon="🏘️", layout="wide")


@st.cache_data(show_spinner=False)
def load_data() -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load the aggregated PIR rows and the matching 2024 district boundaries."""
    rows = pd.read_json(DATA_DIR / "pir.json", encoding="utf-8")
    rows["code"] = rows["code"].astype(str).str.zfill(5)
    rows["year"] = rows["year"].astype(int)
    with (DATA_DIR / "boundaries.geojson").open(encoding="utf-8") as file:
        boundaries = json.load(file)
    for feature in boundaries.get("features", []):
        feature["properties"]["code"] = str(feature["properties"]["code"]).zfill(5)
    return rows, boundaries


def fmt(value: Any, digits: int = 0) -> str:
    if value is None or pd.isna(value):
        return "자료 없음"
    return f"{float(value):,.{digits}f}"


def value_for(row: pd.Series | None, metric: str) -> float | None:
    if row is None:
        return None
    value = row.get(metric)
    if value is None or pd.isna(value):
        return None
    if metric == "income":
        return float(value) / 10_000  # 원 단위 → 만원 단위
    return float(value)


def format_metric(value: float | None, metric: str) -> str:
    if value is None:
        return "자료 없음"
    if metric == "pir":
        return f"{fmt(value, 1)}배"
    if metric == "transactions":
        return f"{fmt(value)}건"
    return f"{fmt(value)}만원"


def quantile_breaks(values: list[float]) -> list[float]:
    if not values:
        return []
    return [float(x) for x in np.quantile(values, [0, .2, .4, .6, .8, 1])]


def quantile_class(value: float | None, breaks: list[float]) -> int:
    if value is None or not breaks:
        return 0
    return int(np.searchsorted(breaks[1:-1], value, side="left")) + 1


def legend_text(value: float, metric: str) -> str:
    return fmt(value, 1 if metric == "pir" else 0)


def all_coordinates(node: Any):
    if isinstance(node, list) and len(node) >= 2 and isinstance(node[0], (int, float)):
        yield node[0], node[1]
    elif isinstance(node, list):
        for child in node:
            yield from all_coordinates(child)


def fit_bounds(features: list[dict[str, Any]]) -> list[list[float]] | None:
    points = [point for feature in features for point in all_coordinates(feature["geometry"]["coordinates"])]
    if not points:
        return None
    longitudes, latitudes = zip(*points)
    return [[min(latitudes), min(longitudes)], [max(latitudes), max(longitudes)]]


def make_map(
    features: list[dict[str, Any]],
    rows_by_code: dict[str, pd.Series],
    metric: str,
    breaks: list[float],
    selected_code: str,
    map_key: str,
    view_state: dict[str, Any] | None = None,
    fit_to_region: bool = True,
) -> dict[str, Any]:
    colored_features: list[dict[str, Any]] = []
    for source in features:
        feature = json.loads(json.dumps(source))
        props = feature["properties"]
        code = props["code"]
        row = rows_by_code.get(code)
        value = value_for(row, metric) if row is not None else None
        class_id = quantile_class(value, breaks)
        props["map_value"] = format_metric(value, metric)
        props["fill_color"] = CORAL[class_id - 1] if class_id else NO_DATA
        colored_features.append(feature)

    map_bounds = fit_bounds(colored_features)
    if map_bounds is None:
        map_bounds = [[33.0, 124.0], [39.5, 132.0]]
    center = [(map_bounds[0][0] + map_bounds[1][0]) / 2, (map_bounds[0][1] + map_bounds[1][1]) / 2]
    view_state = view_state or {}
    saved_center = view_state.get("center")
    if isinstance(saved_center, dict):
        saved_center = [saved_center.get("lat"), saved_center.get("lng")]
    if isinstance(saved_center, (list, tuple)) and len(saved_center) == 2 and all(v is not None for v in saved_center):
        center = [float(saved_center[0]), float(saved_center[1])]
    saved_zoom = view_state.get("zoom")
    zoom_start = int(saved_zoom) if saved_zoom is not None else 7
    fmap = folium.Map(
        location=center,
        zoom_start=zoom_start,
        tiles=None,
        zoom_control=True,
        control_scale=False,
        prefer_canvas=True,
        max_zoom=12,
        min_zoom=5,
    )
    fmap.get_root().html.add_child(Element("<style>.leaflet-container{background:#f1f5f4}</style>"))
    folium.GeoJson(
        {"type": "FeatureCollection", "features": colored_features},
        name="시군구 지표",
        style_function=lambda feature: {
            "fillColor": feature["properties"]["fill_color"],
            "color": "#fff8f6",
            "weight": 2.1 if feature["properties"]["code"] == selected_code else 0.65,
            "fillOpacity": 0.9,
        },
        highlight_function=lambda _feature: {"color": "#5e1730", "weight": 2.2},
        tooltip=folium.GeoJsonTooltip(
            fields=["name", "map_value"],
            aliases=["시군구", metric_label_from_key(metric)],
            sticky=False,
            style="background-color:white;color:#243b38;font-family:'Malgun Gothic',sans-serif;font-size:12px;padding:8px;",
        ),
        popup=folium.GeoJsonPopup(
            fields=["name", "code", "map_value"],
            aliases=["시군구", "시군구 코드", metric_label_from_key(metric)],
        ),
    ).add_to(fmap)
    # Keep the user's current map view while data filters change. Refit only
    # when the selected province changes (or on the first render).
    if fit_to_region and saved_zoom is None:
        fmap.fit_bounds(map_bounds, padding=(16, 16))
    result = st_folium(
        fmap,
        height=570,
        use_container_width=True,
        key=map_key,
        returned_objects=["last_active_drawing", "last_object_clicked_popup"],
    )
    return result or {}


def metric_label_from_key(metric: str) -> str:
    return next(label for label, key in METRICS.items() if key == metric)


def render_legend(breaks: list[float], metric: str) -> None:
    if not breaks:
        st.caption("표시할 값이 없습니다. 회색은 거래 자료가 없거나 값을 계산할 수 없는 지역입니다.")
        return
    labels = [f"{legend_text(breaks[i], metric)}–{legend_text(breaks[i + 1], metric)}" for i in range(5)]
    chips = "".join(
        f'<div style="flex:1;min-width:45px"><div style="height:10px;background:{CORAL[i]};border-radius:3px 3px 0 0"></div>'
        f'<div style="font-size:10px;color:#687a75;padding-top:4px;white-space:nowrap">{labels[i]}</div></div>'
        for i in range(5)
    )
    st.markdown(
        f'<div style="display:flex;gap:3px;align-items:stretch">{chips}</div>'
        f'<div style="font-size:10px;color:#7a8985;margin-top:6px"><span style="display:inline-block;width:10px;height:10px;background:{NO_DATA};margin-right:5px;border-radius:2px"></span>자료 없음</div>',
        unsafe_allow_html=True,
    )


def main() -> None:
    st.markdown(
        """
        <style>
        .stApp{background:#eef3f2;color:#172a2c}
        [data-testid="stHeader"]{background:transparent}
        .block-container{padding:1.2rem 1.35rem 1.5rem;max-width:1800px}
        .pir-topbar{height:68px;background:#123b3c;color:#f7fbfa;display:flex;align-items:center;justify-content:space-between;padding:0 20px;margin:-.4rem 0 1rem;border-radius:12px}
        .pir-brand{display:flex;align-items:center;gap:11px}.pir-brand b{display:block;font-size:16px}.pir-brand small{display:block;color:#c2d5ce;font-size:10px;margin-top:3px}.pir-mark{width:32px;height:32px;border-radius:9px;background:#f87171;color:#fff;display:grid;place-items:center;font-weight:800}.pir-topbar>span{font-size:11px;color:#d3dfdc}
        h1,h2,h3{letter-spacing:-.03em}
        div[data-testid="stVerticalBlockBorderWrapper"]{background:white;border:1px solid #dce5e2;border-radius:13px;padding:14px 16px;box-shadow:0 2px 8px #123b3c0a}
        .stCaption{color:#71827d}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="pir-topbar"><div class="pir-brand"><span class="pir-mark">₩</span>'
        '<div><b>시군구 주거부담 지도</b><small>시군구별 주택가격소득비율 탐색</small></div></div>'
        '<span>2022–2024 · 전국 시군구</span></div>',
        unsafe_allow_html=True,
    )

    data, geojson = load_data()
    features = geojson.get("features", [])
    provinces = sorted({str(f["properties"]["name"]).split()[0] for f in features})

    left, center, right = st.columns([2.7, 6.1, 2.9], gap="small")
    with left:
        with st.container(border=True):
            st.markdown("**지도 기준 선택**")
            st.caption("연도와 면적, 소득 기준에 따라 지역별 주거 부담을 비교합니다.")
            metric_label = st.selectbox("지도 지표", list(METRICS))
            metric = METRICS[metric_label]
            year = st.selectbox("연도", sorted(data["year"].unique().tolist()), index=len(data["year"].unique()) - 1)
            area = st.selectbox("전용면적", AREAS, index=0)
            basis_label = st.radio("소득 기준", list(BASIS_IDS), horizontal=True)
            basis_id = BASIS_IDS[basis_label]
            province = st.selectbox("지역 범위", ["전국", *provinces])
            st.markdown("**지도 색상**")
            st.markdown(
                '<div style="display:flex;gap:2px;height:9px;border-radius:4px;overflow:hidden">'
                '<i style="background:#fff1ec;flex:1"></i><i style="background:#fecaca;flex:1"></i>'
                '<i style="background:#f87171;flex:1"></i><i style="background:#e11d48;flex:1"></i>'
                '<i style="background:#881337;flex:1"></i></div><small>코랄 · 낮은 값에서 높은 값 순서</small>',
                unsafe_allow_html=True,
            )
            st.divider()
            st.markdown("**가격 계산**")
            st.caption("세부 행정구역의 거래 원자료를 소득자료 시군구 기준으로 합산한 뒤 중위가격을 다시 계산합니다. 세부 지역 중위가격의 평균은 사용하지 않습니다.")
            st.markdown("**범례**")
            st.caption("현재 조건에서 값이 있는 지역을 5분위로 나눕니다. 회색은 거래 자료가 없거나 값을 계산할 수 없는 지역입니다.")

    current = data[(data["year"] == year) & (data["area"] == area) & (data["basis"] == basis_id)].copy()
    current[metric] = pd.to_numeric(current[metric], errors="coerce")
    by_code = {row["code"]: row for _, row in current.iterrows()}
    visible_features = [
        feature for feature in features
        if province == "전국" or str(feature["properties"]["name"]).startswith(province)
    ]
    visible_codes = {feature["properties"]["code"] for feature in visible_features}
    values = [value_for(by_code.get(code), metric) for code in visible_codes]
    finite_values = [float(value) for value in values if value is not None and np.isfinite(value)]
    breaks = quantile_breaks(finite_values)
    available = current[current["code"].isin(visible_codes) & current[metric].notna()].copy()
    available = available.sort_values("name")
    code_to_name = {f["properties"]["code"]: f["properties"]["name"] for f in visible_features}
    name_to_code = {name: code for code, name in code_to_name.items()}
    district_key = f"district-selector-{province}"
    if "selected_code" not in st.session_state or st.session_state["selected_code"] not in visible_codes:
        st.session_state["selected_code"] = next(iter(sorted(visible_codes)), None)

    with center:
        with st.container(border=True):
            st.markdown(f"**{year}년 · {area} · {metric_label}**")
            previous_province = st.session_state.get("map_province")
            province_changed = previous_province != province
            map_key = "pir-map"
            map_result = make_map(
                visible_features, by_code, metric, breaks,
                st.session_state["selected_code"], map_key,
                view_state=None if province_changed else st.session_state.get("map_view"),
                fit_to_region=province_changed,
            )
            if map_result.get("center") is not None and map_result.get("zoom") is not None:
                st.session_state["map_view"] = {
                    "center": map_result["center"],
                    "zoom": map_result["zoom"],
                }
            st.session_state["map_province"] = province
            drawing = map_result.get("last_active_drawing") or {}
            clicked_code = str(drawing.get("properties", {}).get("code", ""))
            popup_text = str(map_result.get("last_object_clicked_popup") or "")
            popup_match = re.search(r"(?<!\d)(\d{5})(?!\d)", popup_text)
            if popup_match:
                clicked_code = popup_match.group(1)
            if clicked_code in visible_codes:
                st.session_state["selected_code"] = clicked_code
                if clicked_code in code_to_name:
                    st.session_state[district_key] = code_to_name[clicked_code]
            render_legend(breaks, metric)
            st.caption(f"{len(visible_features)}개 시군구 · {len(finite_values)}개 지역 값 표시")

    with right:
        with st.container(border=True):
            st.markdown("**선택 지역 상세와 순위**")
            options = sorted(name_to_code)
            current_code = st.session_state.get("selected_code")
            default_name = code_to_name.get(current_code, options[0] if options else "")
            if options:
                selected_name = st.selectbox(
                    "선택 지역",
                    options,
                    index=options.index(default_name),
                    key=district_key,
                )
                selected_code = name_to_code[selected_name]
                st.session_state["selected_code"] = selected_code
            else:
                selected_code = ""
                st.info("선택한 조건에 해당하는 시군구가 없습니다.")

            selected_row = by_code.get(selected_code)
            selected_value = value_for(selected_row, metric)
            st.metric(metric_label, format_metric(selected_value, metric))
            if selected_row is not None:
                price = value_for(selected_row, "price")
                income = value_for(selected_row, "income")
                transactions = value_for(selected_row, "transactions")
                st.markdown("**선택 조건 세부 값**")
                st.write(f"아파트 중위가격　{format_metric(price, 'price')}")
                income_rows = data[(data["code"] == selected_code) & (data["year"] == year) & (data["area"] == area)]
                income_lookup = {r["basis"]: r for _, r in income_rows.iterrows()}
                for display, source in BASIS_IDS.items():
                    row = income_lookup.get(source)
                    st.write(f"{display} 중위소득　{format_metric(value_for(row, 'income') if row is not None else None, 'income')}")
                st.write(f"가격 거래 건수　{format_metric(transactions, 'transactions')}")
                households = selected_row.get("households")
                st.write(f"소득 자료 가구수　{fmt(households)}가구")

                trend_rows = data[(data["code"] == selected_code) & (data["area"] == area) & (data["basis"] == basis_id)]
                st.markdown(f"**{metric_label} 연도별 추이**")
                trend_cols = st.columns(3)
                for col, trend_year in zip(trend_cols, [2022, 2023, 2024]):
                    trend_match = trend_rows[trend_rows["year"] == trend_year]
                    trend_row = trend_match.iloc[0] if not trend_match.empty else None
                    with col:
                        st.caption(str(trend_year))
                        st.markdown(f"**{format_metric(value_for(trend_row, metric), metric)}**")

            st.divider()
            rank_title = "소득이 높은 지역" if metric == "income" else "거래가 많은 지역" if metric == "transactions" else "값이 높은 지역"
            st.markdown(f"**{rank_title}**")
            if available.empty:
                st.caption("현재 조건에서 계산된 값이 없습니다.")
            else:
                ranking = available.copy()
                ranking["display_value"] = ranking[metric].map(
                    lambda value: format_metric(value_for(pd.Series({metric: value}), metric), metric)
                )
                ranking = ranking.sort_values(metric, ascending=False).head(8)
                for rank, (_, ranked) in enumerate(ranking.iterrows(), start=1):
                    st.markdown(f"`{rank:02d}`　{ranked['name']}　 **{ranked['display_value']}**")


if __name__ == "__main__":
    main()
