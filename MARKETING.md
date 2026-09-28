# skillrot — launch & marketing plan

Positioning, channels, and copy for popularizing skillrot. Everything here is grounded in
real, cited pain (see the research notes at the bottom), not invented hype.

## One-line positioning

> **skillrot** — the deterministic CLI that measures what your Claude Code skill library
> actually costs, and which skills the router has already stopped seeing.

## Who it's for

- **Claude Code power users** who installed several plugin marketplaces and feel sessions
  get "dumber" / fill up faster. They talk about this constantly on X and r/ClaudeCode.
- **Skill and plugin authors** shipping libraries — the people who *cause* budget overflow
  and need a CI gate before release.
- **Teams** standardizing an agent stack who want a reproducible number, not a vibe.

## The wedge (why now, why this)

Every other tool in this space is an **audit skill** — a prose checklist that runs *inside*
Claude, estimates tokens by word count, and returns a differently-worded report each time
(ECC `context-budget`, `gbrain context-audit`, `cost-optimizer`), plus the built-in
`/skill-doctor`. skillrot is the opposite shape: **deterministic, offline, any-directory,
CI-gateable, zero-dependency.** It's the `eslint` of skill libraries, not another advisor.

The anchor story: a well-known repo (`danielmiessler/LifeOS`, issue #1205) shipped 46 skills
whose descriptions summed to ~3× the listing budget, and Claude Code **silently dropped most
of them at session start** — installed, billed, unroutable. skillrot's one-line CI check
catches exactly that, on the PR.

## Channels & sequence

1. **X (primary).** Launch thread (below). Reply to context-engineering / "too many skills"
   threads with the tool, not just the opinion.
2. **Show HN.** Title: *"Show HN: skillrot – measure what your Claude Code skill library
   costs in context"*. Lead with the 4,642-skill number and the LifeOS drop.
3. **Reddit** r/ClaudeAI, r/ClaudeCode. Text post, no link in title; screenshot of the run.
4. **dev.to / short blog.** "Your agent's skills are dropping silently — here's how to see
   it." One diagram (the Mermaid pipeline), one SVG, the CI snippet.
5. **GitHub topics**: `claude-code`, `agent-skills`, `claude-skills`, `context-engineering`,
   `linter`, `llm`. Open a friendly issue on 1–2 giant libraries offering their number.

## The X post (launch thread)

**Tweet 1 — the hook**

> Every Claude Code skill you install is billed on every message — even the ones that never
> fire.
>
> Install enough and Claude Code silently drops the least-used descriptions to fit a 1%
> budget. Those skills go invisible to the router.
>
> I built skillrot to measure the bill. One file, zero deps 🧵

**Tweet 2 — the number** *(attach `docs/assets/budget-hub.svg`)*

> Point it at a 4,642-skill mega-collection:
>
> the skill *names alone* are ~28,000 tokens — 14× the listing budget — so **every single
> description gets dropped**.
>
> Your router can't match a request it can't see.

**Tweet 3 — proof it's real**

> Not hypothetical. danielmiessler/LifeOS shipped 46 skills at ~3× the budget and Claude
> Code silently dropped most at session start (their issue #1205).
>
> skillrot is the CI check that turns that into a failed PR instead of a bad session.

**Tweet 4 — what else it finds**

> It also flags:
> • skills that never fired once (counted from your *local* transcripts — nothing leaves
>   your machine)
> • two skills answering the same /command
> • near-identical descriptions the router coin-flips between
> • frontmatter that breaks a skill silently

**Tweet 5 — why not /skill-doctor**

> /skill-doctor only sees the skills already loaded in a session.
>
> skillrot is deterministic and runs on *any* folder offline — a marketplace, a PR, a repo
> you haven't installed — and fails CI with a stable rule id.

**Tweet 6 — CTA**

> Zero dependencies, one Python file, MIT.
>
> curl it, run it, get your number:
> github.com/Galactic717/skillrot
>
> Reply with your always-on skill bill 👇 I'll audit the biggest one.

### Single-tweet variant (if not threading)

> Your Claude Code skills are taxed on every message — and once you install too many, Claude
> Code silently drops descriptions to fit a 1% budget, so some skills go invisible to the
> router.
>
> skillrot measures it. One file, zero deps, MIT:
> github.com/Galactic717/skillrot

## Copy rules

- Lead with the number, not the tool. The 14×-budget stat and the LifeOS drop are the hook.
- Never overstate: token counts are 4-char/token estimates; say "ranking, not exact."
- No fake benchmarks, no invented testimonials. Cite the issue and the docs.
- English for the public repo; the audience is global Claude Code users.

## Research notes (verified 2026-09-28)

- Listing budget = 1% of context window, least-used descriptions dropped first —
  code.claude.com/docs/en/skills; confirmed independently (Costenaro, Medium).
- LifeOS #1205 — 43/46 descriptions over ceiling, silently dropped (verified live on GitHub).
- Competitors are all in-session prose skills: ECC `context-budget` (word×1.3 estimate),
  `gbrain context-audit`, `cost-optimizer`; plus built-in `/skill-doctor` / `/doctor`.
- Live demand on X/Reddit: "you're losing thousands of tokens every session", "too many
  skills?", "200k context is really 70k with too many tools enabled."
