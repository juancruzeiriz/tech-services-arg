"""Fixtures compartidas del pipeline de prospección."""

from __future__ import annotations

import pytest

from gtm.factory.types import Demo, PainScore, Prospect, SenderIdentity


@pytest.fixture
def prospect() -> Prospect:
    return Prospect(
        place_id="ChIJtest123",
        name="Ramirez Plumbing & Drain",
        vertical="plumber",
        metro="Tucson, AZ",
        phone="(520) 555-0142",
        website="http://ramirezplumbing.example",
        rating=4.8,
        review_count=214,
        address="1420 E Speedway Blvd, Tucson, AZ 85719",
        top_reviews=("Showed up in 40 minutes on a Sunday and fixed the leak.",),
    )


@pytest.fixture
def sender() -> SenderIdentity:
    return SenderIdentity(
        from_name="Juan Cruz Eiriz",
        from_email="juan@example.com",
        physical_address="Av. Siempre Viva 742, Cordoba, Argentina",
        unsubscribe_url="https://example.com/unsubscribe",
    )


@pytest.fixture
def live_demo() -> Demo:
    return Demo(
        place_id="ChIJtest123",
        slug="ramirez-plumbing-drain-abc123",
        html_path="/tmp/demo/index.html",
        url="https://demos.example.com/ramirez-plumbing-drain-abc123/",
    )


@pytest.fixture
def slow_site_score() -> PainScore:
    return PainScore(place_id="ChIJtest123", performance=23, seo=61, accessibility=70)
