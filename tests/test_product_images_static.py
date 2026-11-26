"""Verify static product WebP assets, cache headers, and Butter migration/redirect integrity."""
import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from scripts.seed_product_images import PRODUCT_IMAGE_MAP

BACKEND_STATIC = Path(__file__).resolve().parents[1] / "app" / "static" / "products"
FRONTEND_STATIC = (
    Path(__file__).resolve().parents[3]
    / "desidhar-api-integration"
    / "public"
    / "static"
    / "products"
)


def test_all_mapped_webp_variants_exist_in_backend_and_frontend() -> None:
    assert len(PRODUCT_IMAGE_MAP) == 12
    assert "Butter" in PRODUCT_IMAGE_MAP
    assert "Amul Butter" not in PRODUCT_IMAGE_MAP

    for name, entries in PRODUCT_IMAGE_MAP.items():
        assert len(entries) >= 2, f"{name} should have at least 2 studio images"
        for idx, entry in enumerate(entries):
            assert entry["sort_order"] == idx
            url = entry["url"]
            assert "amul" not in url.lower()
            assert url.startswith("/static/products/") and url.endswith(".webp")
            rel = url.removeprefix("/static/products/")
            if name == "Pure Desi Ghee":
                assert url.endswith(f"pure-desi-ghee-{idx + 1:02d}.webp")
                variants = [rel, *(rel.replace(".webp", f"-{size}.webp") for size in (320, 640, 1200))]
                for variant_rel in variants:
                    be_file = BACKEND_STATIC / variant_rel
                    fe_file = FRONTEND_STATIC / variant_rel
                    assert be_file.is_file() and be_file.stat().st_size > 1000, f"Missing backend asset: {be_file}"
                    assert fe_file.is_file() and fe_file.read_bytes() == be_file.read_bytes(), f"Frontend static mismatch: {fe_file}"
                continue
            base_tag = "-1600.webp" if url.endswith("-1600.webp") else "-1200.webp"
            expected_sizes = ("320", "640", "1600", "2048") if base_tag == "-1600.webp" else ("320", "640", "1200", "2048")
            for size in expected_sizes:
                variant_rel = rel.replace(base_tag, f"-{size}.webp")
                be_file = BACKEND_STATIC / variant_rel
                fe_file = FRONTEND_STATIC / variant_rel
                assert be_file.is_file() and be_file.stat().st_size > 1000, f"Missing backend asset: {be_file}"
                assert fe_file.is_file() and fe_file.stat().st_size == be_file.stat().st_size, (
                    f"Frontend static mismatch: {fe_file}"
                )


def test_pure_desi_ghee_gallery_and_static_responses() -> None:
    entries = PRODUCT_IMAGE_MAP["Pure Desi Ghee"]
    assert len(entries) == 10
    with TestClient(app) as client:
        response = client.get("/products/pure-desi-ghee")
        assert response.status_code == 200
        data = response.json()
        assert data["slug"] == "pure-desi-ghee"
        assert [image["url"] for image in data["images"]] == [image["url"] for image in entries]
        assert [image["sort_order"] for image in data["images"]] == list(range(10))
        assert [image["alt"] for image in data["images"]] == [image["alt"] for image in entries]
        assert data["images"][7]["alt"].startswith("Serving suggestion:")
        for image in data["images"]:
            asset = client.get(image["url"])
            assert asset.status_code == 200
            assert "image/webp" in asset.headers["content-type"]
            assert 150 * 1024 <= len(asset.content) <= 300 * 1024
            assert "max-age=2592000" in asset.headers["cache-control"]


def test_white_butter_makhan_gallery_quality_and_dimensions() -> None:
    makhan_entries = PRODUCT_IMAGE_MAP["White Butter (Makhan)"]
    assert len(makhan_entries) == 7
    with TestClient(app) as client:
        resp = client.get("/products/white-butter-makhan")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "White Butter (Makhan)"
        assert data["slug"] == "white-butter-makhan"
        assert len(data["images"]) == 7
        assert data["images"][0]["url"].endswith("-01-ceramic-cream-studio-1600.webp")
        for img in data["images"]:
            r = client.get(img["url"])
            assert r.status_code == 200
            assert "webp" in r.headers.get("content-type", "").lower()
            assert len(r.content) <= 305 * 1024, f"{img['url']} exceeds 300KB target: {len(r.content)}"


def test_no_amul_branded_files_remain_on_disk() -> None:
    for root_dir in (BACKEND_STATIC, FRONTEND_STATIC):
        for path in root_dir.rglob("*"):
            assert "amul" not in path.name.lower(), f"Amul asset still exists: {path}"


def test_originals_backup_preserved() -> None:
    backup_dir = BACKEND_STATIC / "_originals_backup"
    assert backup_dir.is_dir()
    assert len(os.listdir(backup_dir)) >= 20


def test_static_product_webp_cache_headers() -> None:
    with TestClient(app) as client:
        for path in (
            "/static/products/gulab-jamun/gulab-jamun-01-primary-white-1200.webp",
            "/static/products/butter/butter-01-primary-white-1200.webp",
        ):
            resp = client.get(path)
            assert resp.status_code == 200
            assert "webp" in resp.headers.get("content-type", "").lower()
            cache_control = resp.headers.get("cache-control", "")
            assert "public" in cache_control and "max-age=2592000" in cache_control


def test_butter_endpoint_and_legacy_amul_redirect() -> None:
    with TestClient(app) as client:
        redirect_resp = client.get("/products/amul-butter", follow_redirects=False)
        assert redirect_resp.status_code in (301, 307, 308)
        assert redirect_resp.headers.get("location") == "butter"

        direct_resp = client.get("/products/butter")
        assert direct_resp.status_code == 200
        payload = direct_resp.json()
        assert payload["name"] == "Butter"
        assert payload["slug"] == "butter"
        assert len(payload["images"]) == 5
        assert all("/static/products/butter/" in img["url"] for img in payload["images"])
        assert "amul" not in (payload.get("description") or "").lower()

        search_butter = client.get("/products", params={"q": "butter"})
        assert search_butter.status_code == 200
        names = [item["name"] for item in search_butter.json()["items"]]
        assert "Butter" in names
        assert not any("amul" in n.lower() for n in names)

        search_amul = client.get("/products", params={"q": "amul"})
        assert search_amul.status_code == 200
        assert search_amul.json()["items"] == []
