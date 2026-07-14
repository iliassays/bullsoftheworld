from __future__ import annotations

import datetime as dt
import socket
from io import BytesIO

from PIL import Image
from sqlalchemy.dialects import postgresql

from ingestion import logos


def test_logo_target_codes_are_normalized_and_deduplicated() -> None:
    assert logos._normalize_codes([" nxtc ", "AGEN", "NXTC", ""]) == ["AGEN", "NXTC"]
    assert logos._normalize_codes(None) is None


def test_failed_logo_recheck_preserves_an_existing_valid_asset() -> None:
    stmt = logos._logo_upsert(
        {
            "market": "US",
            "code": "NXTC",
            "image": None,
            "content_type": None,
            "source_url": None,
            "status": "no_site",
        },
        dt.datetime(2026, 7, 14, tzinfo=dt.UTC),
    )
    sql = str(
        stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert "CASE WHEN (excluded.status = 'ok') THEN excluded.image ELSE company_logos.image END" in sql
    assert "WHEN (company_logos.status = 'ok') THEN company_logos.status" in sql


async def test_logo_url_validation_rejects_private_networks(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))],
    )
    assert not await logos._is_public_url("https://company.example/logo.png")

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ],
    )
    assert await logos._is_public_url("https://company.example/logo.png")
    assert not await logos._is_public_url("file:///etc/passwd")
    assert not await logos._is_public_url("https://user:secret@company.example/logo.png")


async def test_logo_download_decodes_and_normalizes_raster(monkeypatch) -> None:
    raw = BytesIO()
    Image.new("RGB", (32, 32), "red").save(raw, format="JPEG")

    async def fake_get(*_args, **_kwargs):
        return 200, {"content-type": "image/jpeg"}, raw.getvalue(), "https://example.com/a.jpg"

    monkeypatch.setattr(logos, "_safe_get", fake_get)
    result = await logos._download_image(None, "https://example.com/a.jpg")  # type: ignore[arg-type]

    assert result is not None
    assert result["content_type"] == "image/png"
    assert result["image"].startswith(b"\x89PNG")


async def test_logo_download_rejects_svg_even_with_image_content_type(monkeypatch) -> None:
    async def fake_get(*_args, **_kwargs):
        return 200, {"content-type": "image/svg+xml"}, b"<svg></svg>", "https://example.com/a.svg"

    monkeypatch.setattr(logos, "_safe_get", fake_get)
    assert await logos._download_image(None, "https://example.com/a.svg") is None  # type: ignore[arg-type]
