import base64
import json
import pytest
from tools.ghost_client import (
    GhostAdminClient,
    inject_blueprint_html,
    make_ghost_jwt,
    render_blueprint_html,
)


def test_ghost_client_sets_forwarded_proto_and_jwt(monkeypatch):
    key_id = "68d253434949d60001d061a0"
    secret_hex = "ab" * 32
    token = make_ghost_jwt(f"{key_id}:{secret_hex}", now=1700000000)
    header_b64, payload_b64, _ = token.split(".")
    header = json.loads(base64.urlsafe_b64decode(header_b64 + "=="))
    payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=="))
    assert header == {"alg": "HS256", "typ": "JWT", "kid": key_id}
    assert payload == {"iat": 1700000000, "exp": 1700000300, "aud": "/admin/"}

    captured = {}

    def fake_urlopen(req, timeout=15):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())

        class Resp:
            def read(self):
                return b"{\"posts\": [{\"id\": \"p1\", \"slug\": \"test\", \"updated_at\": \"2026-11-14T00:00:00.000Z\"}]}"

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        return Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = GhostAdminClient(f"{key_id}:{secret_hex}")
    post = client.get_post_by_slug("test")
    assert post["id"] == "p1"
    assert captured["headers"].get("X-forwarded-proto") == "https"
    assert captured["headers"].get("Authorization", "").startswith("Ghost ")


def test_inject_blueprint_html_is_idempotent():
    bp1 = render_blueprint_html(
        metrics={"code_loc": 2120, "test_count": 136, "specs_count": 3, "plans_count": 2, "models_used": ["Gemini 4 Argon"]},
        case_study_url="https://github.com/mMarzeta/ai-sdlc-case-studies/tree/main/case-studies/2026-11-24-torrent-drop",
        summary_points=["Spec-first design eliminated network race conditions."],
    )
    original = "<p>Intro paragraph.</p><p>Conclusion.</p>"
    once = inject_blueprint_html(original, bp1)
    assert "id=\"ai-sdlc-blueprint\"" in once
    assert once.count("id=\"ai-sdlc-blueprint\"") == 1

    bp2 = render_blueprint_html(
        metrics={"code_loc": 2500, "test_count": 140, "specs_count": 3, "plans_count": 2, "models_used": ["Gemini 4 Argon"]},
        case_study_url="https://github.com/mMarzeta/ai-sdlc-case-studies/tree/main/case-studies/2026-11-24-torrent-drop",
        summary_points=["Updated metric point."],
    )
    twice = inject_blueprint_html(once, bp2)
    assert twice.count("id=\"ai-sdlc-blueprint\"") == 1
    assert "2,500" in twice or "2500" in twice
    assert "Updated metric point." in twice


def test_inject_blueprint_html_handles_regex_backslash_escapes():
    bp1 = render_blueprint_html(
        metrics={"code_loc": 100, "test_count": 10, "specs_count": 1, "plans_count": 1},
        case_study_url="https://github.com/mMarzeta/ai-sdlc-case-studies",
        summary_points=[r"Initial point"],
    )
    first = inject_blueprint_html("<p>Body</p>", bp1)
    bp_with_regex = render_blueprint_html(
        metrics={"code_loc": 100, "test_count": 10, "specs_count": 1, "plans_count": 1},
        case_study_url="https://github.com/mMarzeta/ai-sdlc-case-studies",
        summary_points=[r"Matched \1 and \d+ and \g<0> in regex scrubber"],
    )
    replaced = inject_blueprint_html(first, bp_with_regex)
    assert r"\1" in replaced
    assert r"\d+" in replaced


def test_render_blueprint_html_includes_amplifier_of_intent_and_goedecke_link():
    bp = render_blueprint_html(
        metrics={"code_loc": 1326, "test_count": 21, "specs_count": 2, "plans_count": 2},
        case_study_url="https://github.com/mMarzeta/ai-sdlc-case-studies/tree/main/case-studies/2026-12-01-ai-sdlc-blog-engine",
    )
    assert "amplifier of intent, not a source of ideas" in bp.lower()
    assert "https://www.seangoedecke.com/writing-is-no-longer-proof-of-work/" in bp
    assert "https://blog.marzeta.pl/writing-is-no-longer-proof-of-work-amplifier-of-intent/" in bp


def test_create_post_html_sends_source_html_and_scheduled_published_at(monkeypatch):
    key_id = "68d253434949d60001d061a0"
    secret_hex = "ab" * 32
    captured = {}

    def fake_urlopen(req, timeout=20):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["body"] = json.loads(req.data.decode("utf-8"))

        class Resp:
            def read(self):
                return b'{"posts": [{"id": "new_post_123", "slug": "test-slug", "status": "scheduled"}]}'

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        return Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = GhostAdminClient(f"{key_id}:{secret_hex}")
    created = client.create_post_html(
        title="Test Title",
        slug="test-slug",
        html="<p>Hello</p>",
        status="scheduled",
        tags=[{"name": "AI-SDLC"}],
        custom_excerpt="Short excerpt",
        featured=True,
        published_at="2026-12-01T08:00:00.000Z",
    )
    assert created["id"] == "new_post_123"
    assert "source=html" in captured["url"]
    assert captured["method"] == "POST"
    post_payload = captured["body"]["posts"][0]
    assert post_payload["title"] == "Test Title"
    assert post_payload["slug"] == "test-slug"
    assert post_payload["status"] == "scheduled"
    assert post_payload["published_at"] == "2026-12-01T08:00:00.000Z"
    assert post_payload["featured"] is True
    assert post_payload["custom_excerpt"] == "Short excerpt"
