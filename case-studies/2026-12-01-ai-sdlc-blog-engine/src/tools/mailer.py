from __future__ import annotations

from datetime import datetime, timezone
from email.message import EmailMessage
import html as html_lib
import json
from pathlib import Path
import smtplib
from typing import Any, Callable


def _load_state(post_dir: Path) -> dict[str, Any]:
    state_path = post_dir / "state.json"
    if state_path.exists():
        return json.loads(state_path.read_text(encoding="utf-8"))
    return {"promoted": False, "pitches_sent": {}, "github_synced": False}


def _save_state(post_dir: Path, state: dict[str, Any]) -> None:
    state_path = post_dir / "state.json"
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _default_smtp_send(msg: EmailMessage, smtp_config: dict[str, Any]) -> None:
    host = smtp_config.get("host", "smtp.eu.mailgun.org")
    port = int(smtp_config.get("port", 587))
    user = smtp_config.get("user", "")
    password = smtp_config.get("password", "")

    with smtplib.SMTP(host, port, timeout=20) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        if user and password:
            server.login(user, password)
        server.send_message(msg)


def send_campaign_pitches(
    post_dir: Path,
    campaign: dict[str, Any],
    newsletters: dict[str, dict[str, Any]],
    smtp_config: dict[str, Any],
    dry_run: bool = False,
    send_fn: Callable[[EmailMessage, dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    sender = send_fn or _default_smtp_send
    state = _load_state(post_dir)
    pitches_sent: dict[str, Any] = state.setdefault("pitches_sent", {})

    from_email = smtp_config.get("from_email", "blog@newsletter.marzeta.pl")
    from_header = f"Maciej Marzęta <{from_email}>" if "<" not in from_email else from_email
    reply_to = smtp_config.get("reply_to", "contact@marzeta.pl")

    results: list[dict[str, Any]] = []
    for pitch in campaign.get("pitches", []):
        if not pitch.get("enabled", True):
            continue
        nl_id = pitch["newsletter_id"]
        nl_info = newsletters.get(nl_id)
        if not nl_info or not nl_info.get("active", True):
            continue

        to_email = nl_info["to_email"]
        subject = pitch["subject"].strip()
        body = pitch["body"].strip()

        if nl_id in pitches_sent:
            prev = pitches_sent[nl_id]
            results.append(
                {
                    "newsletter_id": nl_id,
                    "newsletter_name": nl_info.get("name", nl_id),
                    "to_email": to_email,
                    "subject": subject,
                    "body": body,
                    "status": "already_sent",
                    "sent_at": prev.get("sent_at", ""),
                }
            )
            continue

        msg = EmailMessage()
        msg["From"] = from_header
        msg["To"] = to_email
        msg["Reply-To"] = reply_to
        msg["Subject"] = subject
        msg.set_content(body)

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if dry_run:
            results.append(
                {
                    "newsletter_id": nl_id,
                    "newsletter_name": nl_info.get("name", nl_id),
                    "to_email": to_email,
                    "subject": subject,
                    "body": body,
                    "status": "dry-run",
                    "sent_at": now_iso,
                }
            )
            continue

        sender(msg, smtp_config)
        pitches_sent[nl_id] = {
            "to_email": to_email,
            "subject": subject,
            "sent_at": now_iso,
        }
        _save_state(post_dir, state)
        results.append(
            {
                "newsletter_id": nl_id,
                "newsletter_name": nl_info.get("name", nl_id),
                "to_email": to_email,
                "subject": subject,
                "body": body,
                "status": "sent",
                "sent_at": now_iso,
            }
        )

    return results


def render_execution_summary_email(
    campaign: dict[str, Any],
    actions: dict[str, Any],
    pitch_results: list[dict[str, Any]],
    launch_kit: dict[str, Any],
) -> tuple[str, str, str]:
    title = campaign.get("title", campaign.get("slug", "Blog Post"))
    post_url = actions.get("post_url", "")
    github_url = actions.get("github_url", "")
    subject = f"[Blog Launch Report] {title} — Podsumowanie automatyzacji i wysłanych maili"

    # Plaintext version
    txt_lines = [
        f"PODSUMOWANIE PUBLIKACJI I PROMOCJI: {title}",
        "=" * 72,
        f"1. Opublikowany post (Ghost): {post_url}",
        f"2. GitHub Case Study (Specki, Plany, Kod): {github_url}",
        f"3. Wysłane maile do newsletterów: {len(pitch_results)}",
        "",
        "SZCZEGÓŁOWY LOG WYSŁANYCH MAILI (DO KOGO I DOKŁADNA TREŚĆ):",
        "-" * 72,
    ]
    for idx, pr in enumerate(pitch_results, 1):
        txt_lines.extend(
            [
                f"[{idx}] Newsletter: {pr['newsletter_name']} ({pr['newsletter_id']})",
                f"    Do (To):      {pr['to_email']}",
                f"    Status:       {pr['status']} ({pr.get('sent_at', '')})",
                f"    Temat:        {pr['subject']}",
                "    Treść maila:",
                "    " + "\n    ".join(pr["body"].splitlines()),
                "-" * 72,
            ]
        )

    txt_lines.extend(
        [
            "",
            "PAKIET 1-CLICK DO RĘCZNEGO WRZUCENIA (HACKER NEWS / LOBSTE.RS / REDDIT):",
            f"- Hacker News (1-Click Submit): {launch_kit.get('hacker_news_submit_url', '')}",
            f"- Lobste.rs (1-Click Submit):   {launch_kit.get('lobsters_submit_url', '')}",
        ]
    )
    for rp in launch_kit.get("reddit_posts", []):
        txt_lines.extend(
            [
                f"\n- Reddit ({rp['subreddit']}): {rp.get('submit_url', '')}",
                f"  Tytuł: {rp['title']}",
                "  Treść:\n" + rp["body_markdown"],
            ]
        )
    text_body = "\n".join(txt_lines)

    # Rich HTML version
    rows_html = []
    cards_html = []
    for idx, pr in enumerate(pitch_results, 1):
        rows_html.append(
            "<tr>"
            f'<td style="padding:8px;border-bottom:1px solid #e5e7eb;"><strong>{html_lib.escape(pr["newsletter_name"])}</strong></td>'
            f'<td style="padding:8px;border-bottom:1px solid #e5e7eb;"><code>{html_lib.escape(pr["to_email"])}</code></td>'
            f'<td style="padding:8px;border-bottom:1px solid #e5e7eb;">{html_lib.escape(pr["status"])}</td>'
            f'<td style="padding:8px;border-bottom:1px solid #e5e7eb;">{html_lib.escape(pr.get("sent_at", ""))}</td>'
            "</tr>"
        )
        cards_html.append(
            '<div style="background:#f9fafb;border:1px solid #d1d5db;border-radius:8px;padding:14px;margin-bottom:16px;">'
            f'<div style="font-size:14px;color:#111827;margin-bottom:6px;"><strong>#{idx} {html_lib.escape(pr["newsletter_name"])}</strong> &mdash; <code>{html_lib.escape(pr["to_email"])}</code> ({html_lib.escape(pr["status"])})</div>'
            f'<div style="font-size:13px;color:#374151;margin-bottom:8px;"><strong>Subject:</strong> {html_lib.escape(pr["subject"])}</div>'
            f'<pre style="background:#ffffff;border:1px solid #e5e7eb;border-radius:6px;padding:12px;white-space:pre-wrap;font-family:monospace;font-size:12px;color:#1f2937;margin:0;">{html_lib.escape(pr["body"])}</pre>'
            "</div>"
        )

    reddit_html = []
    for rp in launch_kit.get("reddit_posts", []):
        reddit_html.append(
            '<div style="background:#f9fafb;border:1px solid #d1d5db;border-radius:8px;padding:14px;margin-bottom:14px;">'
            f'<div style="margin-bottom:6px;"><strong>{html_lib.escape(rp["subreddit"])}</strong> &mdash; <a href="{html_lib.escape(rp.get("submit_url", ""), quote=True)}">Otwórz formularz Reddit z wypełnioną treścią &rarr;</a></div>'
            f'<div style="font-size:13px;margin-bottom:6px;"><strong>Tytuł:</strong> {html_lib.escape(rp["title"])}</div>'
            f'<pre style="background:#ffffff;border:1px solid #e5e7eb;border-radius:6px;padding:10px;white-space:pre-wrap;font-family:monospace;font-size:12px;margin:0;">{html_lib.escape(rp["body_markdown"])}</pre>'
            "</div>"
        )

    html_body = (
        '<div style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;max-width:760px;margin:0 auto;color:#111827;line-height:1.5;">'
        f'<h2 style="margin-bottom:4px;">Raport wykonania automatyzacji bloga</h2>'
        f'<p style="margin-top:0;color:#4b5563;">Post: <strong>{html_lib.escape(title)}</strong></p>'
        '<div style="background:#eef2ff;border:1px solid #c7d2fe;border-radius:8px;padding:14px;margin-bottom:20px;">'
        "<h3 style=\"margin-top:0;margin-bottom:8px;font-size:15px;\">1. Co zostało zrobione automatycznie</h3>"
        "<ul style=\"margin:0;padding-left:20px;\">"
        f'<li><strong>Ghost Post Live:</strong> <a href="{html_lib.escape(post_url, quote=True)}">{html_lib.escape(post_url)}</a></li>'
        f'<li><strong>GitHub AI-SDLC Case Study (Specki + Plany + Kod):</strong> <a href="{html_lib.escape(github_url, quote=True)}">{html_lib.escape(github_url)}</a></li>'
        f"<li><strong>Wysłane maile do redakcji newsletterów:</strong> {len(pitch_results)}</li>"
        "</ul>"
        "</div>"
        "<h3>2. Odbiorcy newsletterów</h3>"
        '<table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:20px;">'
        '<thead><tr style="background:#f3f4f6;text-align:left;">'
        '<th style="padding:8px;">Newsletter</th><th style="padding:8px;">Adres e-mail</th><th style="padding:8px;">Status</th><th style="padding:8px;">Czas (UTC)</th>'
        "</tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody></table>"
        "<h3>3. Dokładna treść wysłanych maili (Verbatim Log)</h3>"
        f"{''.join(cards_html)}"
        "<h3>4. Linki 1-Click do ręcznej wrzutki (Hacker News / Lobste.rs / Reddit)</h3>"
        "<p>"
        f'<a href="{html_lib.escape(launch_kit.get("hacker_news_submit_url", ""), quote=True)}" style="display:inline-block;background:#ff6600;color:#ffffff;text-decoration:none;padding:10px 16px;border-radius:6px;font-weight:600;margin-right:10px;">Wrzuć na Hacker News (1-Click) &rarr;</a>'
        f'<a href="{html_lib.escape(launch_kit.get("lobsters_submit_url", ""), quote=True)}" style="display:inline-block;background:#ac130d;color:#ffffff;text-decoration:none;padding:10px 16px;border-radius:6px;font-weight:600;">Wrzuć na Lobste.rs (1-Click) &rarr;</a>'
        "</p>"
        f"{''.join(reddit_html)}"
        "</div>"
    )
    return subject, text_body, html_body


def send_execution_summary_email(
    smtp_config: dict[str, Any],
    subject: str,
    text_body: str,
    html_body: str,
    dry_run: bool = False,
    send_fn: Callable[[EmailMessage, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    sender = send_fn or _default_smtp_send
    from_email = smtp_config.get("from_email", "blog@newsletter.marzeta.pl")
    notify_to = smtp_config.get("notify_to", "contact@marzeta.pl")

    msg = EmailMessage()
    msg["From"] = f"MarzTech Blog Automation <{from_email}>" if "<" not in from_email else from_email
    msg["To"] = notify_to
    msg["Subject"] = subject
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    if dry_run:
        return {"status": "dry-run", "to": notify_to, "subject": subject}

    sender(msg, smtp_config)
    return {"status": "sent", "to": notify_to, "subject": subject}
