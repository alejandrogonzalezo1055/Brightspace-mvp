"""
Descubrimiento de versiones [DOC]. Son rutas anónimas: no piden token.

  GET  /d2l/api/versions/
  GET  /d2l/api/(productCode)/versions/
  GET  /d2l/api/(productCode)/versions/(version)
  POST /d2l/api/versions/check
"""
from fastapi import APIRouter, Request

from app.errors import bad_request, not_found

router = APIRouter()
PRODUCTS = ("lp", "le")


def _product_versions(settings, product: str) -> dict:
    versions = settings.versions_for(product)
    return {"ProductCode": product, "LatestVersion": versions[-1], "SupportedVersions": versions}


def _supported(settings, product: str, version: str) -> dict:
    versions = settings.versions_for(product)
    return {"Supported": version in versions, "LatestVersion": versions[-1] if versions else None}


@router.get("/d2l/api/versions/")
def all_versions(request: Request):
    return [_product_versions(request.app.state.settings, p) for p in PRODUCTS]


@router.get("/d2l/api/{product}/versions/")
def product_versions(product: str, request: Request):
    if product not in PRODUCTS:
        raise not_found()
    return _product_versions(request.app.state.settings, product)


@router.get("/d2l/api/{product}/versions/{version}")
def check_one(product: str, version: str, request: Request):
    if product not in PRODUCTS:
        raise not_found()
    return _supported(request.app.state.settings, product, version)


@router.post("/d2l/api/versions/check")
async def check_bulk(request: Request):
    try:
        body = await request.json()
    except ValueError:
        raise bad_request("Invalid JSON")
    if not isinstance(body, list):
        raise bad_request("Expected an array of SupportedVersionRequest")
    settings = request.app.state.settings
    results = []
    for item in body:
        if not isinstance(item, dict) or not isinstance(item.get("ProductCode"), str) or not isinstance(item.get("Version"), str):
            raise bad_request("Each item needs ProductCode and Version")
        check = _supported(settings, item["ProductCode"], item["Version"])
        results.append({"ProductCode": item["ProductCode"], "Version": item["Version"], **check})
    return {"Supported": all(r["Supported"] for r in results), "Versions": results}
