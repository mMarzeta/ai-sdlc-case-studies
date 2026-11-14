from pathlib import Path
import pytest
from tools.github_showcase import (
    ScrubberSecurityError,
    export_case_study,
    loaded_default_rules,
    scrub_content,
    update_portfolio_readme,
)


def test_scrubber_normalizes_paths_ips_and_blocks_secrets():
    rules = loaded_default_rules()
    raw = (
        "Host at 192.0.2.10 in ~/projects/torrent-drop.\n"
        "See [Spec](./specs-and-plans/2026-11-13-vpn-torrent-drop-design.md)."
    )
    cleaned = scrub_content(raw, rules)
    assert "192.0.2.10" not in cleaned
    assert "192.0.2.10" in cleaned
    assert "~/projects" not in cleaned
    assert "file://~" not in cleaned

    with pytest.raises(ScrubberSecurityError):
        scrub_content("GHOST_DB_PASSWORD" + "=super_secret_prod_pass_12345", rules)

    with pytest.raises(ScrubberSecurityError):
        scrub_content("token = 'ghp_" + "1234567890abcdefghijklmnopqrstuvwx'", rules)


def test_export_case_study_copies_sources_and_updates_readme(tmp_path):
    post_dir = tmp_path / "posts" / "2026-11-24-torrent-drop"
    sources_dir = post_dir / "sources"
    sources_dir.mkdir(parents=True)
    (sources_dir / "spec.md").write_text("# Spec on 192.0.2.10\n")
    app_dir = tmp_path / "app"
    (app_dir / "__pycache__").mkdir(parents=True)
    (app_dir / "__pycache__" / "mod.cpython-313.pyc").write_bytes(b"123")
    (app_dir / "main.py").write_text("HOST = '192.0.2.10'\n")
    (post_dir / "campaign.yaml").write_text(
        "slug: vpn-torrent-drop\n"
        "title: Torrent Drop AI SDLC\n"
        "status: published\n"
        "sdlc_metrics:\n  code_loc: 2120\n  test_count: 136\n  specs_count: 3\n  plans_count: 2\n"
        "github_showcase:\n  enabled: true\n  case_study_dir: case-studies/2026-11-24-torrent-drop\n"
        "  summary: VPN media pipeline\n  include_paths:\n    - ../../app\n"
    )
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    result = export_case_study(post_dir, repo_dir, loaded_default_rules(), git_push=False)
    exported_spec = repo_dir / "case-studies/2026-11-24-torrent-drop/specs-and-plans/spec.md"
    exported_main = repo_dir / "case-studies/2026-11-24-torrent-drop/src/app/main.py"
    assert exported_spec.exists()
    assert exported_main.exists()
    assert "192.0.2.10" in exported_main.read_text()
    assert not (repo_dir / "case-studies/2026-11-24-torrent-drop/src/app/__pycache__").exists()
    assert "192.0.2.10" in exported_spec.read_text()
    readme = update_portfolio_readme(repo_dir, [result])
    assert "Torrent Drop AI SDLC" in readme.read_text()
    assert "136" in readme.read_text()


def test_scrubber_scrubs_dockerfile_and_handles_draft_status(tmp_path):
    post_dir = tmp_path / "posts" / "2026-11-24-draft"
    sources_dir = post_dir / "sources"
    sources_dir.mkdir(parents=True)
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("ENV HOST_IP=192.0.2.10\n")
    (post_dir / "campaign.yaml").write_text(
        "slug: unwritten-slug\n"
        "title: Unwritten Draft Case Study\n"
        "status: draft\n"
        "sdlc_metrics:\n  code_loc: 500\n  test_count: 20\n  specs_count: 1\n  plans_count: 1\n"
        "github_showcase:\n  enabled: true\n  case_study_dir: case-studies/2026-11-24-draft\n"
        "  summary: Draft summary\n  include_paths:\n    - ../../Dockerfile\n"
    )
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    result = export_case_study(post_dir, repo_dir, loaded_default_rules(), git_push=False)
    exported_df = repo_dir / "case-studies/2026-11-24-draft/src/Dockerfile"
    assert exported_df.exists()
    assert "192.0.2.10" not in exported_df.read_text()
    assert "192.0.2.10" in exported_df.read_text()

    readme_text = update_portfolio_readme(repo_dir, [result]).read_text()
    assert "https://blog.marzeta.pl/unwritten-slug/" not in readme_text
    assert "Unwritten Draft Case Study" in readme_text


def test_portfolio_readme_includes_amplifier_of_intent_manifesto(tmp_path):
    readme_path = update_portfolio_readme(tmp_path, [], git_push=False)
    text = readme_path.read_text(encoding="utf-8")
    assert "Amplifier of Intent" in text
    assert "https://www.seangoedecke.com/writing-is-no-longer-proof-of-work/" in text
    assert "https://blog.marzeta.pl/writing-is-no-longer-proof-of-work-amplifier-of-intent/" in text


def test_self_export_of_blog_engine_passes_scrubber():
    rules = loaded_default_rules()
    blog_root = Path(__file__).resolve().parent.parent
    for sub in ("tools", "tests", "config", "posts"):
        for path in (blog_root / sub).rglob("*"):
            real_p = path.resolve()
            if real_p.is_file() and real_p.suffix in {".py", ".yaml", ".md"}:
                cleaned = scrub_content(real_p.read_text(encoding="utf-8", errors="replace"), rules)
                assert isinstance(cleaned, str)
