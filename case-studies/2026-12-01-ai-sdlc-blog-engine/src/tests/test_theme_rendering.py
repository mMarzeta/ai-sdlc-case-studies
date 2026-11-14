import urllib.request


def test_live_homepage_renders_minimal_hashimoto_ronacher_theme():
    req = urllib.request.Request("http://127.0.0.1:2368/")
    req.add_header("X-Forwarded-Proto", "https")
    with urllib.request.urlopen(req, timeout=10) as resp:
        html = resp.read().decode("utf-8")

    assert "minimal.css" in html
    assert 'class="minimal-intro"' in html
    assert 'class="minimal-post-row"' in html
    assert 'class="minimal-post-date"' in html
    assert 'class="minimal-post-title"' in html
    assert "https://github.com/mMarzeta/ai-sdlc-case-studies" in html
