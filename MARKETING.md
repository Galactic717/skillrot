# skillrot — launch & marketing plan

Positioning, research, assets and copy for launching skillrot on X. Every number in the copy
comes from a real run (see `docs/runs/`); nothing here is invented.

## One-line positioning

> **skillrot** — the deterministic CLI that shows what your agent's skill library costs, and
> which skills the router has already stopped seeing.

## Research: how skills get presented on X (checked live, 2026-09-28)

Method: X search in a logged-in browser, `"claude code" skill min_faves:2000` (top), plus
targeted searches for caveman / ponytail / archify / humanizer and for
context-bloat / skill-doctor posts. Posts were opened and read, not summarized.

**Format.** Of 28 top posts about Claude Code skills (≥2,000 likes each): **15 video, 9
image, 5 text-only.** Video is the default for anything you can *show running*.

**What the winners do:**

| Pattern | Example (likes · views where visible) | Why it works |
| --- | --- | --- |
| Pain + cost in line one | greenlight CLI: "every App Store rejection costs you 2-5 days." (3.9K · 650K) | the reader sees their own problem before the product |
| Short screen video, tool + result side by side | same post: 30 s, terminal left, app right | proof in motion beats claims |
| `>` checklist of what it checks | same post: "> payment & IAP compliance > privacy manifests …" | scannable; each line is a reason to save |
| **Bookmarks > likes** | same post: 6.8K bookmarks vs 3.9K likes | tools are *saved for later*; optimize for the save |
| Link in the **first reply**, not the post | same post: repo card in the author's first reply | the main post isn't down-ranked as an outbound link |
| Before → after numbers as a list, with an honest range | caveman (via @om_patel5, 6.2K): "explain React re-render bug: 1180 → 159 tokens (87% saved)" … "range is 22–87%" | concrete, checkable, and the range makes it believable |
| Before / after image pair, almost no text | ponytail (@MilesCranmer, 2.6K · 380K, 2.9K bookmarks): "Before ponytail skill / After ponytail skill" | the picture does the arguing |
| One-line install in the post | text-to-lottie (8.8K): `$ npx skills add diffusionstudio/lottie` | zero friction to try |
| Curators carry the reach | @om_patel5, @DataChaz ("STOP BURNING YOUR TOKENS … 10 tools", 4.3K), @GithubProjects, @GitHub_Daily | many viral skill posts are *third-party* roundups; getting into "N tools that save tokens" lists is a channel |

**Timing.** Claude Code's built-in `/skill-doctor` is being discussed right now (posts
22–27 Sep 2026, low engagement so far). The topic is warm, and skillrot answers the obvious
follow-up: "what about skills I haven't installed yet, and how do I stop it in CI?"

**Anchor story (verified on GitHub).** danielmiessler/LifeOS#1205: 46 skills at ~3× the
listing budget; Claude Code silently dropped most of them at session start.

## Assets (in the repo)

| File | Use |
| --- | --- |
| `docs/assets/skillrot-explainer.mp4` | 27 s, 1920×1080, H.264 — the video for the main post |
| `docs/assets/skillrot-explainer.gif` | README / places that don't play video |
| `docs/assets/live-audit-card.png` | still of the 5-library results — second post / quote tweets |
| `docs/assets/budget-ecc.svg` | `--svg` output on a real library |
| `docs/demo/explainer.html` | the source of the video; plays in a browser, re-render with `docs/demo/render.py` |

The video's scenes: hook → how the 1% listing budget drops descriptions → a real terminal
run on affaan-m/ECC → the weekly five-library results → install line.

## The launch post (attach the MP4)

> Your Claude Code skills have a budget you can't see.
>
> 1% of the context window. Past it, Claude Code silently drops descriptions — least used
> first — and those skills stop getting picked.
>
> I audited 5 popular skill libraries. 4 are over it. One is 27× over.

**First reply (the link):**

> skillrot — one Python file, zero deps. Runs on any folder, before you install, or in CI:
> github.com/Galactic717/skillrot

**Thread, 2 — the numbers (list, like the caveman post):**

> Live audit, 2026-09-28 (skills + commands, listing vs. budget, 200k window):
>
> > obra/superpowers — 0.35× ✓
> > addyosmani/agent-skills — 1.3× (5 name-only)
> > affaan-m/ECC — 13.2× (all 375 name-only)
> > ComposioHQ/awesome-claude-skills — 14.2× (all 864)
> > alirezarezvani/claude-skills — 27.4× (483)
>
> Re-run every Monday in public CI.

**3 — it already happened to someone:**

> Not hypothetical. LifeOS shipped 46 skills at ~3× the budget and Claude Code dropped most
> of them at session start (issue #1205). One line in CI catches that on the PR:
>
> `python skillrot.py . --fail-over-budget`

**4 — what else it checks:**

> > skills that never fired (from your *local* transcripts — nothing leaves your machine)
> > two skills answering to the same /command
> > near-identical descriptions the router coin-flips between
> > frontmatter that silently kills a skill
> > fields that make a claude.ai upload fail (--portable)

**5 — why not /skill-doctor:**

> /skill-doctor only sees skills already loaded in your session.
> skillrot reads any folder offline — a marketplace, a PR, a repo you haven't installed —
> and gives the same numbers every run.

**6 — the ask (drives replies and saves):**

> Reply with a public skill repo and I'll post its number.

### Single-post variant

> Claude Code gives your skill listing 1% of the context window. Past that, it silently
> drops descriptions and those skills stop getting picked.
>
> 4 of 5 popular skill libraries I audited are over. One is 27× over.
>
> (link in reply)

## Follow-ups (week one)

1. **Reply-audits.** For each repo people send, run `skillrot <repo> --svg out.svg` and
   quote-tweet the SVG with its one-line verdict. Every reply becomes a fresh post with a
   picture.
2. **Before / after.** When anyone trims a library with skillrot, post the two `--svg`
   charts side by side with one line of text — the ponytail format.
3. **Join the /skill-doctor threads** with the one thing it can't do (audit before
   install / in CI), not with a pitch.
4. **Curators.** Send the MP4 and the live-audit card to the accounts that run "tools that
   save tokens" roundups. One inclusion beats ten solo posts.
5. **Show HN** the same week: "Show HN: skillrot – see which of your Claude Code skills the
   router can't see". Lead with the table.

## Rules for the copy

- Lead with the reader's cost, then the number. The product name comes last.
- Only numbers from `docs/runs/`. Say "≈" where it is an estimate; counts are what the
  manifests install (skills + commands). Bundled and claude.ai-synced skills are not on
  disk, so a real session lists a little more, never less.
- Measure, don't dunk. Name libraries only next to their numbers, and offer the fix
  (`skillOverrides`, shorter descriptions) — maintainers are the best amplifiers.
- English for the public post; the audience is global Claude Code users.
- Nothing goes out from the maintainer's account without the maintainer's go-ahead.
