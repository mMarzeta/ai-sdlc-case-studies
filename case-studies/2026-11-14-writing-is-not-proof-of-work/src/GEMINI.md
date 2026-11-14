# Blog & AI-SDLC Promotion Workspace (`blog.marzeta.pl`)

Dedicated workspace for authoring technical case studies on `blog.marzeta.pl`, syncing verifiable AI-SDLC artifacts (specs, plans, tests, and code) to `github.com/mMarzeta/ai-sdlc-case-studies`, and running automated newsletter outreach.

Always read **[PLAYBOOK.md](./PLAYBOOK.md)** before drafting or editing any blog post.

---

## Directory Structure

```text
~/projects/blog/
├── GEMINI.md                  # Technical reference & CLI workflows (this file)
├── PLAYBOOK.md                # Mandatory CTO / Head of AI editorial & AI-SDLC framing rules
├── .env                       # GHOST_ADMIN_API_KEY, Mailgun SMTP credentials (gitignored)
├── .github-showcase-repo/     # Isolated clone of git@github.com:mMarzeta/ai-sdlc-case-studies.git
├── config/
│   ├── newsletters.yaml       # Editorial contacts (Python Weekly, PyCoder's, TLDR, Pointer, Changelog)
│   └── scrubber_rules.yaml    # Path/IP normalization & secret-blocking regexes for GitHub export
├── tools/
│   ├── blogctl.py             # Main CLI & Tuesday 08:05 UTC cron entry point
│   ├── ghost_client.py        # Ghost 6 Admin API client (HS256 JWT + Blueprint HTML injector)
│   ├── github_showcase.py     # Scrubber & portfolio exporter to GitHub
│   ├── mailer.py              # Mailgun SMTP pitcher & verbatim execution summary emailer
│   └── syndicator.py          # 1-click HN/Lobste.rs/Reddit kit builder & optional Dev.to cross-poster
├── tests/                     # Pytest test suite for all automation tools
└── posts/                     # Self-contained post packages (drafts, scheduled, and published)
    └── <YYYY-MM-DD-slug>/
        ├── post.md            # Article markdown
        ├── campaign.yaml      # SDLC metrics, GitHub include_paths, newsletter pitches, HN/Reddit copy
        ├── state.json         # Idempotent promotion & email-send tracking
        ├── sources/           # Design specs, implementation plans, AGY chat summaries
        └── assets/            # Diagrams and screenshots
```

---

## Standard Workflow for Creating a New Post

1. **Create Post Folder & Ingest Materials (`specs`, `plans`, `AGY brain summaries`):**
   ```bash
   mkdir -p ~/projects/blog/posts/2026-11-24-torrent-drop
   python3 ~/projects/blog/tools/blogctl.py ingest posts/2026-11-24-torrent-drop \
     ~/.gemini/antigravity-cli/brain/<conv-id>/architecture_decisions_summary.md \
     ~/Projects/docs/superpowers/specs/2026-11-13-vpn-torrent-drop-design.md \
     ~/Projects/docs/superpowers/plans/2026-11-13-vpn-torrent-drop.md
   ```
   *(Files inside `~/Projects/` are symlinked; external files from `~/.gemini/` are copied into `sources/`).*

2. **Draft `post.md` and `campaign.yaml` Following `PLAYBOOK.md`:**
   - Write `post.md` and `campaign.yaml` inside `posts/<YYYY-MM-DD-slug>/`.
   - Set `approved: true` in `campaign.yaml` once the user approves the draft and pitches.

3. **Sync Post & AI-SDLC Blueprint to Ghost:**
   ```bash
   python3 ~/projects/blog/tools/blogctl.py ghost-sync posts/2026-11-24-torrent-drop
   ```

4. **Automated Tuesday Promotion (`08:05 UTC` Cron):**
   - Every Tuesday at `08:05 UTC` (5 minutes after Ghost's `08:00 UTC` scheduled publish slot), cron runs:
     ```bash
     /usr/bin/python3 ~/projects/blog/tools/blogctl.py cron-run
     ```
   - For any post with `approved: true` and `state.promoted != true` whose Ghost status is now `published`, `blogctl` automatically:
     1. Scrubs and pushes `sources/` + `include_paths` to `https://github.com/mMarzeta/ai-sdlc-case-studies`.
     2. Sends all enabled pitch emails in `campaign.yaml` to newsletter editors via Mailgun SMTP (`Reply-To: contact@marzeta.pl`).
     3. Sends a full **Execution Summary Email** to `contact@marzeta.pl` containing what was done, who received emails, the **exact verbatim text of every email sent**, and 1-click submission links for Hacker News, Lobste.rs, and Reddit.
   - To preview a promotion without sending external emails:
     ```bash
     python3 ~/projects/blog/tools/blogctl.py promote posts/<folder> --dry-run
     ```
