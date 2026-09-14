from __future__ import annotations

from io import BytesIO
import re
import pandas as pd

from .config import BOHOL_CENTER, LAND_USE_ORDER


SOURCE_COLUMNS = {
    "land_use": 9,
    "total": 10,
    "developed": 11,
    "remaining": 12,
    "lc_name": 13,
    "lc_zone": 14,
    "lc_area": 15,
    "lc_balance": 16,
    "lc_applied": 17,
    "lc_issued": 18,
    "reclass_allowable": 19,
    "reclass_name": 20,
    "reclass_to": 21,
    "reclass_area": 22,
    "reclass_balance": 23,
    "reclass_applied": 24,
    "reclass_approved": 25,
    "approved_by": 26,
    "remarks": 27,
}


def _number(value) -> float:
    return float(pd.to_numeric(value, errors="coerce")) if pd.notna(pd.to_numeric(value, errors="coerce")) else 0.0


def _clean(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _year(value, default: int) -> int:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.notna(parsed):
        return int(parsed.year)
    numeric = int(_number(value))
    return numeric if numeric else default


def _planning_year_shift(raw: pd.DataFrame) -> int:
    headers = [_clean(value).casefold() for value in raw.iloc[1].tolist()]
    return 1 if any("number of planning years" in value for value in headers) else 0


def _category(label: str) -> str | None:
    text = label.casefold()
    if "settlement" in text:
        return "Settlement Areas"
    if "production areas" in text:
        return "Production Areas"
    if "infrastructure areas" in text:
        return "Infrastructure Areas"
    if "protection areas" in text:
        return "Protection Areas"
    if "municipal water" in text:
        return "Municipal Water"
    return None


def _read(source) -> pd.DataFrame:
    if hasattr(source, "seek"):
        source.seek(0)
    return pd.read_excel(source, sheet_name=0, header=None, engine="openpyxl")


def parse_master(source) -> pd.DataFrame:
    raw = _read(source)
    column_shift = _planning_year_shift(raw)
    rows, active = [], None
    header = [_clean(value).casefold() for value in raw.iloc[1].tolist()] if len(raw) > 1 else []
    latitude_col = next((i for i, value in enumerate(header) if value in ("latitude", "lat")), None)
    longitude_col = next((i for i, value in enumerate(header) if value in ("longitude", "lng", "lon", "long")), None)
    def first_value(column, default=""):
        if column >= raw.shape[1]:
            return default
        values = [_clean(value) for value in raw.iloc[2:, column].tolist()]
        return next((value for value in values if value and not value.startswith("=")), default)

    municipality = first_value(0, "Bohol")
    province = first_value(2, "Bohol")
    region = first_value(3, "Region VII")
    clup_status = first_value(5, "Not specified")
    planning_from = pd.to_datetime(first_value(6, 0), errors="coerce")
    planning_to = pd.to_datetime(first_value(7, 0), errors="coerce")
    approval_year = _year(first_value(6, 0), 1900)
    end_year = _year(first_value(7, 0), 2050)
    planning_years = (
        int(_number(first_value(8, 0))) if column_shift else max(end_year - approval_year, 0)
    )
    for _, row in raw.iloc[3:].iterrows():
        row_municipality = _clean(row.iloc[0] if len(row) else "")
        if row_municipality:
            municipality = row_municipality
        latitude = _number(row.iloc[latitude_col]) if latitude_col is not None and latitude_col < len(row) else BOHOL_CENTER["latitude"]
        longitude = _number(row.iloc[longitude_col]) if longitude_col is not None and longitude_col < len(row) else BOHOL_CENTER["longitude"]
        latitude = latitude or BOHOL_CENTER["latitude"]
        longitude = longitude or BOHOL_CENTER["longitude"]
        label_col = SOURCE_COLUMNS["land_use"] + column_shift
        label = _clean(row.iloc[label_col] if len(row) > label_col else "")
        section = _category(label)
        if section:
            active = section
            total = _number(row.iloc[SOURCE_COLUMNS["total"] + column_shift])
            developed = _number(row.iloc[SOURCE_COLUMNS["developed"] + column_shift])
            remaining = _number(row.iloc[SOURCE_COLUMNS["remaining"] + column_shift])
            # Municipal Water stores its figures directly on the section row.
            # The other section rows contain Excel subtotal formulas, which
            # pandas reads as text and are therefore ignored here.
            if section == "Municipal Water" and any((total, developed, remaining)):
                rows.append({
                    "Municipality": municipality,
                    "Region": region,
                    "Province": province,
                    "CLUP Status": clup_status,
                    "Approval Year": approval_year,
                    "End Year": end_year,
                    "Planning Period From": planning_from,
                    "Planning Period To": planning_to,
                    "Number of Planning Years": planning_years,
                    "Latitude": latitude,
                    "Longitude": longitude,
                    "Category": active,
                    "Zoning Classification": active,
                    "Total Area": total,
                    "Developed Area": developed,
                    "Still to Be Developed": remaining if remaining else max(total - developed, 0),
                })
            continue
        if not active or not label or re.match(r"^\d+\.", label):
            continue
        total = _number(row.iloc[SOURCE_COLUMNS["total"] + column_shift])
        developed = _number(row.iloc[SOURCE_COLUMNS["developed"] + column_shift])
        remaining_raw = _number(row.iloc[SOURCE_COLUMNS["remaining"] + column_shift])
        if not any((total, developed, remaining_raw)):
            continue
        rows.append({
            "Municipality": municipality,
            "Region": region,
            "Province": province,
            "CLUP Status": clup_status,
            "Approval Year": approval_year,
            "End Year": end_year,
            "Planning Period From": planning_from,
            "Planning Period To": planning_to,
            "Number of Planning Years": planning_years,
            "Latitude": latitude,
            "Longitude": longitude,
            "Category": active,
            "Zoning Classification": label.lstrip("- "),
            "Total Area": total,
            "Developed Area": developed,
            "Still to Be Developed": remaining_raw if remaining_raw else max(total - developed, 0),
        })
    return pd.DataFrame(rows)


def parse_locational(source) -> pd.DataFrame:
    raw = _read(source)
    column_shift = _planning_year_shift(raw)
    rows = []
    for _, row in raw.iloc[3:].iterrows():
        name = _clean(row.iloc[SOURCE_COLUMNS["lc_name"] + column_shift])
        zone = _clean(row.iloc[SOURCE_COLUMNS["lc_zone"] + column_shift])
        area = _number(row.iloc[SOURCE_COLUMNS["lc_area"] + column_shift])
        applied = pd.to_datetime(row.iloc[SOURCE_COLUMNS["lc_applied"] + column_shift], errors="coerce")
        if not any((name, zone, area)) and pd.isna(applied):
            continue
        rows.append({
            "Issued To": name or "Not specified",
            "Zoning Classification": zone or "Not specified",
            "Area (ha)": area,
            "Still to Be Developed (ha)": _number(row.iloc[SOURCE_COLUMNS["lc_balance"] + column_shift]),
            "Date Applied": applied,
            "Date Issued": pd.to_datetime(row.iloc[SOURCE_COLUMNS["lc_issued"] + column_shift], errors="coerce"),
        })
    return pd.DataFrame(rows)


def parse_reclassification(source) -> pd.DataFrame:
    raw = _read(source)
    column_shift = _planning_year_shift(raw)
    headers = [_clean(value).casefold() for value in raw.iloc[1].tolist()]
    planning_columns = [i for i, value in enumerate(headers) if "number of planning years" in value]
    reclass_planning_col = planning_columns[-1] if len(planning_columns) > 1 else None
    overall_planning_col = planning_columns[0] if planning_columns else None
    overall_planning_years = 0
    if overall_planning_col is not None:
        overall_planning_years = next(
            (int(_number(value)) for value in raw.iloc[2:, overall_planning_col] if _number(value) > 0),
            0,
        )
    remarks_col = next((i for i, value in enumerate(headers) if value == "remarks"), SOURCE_COLUMNS["remarks"] + column_shift)
    rows = []
    for _, row in raw.iloc[3:].iterrows():
        name = _clean(row.iloc[SOURCE_COLUMNS["reclass_name"] + column_shift])
        target = _clean(row.iloc[SOURCE_COLUMNS["reclass_to"] + column_shift])
        area = _number(row.iloc[SOURCE_COLUMNS["reclass_area"] + column_shift])
        applied = pd.to_datetime(row.iloc[SOURCE_COLUMNS["reclass_applied"] + column_shift], errors="coerce")
        approved = pd.to_datetime(row.iloc[SOURCE_COLUMNS["reclass_approved"] + column_shift], errors="coerce")
        planning_years = (
            int(_number(row.iloc[reclass_planning_col])) if reclass_planning_col is not None else 0
        ) or overall_planning_years
        if not any((name, target, area)) and pd.isna(applied) and pd.isna(approved):
            continue
        rows.append({
            "Applicant": name or "Not specified",
            "Reclassified To": target or "Not specified",
            "Area (ha)": area,
            "Net Balance (ha)": _number(row.iloc[SOURCE_COLUMNS["reclass_balance"] + column_shift]),
            "Date Applied": applied,
            "Date Approved": approved,
            "Approved By": _clean(row.iloc[SOURCE_COLUMNS["approved_by"] + column_shift]),
            "Number of Planning Years": planning_years,
            "Remarks": _clean(row.iloc[remarks_col]),
        })
    return pd.DataFrame(rows)


def parse_table_upload(source, record_type: str) -> pd.DataFrame:
    """Accept the original 29-column workbook or a clean exported record table."""
    if hasattr(source, "seek"):
        source.seek(0)
    try:
        raw = pd.read_excel(source, sheet_name=0)
        normalized = {str(c).strip().casefold(): c for c in raw.columns}
        if record_type == "locational" and any("zoning classification" in key for key in normalized):
            rename = {}
            for key, col in normalized.items():
                if "issued to" in key: rename[col] = "Issued To"
                elif "zoning classification" in key: rename[col] = "Zoning Classification"
                elif key.startswith("area"): rename[col] = "Area (ha)"
                elif "still to be developed" in key or "net balance" in key: rename[col] = "Still to Be Developed (ha)"
                elif "date applied" in key: rename[col] = "Date Applied"
                elif "date issued" in key: rename[col] = "Date Issued"
            result = raw.rename(columns=rename)
            for col in ["Area (ha)", "Still to Be Developed (ha)"]:
                if col in result: result[col] = pd.to_numeric(result[col], errors="coerce").fillna(0)
            for col in ["Date Applied", "Date Issued"]:
                if col in result: result[col] = pd.to_datetime(result[col], errors="coerce")
            return result[[c for c in ["Issued To", "Zoning Classification", "Area (ha)", "Still to Be Developed (ha)", "Date Applied", "Date Issued"] if c in result]]
        if record_type == "reclassification" and any("reclassified" in key for key in normalized):
            rename = {}
            for key, col in normalized.items():
                if "reclassification" in key and "name" in key: rename[col] = "Applicant"
                elif "reclassified to" in key: rename[col] = "Reclassified To"
                elif key.startswith("area"): rename[col] = "Area (ha)"
                elif "net balance" in key: rename[col] = "Net Balance (ha)"
                elif "date applied" in key: rename[col] = "Date Applied"
                elif "date approved" in key: rename[col] = "Date Approved"
                elif "approved by" in key: rename[col] = "Approved By"
                elif "number of planning years" in key: rename[col] = "Number of Planning Years"
                elif "remarks" in key: rename[col] = "Remarks"
            result = raw.rename(columns=rename)
            for col in ["Area (ha)", "Net Balance (ha)"]:
                if col in result: result[col] = pd.to_numeric(result[col], errors="coerce").fillna(0)
            for col in ["Date Applied", "Date Approved"]:
                if col in result: result[col] = pd.to_datetime(result[col], errors="coerce")
            if "Number of Planning Years" in result:
                result["Number of Planning Years"] = pd.to_numeric(result["Number of Planning Years"], errors="coerce").fillna(0).astype(int)
            return result[[c for c in ["Applicant", "Reclassified To", "Area (ha)", "Net Balance (ha)", "Date Applied", "Date Approved", "Approved By", "Number of Planning Years", "Remarks"] if c in result]]
    except Exception:
        pass
    return parse_locational(source) if record_type == "locational" else parse_reclassification(source)


def load_all(source):
    content = source.read() if hasattr(source, "read") else None
    if content is not None:
        return (
            parse_master(BytesIO(content)),
            parse_locational(BytesIO(content)),
            parse_reclassification(BytesIO(content)),
        )
    return parse_master(source), parse_locational(source), parse_reclassification(source)
