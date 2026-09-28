# Live audit — 2026-09-28

Run [36445780870](https://github.com/Galactic717/skillrot/actions/runs/36445780870) of
[live-audit.yml](../../.github/workflows/live-audit.yml): each library cloned at HEAD and audited with
`python skillrot.py <repo> --no-usage` (200k-token window, 1% listing budget).

| Library | Skills | Listing vs. budget | Name-only | Errors | Warnings |
| --- | ---: | ---: | ---: | ---: | ---: |
| [obra/superpowers](https://github.com/obra/superpowers) | 15 | 0.33× | 0 | 0 | 1 |
| [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) | 25 | 1.17× | 2 | 0 | 0 |
| [affaan-m/ECC](https://github.com/affaan-m/ECC) | 292 | 11.82× | 278 | 0 | 36 |
| [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) | 864 | 14.20× | 864 | 0 | 869 |
| [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) | 382 | 22.74× | 372 | 0 | 31 |

Skill counts are what each plugin manifest installs, not every SKILL.md in the repo;
legacy `commands/` files also enter the real listing and are not counted, so every
number here is a lower bound.

## affaan-m/ECC

```

skillrot 0.2.0

  Context bill
    292 skills discovered
    ~2,000 tokens in the always-on listing  (1.0% of a 200,000-token window)
    ~2,000 tok listing budget (1182% requested)
    over budget by ~21,639 tok: descriptions are being dropped
    ~637,625 tokens of skill bodies waiting to load
    4.4MB on disk

  Heaviest listings  (paid on every message)
      148 tok  /ecc:intent-driven-development
      146 tok  /ecc:flox-environments
      131 tok  /ecc:benchmark-methodology
      129 tok  /ecc:customs-trade-compliance
      128 tok  /ecc:browser-qa
      126 tok  /ecc:living-docs-governance
      126 tok  /ecc:production-scheduling
      126 tok  /ecc:recursive-decision-ledger
      124 tok  /ecc:agent-architecture-audit
      124 tok  /ecc:ito-baskets
```
