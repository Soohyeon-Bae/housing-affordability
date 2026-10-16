# 시군구 주거부담 지도 (Python)

Streamlit으로 실행하는 행정구역별 가격소득비율(PIR) 지도입니다. 지표, 연도, 전용면적, 소득 기준, 시도 범위를 선택할 수 있고, 시도 선택 시 지도가 해당 경계에 맞춰 확대됩니다. 지도 폴리곤을 누르면 팝업이 열리고, 오른쪽의 지역 선택에서 상세 수치를 확인합니다. 지도 색상은 코랄 단일 팔레트입니다.

## 실행 방법

Python 3.10 이상을 준비한 뒤 프로젝트 폴더에서 실행합니다.

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

macOS / Linux:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

브라우저에서 Streamlit이 안내하는 로컬 주소(기본 `http://localhost:8501`)를 엽니다.
Folium 지도를 그리는 데 브라우저가 Leaflet 정적 파일을 불러올 수 있도록 인터넷 연결이 필요합니다.

## GitHub에 올리기

`app.py`, `requirements.txt`, `README.md`, `.gitignore`, `data/`를 저장소에 포함하세요. `data/`에는 개인별 기록이 아닌 시군구별 집계 결과와 시군구 경계만 있습니다. 원자료 개인 레코드는 포함하지 마세요.

```bash
git init
git add app.py requirements.txt README.md .gitignore data
git commit -m "Add local PIR map app"
```

## 데이터 구성

- `data/pir.json`: 연도 × 시군구 × 전용면적 × 소득기준별 PIR, 가격, 소득, 거래 수, 가구 수
- `data/boundaries.geojson`: 지표 코드에 맞춰 연결한 2024년 시군구 경계

`PIR_지도용`에서 사용하는 집계 결과를 앱에서 읽기 쉬운 JSON으로 저장한 파일입니다. 가격은 더 작은 행정구역의 거래 원자료를 소득자료 시군구 기준으로 합친 뒤 중위값을 다시 계산한 값입니다. 세부 구역별 중위가격의 평균을 내지 않습니다.

## 선택 항목

- 지도 지표: PIR, 아파트 중위 거래가격, 중위 가구소득, 거래 건수
- 연도: 2022–2024
- 전용면적: 전체 및 5개 면적 구간
- 소득 기준: 행정자료(원자료 중위소득), 신용자료(보정 중위소득)
- 지역 범위: 전국 또는 시도

지도에 값이 없는 시군구는 회색으로 표시됩니다.
