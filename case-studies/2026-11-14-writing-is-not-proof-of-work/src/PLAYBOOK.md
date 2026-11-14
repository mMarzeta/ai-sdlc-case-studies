# PLAYBOOK: AI-Native SDLC & Executive Positioning (`blog.marzeta.pl`)

This playbook governs how AI agents write, structure, and promote every article on **MarzTech (`blog.marzeta.pl`)**.

---

## 1. Strategic Goal & Target Audience

Every post on `blog.marzeta.pl` has a dual mission:
1. **For Senior/Principal Engineers:** Deliver an unflinchingly technical, zero-fluff engineering deep dive backed by real code, real failure modes, and reproducible numbers.
2. **For CTOs, VPs of Engineering, Founders & Executive Recruiters:** Demonstrate that **Maciej Marzęta** operates as a **CTO / Head of AI / AI-SDLC Architect** who has solved the hardest problem in modern software teams: **turning autonomous AI agents into a deterministic, spec-driven production delivery pipeline without architectural drift or technical debt.**

*(Maciej does not use LinkedIn. This blog and `github.com/mMarzeta/ai-sdlc-case-studies` are his primary executive portfolio.)*

---

## 2. Framing Rule: Lead with Architecture & AI-SDLC, Not Hardware

Even when a system runs on a Raspberry Pi 5 homelab or integrates with home hardware (Sony Bravia, Jellyfin, Gluetun, Home Assistant), **never frame the article as a hobbyist tinkering project**.

- **Weak Framing (Avoid):** *"How I built a script to download torrents and send emails on my Raspberry Pi"*
- **Executive/Architect Framing (Required):** *"Spec-Driven AI SDLC in Practice: Shipping a VPN-Isolated Media Pipeline (2,120 LOC, 136 Tests) in One Evening with Zero Architectural Drift"*

Always highlight:
- **System boundaries & failure domains** (e.g., network namespace isolation, atomic filesystem transitions, SQLite WAL concurrency, zero-noise alerting).
- **Explicit trade-off tables** (why alternative A was rejected in favor of B).
- **Production bugs caught during verification** (what broke on contact with reality and how the test suite locked it down).

---

## 3. Mandatory Article Structure

Every blog post in `posts/<YYYY-MM-DD-slug>/post.md` must include:

1. **Metadata Header:**
   - `Proposed Title`, `Proposed Slug`, `Custom Excerpt` (140–160 chars, high-signal), `Tags` (must include `AI-SDLC` and `Architecture`), `Ghost Post ID`, `Status`.
2. **The Hook (The Engineering Tension):**
   - Start with a concrete production problem, security incident, or architectural bottleneck.
3. **System Architecture & Trade-Offs:**
   - Clear diagrams/flows, component boundaries, and explicit engineering trade-offs.
4. **The War Story (Contact with Production Reality):**
   - Specific edge cases (e.g., `clone3` syscalls, Docker DNS leaks, dual-stack IPv6 `169.254.x.x`, `setupwraith` bricks) and their root-cause fixes.
5. **Mandatory Closing Section: `## The AI-SDLC Blueprint (How This Was Engineered)`:**
   - Rendered automatically via `blogctl ghost-sync` or included at the bottom of the post:
     - **Production Footprint:** LOC of production code & UI.
     - **Verification Gate:** Number of automated `pytest` tests / integration checks.
     - **Spec-First Governance:** Number of design specs (`specs/`) and implementation plans (`plans/`) written before touching code.
     - **Agent vs. Architect Division of Labor:** Bullet points explaining what the AI agents automated vs. which critical architectural rulings the human architect made.
     - **Direct Link to GitHub Proof-of-Work:** `https://github.com/mMarzeta/ai-sdlc-case-studies/tree/main/case-studies/<YYYY-MM-DD-slug>`

---

## 4. Generating `campaign.yaml` (Automated Distribution Package)

Whenever you draft a new post in `posts/<YYYY-MM-DD-slug>/`, you MUST also generate `posts/<YYYY-MM-DD-slug>/campaign.yaml` containing:

1. **`sdlc_metrics`** and **`blueprint_highlights`** (3–4 bullets on how Spec-Driven AI SDLC accelerated delivery and prevented bugs).
2. **`github_showcase`:**
   - `enabled: true`
   - `case_study_dir: "case-studies/<YYYY-MM-DD-slug>"`
   - `include_paths`: relative paths to the project's application code and test suite so `blogctl` scrubs and pushes them to `mMarzeta/ai-sdlc-case-studies` automatically.
3. **`pitches` (Automated Mailgun Emails to Newsletter Editors):**
   - Tailor 3-sentence plain-text pitches for relevant newsletters in `config/newsletters.yaml` (`python_weekly`, `pycoders_weekly`, `tldr_ai`, `pointer_io`, `changelog_news`).
   - Every pitch must include both the live `https://blog.marzeta.pl/<slug>/` link and the GitHub Case Study link.
4. **`social_kit` (1-Click Manual Launch Links Included in the Summary Email):**
   - `hacker_news.title`: Crisp, factual `Show HN:` or technical title (max 80 chars, no emojis, no clickbait).
   - `reddit`: Native self-post markdown drafts tailored for `r/ExperiencedDevs` (focused on AI-SDLC methodology & architecture governance) and `r/Python` or `r/selfhosted`.
