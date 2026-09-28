# Live audit - 2026-09-28

Run [36447829550](https://github.com/Galactic717/skillrot/actions/runs/36447829550) of
[live-audit.yml](../../.github/workflows/live-audit.yml), skillrot 0.3.0: each library cloned
at HEAD and audited with `python skillrot.py <repo> --no-usage` (200k-token window, 1% listing
budget).

| Library | Skills | Commands | Listing vs. budget | Name-only | Errors | Warnings |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| [obra/superpowers](https://github.com/obra/superpowers) | 15 | 0 | 0.35x | 0 | 0 | 1 |
| [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) | 25 | 9 | 1.3x | 5 | 0 | 0 |
| [affaan-m/ECC](https://github.com/affaan-m/ECC) | 292 | 94 | 13.2x | 375 | 0 | 45 |
| [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) | 864 | 0 | 14.2x | 864 | 0 | 869 |
| [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) | 382 | 104 | 27.4x | 483 | 0 | 33 |

Counts are what each plugin manifest installs (skills and command files), not every
SKILL.md in the repo. A skill and a command sharing a name are listed once.

## affaan-m/ECC

```

skillrot 0.3.0

  Context bill
    292 skills + 94 commands discovered
    2 kept out of context (disable-model-invocation / skillOverrides)
    ~2,027 tokens in the always-on listing  (1.0% of a 200,000-token window)
    ~2,000 tok listing budget (1319% requested)
    over budget by ~24,388 tok: descriptions are being dropped
    ~727,884 tokens of skill bodies waiting to load
    4.7MB on disk

  Heaviest listings  (paid on every message)
      149 tok  /ecc:intent-driven-development
      148 tok  /ecc:flox-environments
      132 tok  /ecc:benchmark-methodology
      130 tok  /ecc:customs-trade-compliance
      129 tok  /ecc:browser-qa
      128 tok  /ecc:production-scheduling
      128 tok  /ecc:recursive-decision-ledger
      126 tok  /ecc:ito-baskets
      126 tok  /ecc:living-docs-governance
      126 tok  /ecc:terminal-opener

  0 error(s), 45 warning(s), 375 name-only
```
