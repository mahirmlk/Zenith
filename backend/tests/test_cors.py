"""Exact backend CORS origin configuration tests."""

import pytest

from main import _configured_cors_origins


def test_cors_defaults_to_one_canonical_app_url():
    assert _configured_cors_origins("https://app.example.com", "") == [
        "https://app.example.com"
    ]


def test_cors_accepts_multiple_exact_origins_and_deduplicates():
    assert _configured_cors_origins(
        "https://app.example.com",
        "https://app.example.com/, https://admin.example.com",
    ) == ["https://app.example.com", "https://admin.example.com"]


@pytest.mark.parametrize(
    "value",
    [
        "*",
        "https://app.example.com/path",
        "https://user:password@app.example.com",
        "javascript:alert(1)",
        "https://app.example.com?debug=true",
        "https://app.example.com:invalid",
    ],
)
def test_cors_rejects_non_origin_values(value: str):
    with pytest.raises(ValueError, match="exact http\(s\) origins"):
        _configured_cors_origins("https://app.example.com", value)


def test_cors_rejects_legacy_comma_separated_app_url():
    with pytest.raises(ValueError, match="exact http\(s\) origins"):
        _configured_cors_origins(
            "https://app.example.com,https://admin.example.com", ""
        )
