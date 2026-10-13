# Реверс-інженерія доставки, тестів і документації skillrot

> **Актуальний стан: 0.4.0, підготовка релізу.** Є builder, перевірені local/Agensi ZIP
> і повний source distribution. Остаточне ядро: 2064 рядки,
> SHA256 `c73ec50a59708a1323fb32889de9dad3114d1093f76694688dd6eaad91fd842e`.
> Фінальні 213 source tests повторно проходять на Python 3.14.5 і 3.9.25;
> один очікуваний Windows skip. Остаточні artifacts/smoke hashes: `RELEASE.md`.
>
> **Історичний початковий знімок:** розділи до «Повний індекс тестових блоків» описують
> стан 0.4.0.dev0 **перед цією роботою**: 179 тестів, 8 package smokes і ще відсутній ZIP
> builder. Формулювання «немає», «потрібно» та початкові line ranges у цих розділах
> є baseline findings, а не твердженнями про фінальний продукт. Фінальний індекс і всі
> розділи після нього описують актуальну доставку 0.4.0.


Дата дослідження: 2026-10-13. Об'єкт: наявний робочий каталог `repository checkout`, версія
`0.4.0.dev0`, включно з незакоміченими змінами, які вже існували перед цим дослідженням.
Цей документ описує допоміжні файли. Аналіз алгоритмів `skillrot.py` виконується окремо.
Початкові розділи описують знімок до змін. Фінальний індекс тестів і розділ нової
доставки описують підготовлену версію 0.4.0; ці знімки явно розділені.

У початковому знімку прочитано всі рядки чотирьох тестових модулів, обох Python-скриптів, HTML, конфігурації
пакета, workflow і текстової документації. У фінальному знімку додатково
прочитано обидва нові test modules, builder, source atlas і розширений package smoke.
Таблиці в кінці містять актуальний діапазон кожного тесту й допоміжного методу. Порожні рядки, коментарі й декоратори належать прилеглому
блоку; вони не створюють прихованої поведінки. Бінарні медіафайли описано як артефакти,
бо в них немає рядків вихідного коду.

## Початковий знімок: що саме доставляв проєкт

Проєкт має дві різні форми використання:

1. Python CLI: модуль `skillrot.py`, запуск через `python skillrot.py` або встановлену
   команду `skillrot`. Аналіз локальний; runtime-залежностей немає.
2. Agent Skill: інструкція `SKILL.md`, той самий Python-модуль і довідник правил.
   Інструкція доручає агенту запустити CLI, прочитати JSON та пояснити знахідки.

На момент **початкового знімка, до реалізації** автоматизовано й перевірено тільки доставку CLI. Копіювання
Agent Skill описано в README вручну. Колесо Python не містить `SKILL.md` або правил.
Встановлення wheel саме по собі не додає `/skillrot` до Claude або іншого агента.
Саме цей розрив потрібно закрити перед розміщенням архіву skill на маркетплейсі.

## Верифікований початковий стан

| Перевірка | Результат і межа висновку |
| --- | --- |
| `python -m unittest discover -s tests -v` | 179 тестів, 0 помилок, Windows, CPython 3.14.5 |
| `uv run --no-project --python 3.9 python -m unittest discover -s tests` | 179 тестів, 0 помилок, реальний CPython 3.9.25; інтерпретатор завантажено в кеш uv, не в репозиторій |
| `python -m mypy . --ignore-missing-imports` з окремим тимчасовим кешем | 7 Python-файлів, 0 зауважень, mypy 2.2.0 |
| `ast.parse(..., feature_version=(3, 9))` для всіх Python-файлів | Усі файли сумісні з граматикою Python 3.9; цей результат додатковий до реального запуску 3.9 |
| Build у тимчасовій копії: `python -m build --no-isolation` | Успішні sdist і універсальне `py3-none-any` wheel; wheel зібрано зі sdist |
| `python scripts/smoke_package.py <temp-dist>` | 8 тестів установленої команди, 0 помилок; запуск поза вихідним каталогом |

SHA-256 початкового `skillrot.py`:
`904182c260224f775044b0ff6caac3634b4ed98c22370b1d727542ddc01a685f`.
Це локальна перевірка Windows; вона не означає, що в цій сесії повторно запущено Linux
і macOS. Для них репозиторій має CI-матрицю. Вихідний стан уже містить 179 тестів,
тому старі 83 тести з `PRODUCTION_AUDIT.md` не є актуальним підсумком цього запуску.

## Конфігурація Python-пакета: pyproject.toml, 34 рядки

| Рядки | Що робить блок |
| --- | --- |
| 1–3 | PEP 517 backend `setuptools.build_meta`, мінімум setuptools 77.0.3 для SPDX metadata |
| 5–13 | Ідентичність `skillrot`, dev-версія, опис, README, мінімум Python 3.9, MIT і файл ліцензії, автор |
| 14–21 | Пошукові ключові слова й класифікатори: консольна beta-утиліта для розробників, quality assurance |
| 24–28 | Homepage, документація, source й issues ведуть на один GitHub-репозиторій |
| 30–31 | Console script `skillrot` імпортує `skillrot:main`; системний launcher створює installer |
| 33–34 | Єдиний `py-module`; немає package-data, skill bundle, додаткових runtime-модулів |

`dependencies = []` — перевірена властивість runtime, а не обіцянка нульових залежностей
для збірки чи відео. Wheel містить `skillrot.py`, MIT і `.dist-info`; він не є executable
binary і потребує Python. `0.4.0.dev0` — передреліз, тому стабільний продаж повинен мати
узгоджені версію CLI, metadata, README й артефактів.

## Установлений smoke runner: scripts/smoke_package.py, 161 рядок

| Рядки | Поведінка |
| --- | --- |
| 1–8 | Документує build-команду та ізольовану перевірку встановлення |
| 9–20 | Future annotations і лише standard-library imports: argparse, JSON, subprocess, temp, venv, XML, ZIP |
| 23–29 | Клас unittest і атрибути, які заповнює setup |
| 31–44 | Вимагає рівно одне wheel і sdist; читає wheel metadata, дістає версію, забороняє Requires-Dist, перевіряє LICENSE |
| 45–60 | Реєструє автоматичне прибирання temp-каталогу, створює venv з pip, обирає Windows/POSIX launchers, ставить локальне wheel через `--no-index --no-deps`, готує skill у шляху з пробілами |
| 62–69 | Статичний fixture writer створює валідний `SKILL.md`, допускає підміну тексту для негативних випадків |
| 71–79 | Запуск установленої команди з temp cwd; прибирає PYTHONPATH, PYTHONHOME, listing-budget env; керує кодуванням; timeout 30 секунд |
| 81–84 | Перевіряє exit і відсутність traceback; stderr додає до повідомлення про збій |
| 86–92 | Версія мусить збігатися з wheel metadata; help мусить містити budget gate |
| 94–105 | Валідний portable skill: exit 0, JSON schema 1, harness Claude, estimated true, usage unavailable, рівно одна навичка й жодної знахідки |
| 107–111 | SVG мусить бути коректним XML із SVG namespace |
| 113–122 | Початкова порожня лінія породжує SR001 і exit 1; мале context window з budget gate теж дає 1 |
| 124–129 | Відсутній шлях окремо й разом із валідним шляхом дає operational exit 2 |
| 131–134 | Неможливий каталог SVG не може дати успішний exit |
| 136–141 | Нульовий/NaN token divisor, негативний context, NaN fraction дають usage exit 2 |
| 143–148 | Японський шлях мусить пережити справжній cp1251 stdout pipe і відновитися з JSON |
| 151–157 | Parser приймає dist path, запускає рівно цей test class, повертає 0 або 1 за suite result |
| 160–161 | Entry point передає результат `main()` у SystemExit |

Це суттєва перевірка користувацьких контрактів. Вона не встановлює sdist окремим pip
викликом, але стандартний `python -m build` спершу робить sdist й потім wheel із нього.
Наразі runner не перевіряє Agent Skill архів, підтримку іншого агента або фактичну
якість агентської відповіді.

## GitHub Actions

### .github/workflows/ci.yml, 40 рядків

| Рядки | Поведінка |
| --- | --- |
| 1–9 | Назва, push на main і pull requests; token має тільки contents:read |
| 11–18 | 12 комбінацій: Ubuntu/Windows/macOS × Python 3.9/3.12/3.13/3.14; fail-fast false |
| 19–25 | Checkout v4 без збереження credentials; setup-python v5 обирає matrix interpreter |
| 26–30 | На Python 3.13 ставить pinned mypy 2.2.0 й перевіряє всі Python-файли; ignore missing imports допускає optional Playwright |
| 31–32 | Уся source unittest suite |
| 33–34 | Portable self-audit без читання transcript, gate на error |
| 35–38 | Ставить build frontend, збирає sdist і wheel через build isolation |
| 39–40 | Запускає installed-package smoke runner для dist |

Матриця покриває сумісність CLI, але workflow поки не збирає marketplace ZIP і не
публікує release artifacts. Actions вказані major tags, не immutable commit SHA;
це звичайний maintenance tradeoff, а не відтворений дефект виконання CLI.

### .github/workflows/live-audit.yml, 91 рядок

| Рядки | Поведінка |
| --- | --- |
| 1–12 | Щотижневий запуск понеділками о 06:17 UTC й ручний запуск; contents:read |
| 14–26 | Ubuntu, fail-fast false, п'ять публічних бібліотек; назви repo — фіксовані matrix literals |
| 27–33 | Checkout tool без persistent credentials, Python 3.12 |
| 35–36 | Shallow clone поточного HEAD цільового репозиторію в target; мережа є тільки в workflow, не CLI |
| 38–48 | Bash, явні параметри моделі 200000/0.01/4; окремі text, JSON, SVG запуски |
| 49–60 | Вбудований Python імпортує дату/JSON/path/subprocess/skillrot і формує base command |
| 61–74 | Provenance записує UTC, target URL/SHA, tool SHA/version, Python, workflow URL й усі три commands |
| 75–83 | Summary додає target/tool commits і перші 12 рядків звіту |
| 85–91 | Upload artifacts v4: text, JSON, SVG; `.provenance.json` теж потрапляє під `audit-*.json`; fail якщо файлів немає; 90 днів retention |

Workflow не використовує lint gates: знаходження проблем у чужій бібліотеці є
результатом звіту, не падінням job. Operational failure має зірвати Bash step; shell
`bash` у GitHub Actions застосовує `-e -o pipefail`, тому `tee` не маскує exit CLI.
Target HEAD змінюється, але нові запуски зберігають SHA. Постійно опубліковані цифри
потребують власної копії provenance, бо artifact retention обмежений.

## Демонстраційний renderer: docs/demo/render.py, 79 рядків

| Рядки | Поведінка |
| --- | --- |
| 1–8 | Інструкція full render/stills; явно вимагає Playwright Chromium і ffmpeg |
| 9–16 | Imports; Playwright потрібен уже під час import цього optional скрипта, а не CLI |
| 18–20 | Виводить HERE/PAGE/ASSETS від фізичного шляху скрипта; file URI з `?capture=1`; FPS 30 |
| 23–32 | Launch Chromium, viewport 1920×1080, відкриває локальну HTML, чекає seek, вибирає кожен deterministic timestamp й screenshot, закриває browser |
| 35–47 | Parser --stills; float timestamps з CSV, створює stills, рендерить, перейменовує f0000 на t000.0 і повертається |
| 49–56 | Другий browser читає `window.DURATION` з HTML |
| 58–67 | Тимчасові кадри; 30 FPS; ffmpeg H.264 slow/CRF20/yuv420p/faststart, overwrite існуючого MP4 |
| 68–71 | GIF: 12 FPS, ширина 960, Lanczos, 64-color palette, Bayer dither, diff mode; overwrite існуючого GIF |
| 72–75 | Друк розмірів; finally прибирає тільки створений temp directory |
| 78–79 | Entry point main |

Renderer потрібен лише для створення рекламного медіа. Його dependencies не входять
у shipped CLI. Він не має validation --stills для NaN/negative/дубльованих timestamps,
а однакове округлення імен до 0.1 секунди може перезаписувати stills. Це обмеження
optional developer utility; користувацький аудит від нього не залежить.

## Демонстраційна HTML: docs/demo/explainer.html, 311 рядків

| Рядки | Поведінка |
| --- | --- |
| 1–6 | Локальна HTML5-сторінка, en, UTF-8, viewport, заголовок прямо називає historical v0.3.0 |
| 7–25 | CSS tokens, reset, нерухома сцена 1920×1080, absolute sections, mono font, brand |
| 27–29 | Стилі hook-сцени |
| 31–54 | Стилі listing, name/description/tag rows, budget gauge, counters, legend |
| 56–65 | Псевдотермінал: bar/dots/pre і семантичні кольори |
| 67–82 | Leaderboard rows, log tracks, counts, статуси, axis і provenance caption |
| 84–92 | CTA word/chips/commands/repository URL |
| 93–102 | DOM stage, historical brand і вступ про обмежений listing budget |
| 104–124 | DOM listing-графіки; estimates, retained names, potential omission; контейнер рядків заповнює JS |
| 126–131 | DOM термінала з historical date/version |
| 133–139 | Historical leaderboard, log-scale label і workflow attribution |
| 141–148 | CTA: один Python файл, dependency-free CLI, git clone v0.3.1, GitHub URL |
| 150–156 | JS duration 27 секунд, clamp/segment/ease/element helper, п'ять scene intervals |
| 158–182 | 12 зафіксованих ECC names/descriptions, schematic cost units; DOM rows створюються з локальних constants через innerHTML |
| 184–200 | Збережені v0.3.0 terminal strings; escaping `&` і `<` перед HTML rendering |
| 202–225 | П'ять зафіксованих historical ratios/drop counts; log axis, bar/status DOM |
| 227–231 | show() crossfade за входом/виходом scene; повертає visibility |
| 233–241 | seek(): задає всі scene opacities, brand, hook ease/translation |
| 243–271 | Показує names, намагається показати descriptions, перші п'ять fit, решта dim/strike/tag; updates gauge і counters; це схема, не CLI computation |
| 273–285 | Typewriter командного рядка й поступове додавання історичного stdout; cursor animation |
| 287–293 | Staggered reveal leaderboard і growth log bars |
| 295–303 | Експортує seek/DURATION; scaleStage пропорційно вписує 1920×1080 й центрує при resize |
| 304–308 | У capture mode тільки seek(0), інакше requestAnimationFrame і 27-second loop |
| 309–311 | Закриває script/body/html |

Сторінка не завантажує remote resources і не обчислює живий аудит. Константи роблять
відеокадри відтворюваними. Усередині historical terminal ще є старі формулювання
«paid on every message» і «descriptions are being dropped»; global historical label
зменшує плутанину, проте цей фрагмент не годиться як актуальний proof для реклами.
Презентація початкових аудитів не дозволяє відновити target SHAs, яких тоді не записали.

## Документація й приклади: повна карта рядків

| Файл / рядки | Що містить і як впливає на продукт |
| --- | --- |
| README.md 1–15 | Product promise, offline/zero-runtime-deps, minimum Python; відрізняє checkout від stable v0.3.1 |
| README.md 16–41 | Source quick start, install stable git tag у venv, git/build prerequisites, development install |
| README.md 42–64 | Ручне встановлення Agent Skill для Bash і PowerShell; копіює SKILL, CLI, rules |
| README.md 65–85 | Requested/retained/body distinctions; правильні межі model-vs-runtime і practical pruning |
| README.md 86–131 | Усі CLI examples; default Claude discovery, manifests/profile omissions, `--all`, settings і other-harness assumptions |
| README.md 132–153 | 4 chars/token, estimated status, deterministic no-usage ordering, 1536 cap, local transcript privacy й null-vs-zero |
| README.md 154–191 | Bounded parser, normative-vs-policy severities, portable subset, таблиця кожного rule |
| README.md 192–226 | Exit 0/1/2, JSON shape/schema/model/costs/invocations, CI і provenance |
| README.md 227–239 | skillscore і Claude-native alternatives; не заявляє унікальність загальних static checks |
| README.md 240–247 | Historical assets v0.3.0, unreproducible old target SHAs, нова provenance практика |
| README.md 248–251 | Contributing/changelog/MIT |
| SKILL.md 1–6 | Portable frontmatter name/description/license/allowed-tools; intended discovery triggers |
| SKILL.md 8–27 | Agent workflow і CLI calls через `${CLAUDE_SKILL_DIR}`; Claude-specific path assumption |
| SKILL.md 29–40 | Exact requested/retained/body/invocation semantics для відповіді агента |
| SKILL.md 42–56 | Шість instruction points: lead pressure, errors/conflicts, estimate caveat, usage coverage, heuristics, YAML subset |
| SKILL.md 58–62 | Other harness estimate caveat, не змінювати чужі skills без конкретного user request, read rules on uncertainty |
| docs/RULES.md 1–16 | Sources checked 2026-10-08, policy й subset caveats |
| docs/RULES.md 17–24 | SR001 frontmatter first line |
| docs/RULES.md 25–30 | SR002 missing description, host fallback, portable error |
| docs/RULES.md 31–36 | SR003 1536 combined listing cap vs 1024 portable description cap |
| docs/RULES.md 37–43 | SR004 both invocation controls disabled |
| docs/RULES.md 44–49 | SR005 boolean spelling/types |
| docs/RULES.md 50–54 | SR006 missing closing delimiter |
| docs/RULES.md 55–59 | SR007 unavailable file |
| docs/RULES.md 60–66 | SR008 Git symlink stub heuristic |
| docs/RULES.md 67–74 | SR009 syntax/unsupported YAML, not universal host rejection |
| docs/RULES.md 75–83 | SR010 portable fields vs Claude fields |
| docs/RULES.md 84–88 | SR011 compatibility <=500 |
| docs/RULES.md 89–95 | SR013 name constraints й directory match |
| docs/RULES.md 96–107 | SR014 types, description <=1024, metadata string map, supported-subset limits |
| docs/RULES.md 108–114 | SR012 unknown top-level field |
| docs/RULES.md 115–120 | SR020 conflicting command, precedence caution |
| docs/RULES.md 121–129 | SR021 lexical overlap, exact duplicates, candidate-pruning limitations |
| docs/RULES.md 130–135 | SR022 trigger-language heuristic |
| docs/RULES.md 136–142 | SR023 nonblank body lines threshold/progressive disclosure |
| docs/RULES.md 143–150 | SR024 observed history, null when unavailable, no proof of uselessness |
| docs/RULES.md 151–155 | SR025 short descriptions heuristic |
| docs/RULES.md 156–168 | SR030 name-only modeled retention, settings/inventory/budget and ordering limits |
| CONTRIBUTING.md 1–7 | One-file/zero-runtime dependency policy, behavior regressions й normative references |
| CONTRIBUTING.md 8–17 | Source suite/self-audit/typecheck commands |
| CONTRIBUTING.md 18–39 | Build/smoke commands, clean dist requirement, platform matrix, Python 3.9 compatible build tooling |
| CONTRIBUTING.md 40–50 | JSON/exit compatibility, changelog, immutable provenance й finite retention |
| CHANGELOG.md 1–27 | Already-existing unreleased 0.4 hardening, compatibility impact, no assertion that published 0.3.1 contains it |
| CHANGELOG.md 28–31 | v0.3.1 budget gate historical change |
| CHANGELOG.md 32–34 | v0.3.0 budget/demo release |
| MARKETING.md 1–17 | Target workflow, admissible claims, explicit rejection of unmeasured savings/router certainty |
| MARKETING.md 18–31 | Draft copy й evidence requirements |
| MARKETING.md 32–42 | Four-step release-version demo plan with before/after evidence |
| MARKETING.md 43–56 | Historical media label; earlier X research is unverified, not market proof |
| MARKETING.md 57–62 | Fair comparison/native diagnostics; previous approval wording is repository guidance, latest user authorization governs current scope |
| docs/PRODUCTION_AUDIT.md 1–36 | Older audit scope, baseline commit, component map, offline claim |
| docs/PRODUCTION_AUDIT.md 37–51 | Historical 83-test/build/CI/repository evidence; not current 179-test verification |
| docs/PRODUCTION_AUDIT.md 52–88 | Table of reproduced pre-hardening problems й two exit-contract examples |
| docs/PRODUCTION_AUDIT.md 89–114 | Normative references and limits of old examples |
| docs/PRODUCTION_AUDIT.md 115–133 | Older seven-way primary-source competition comparison |
| docs/PRODUCTION_AUDIT.md 134–157 | Buyer/employer assessment, free alternatives, hypothetical future services; not implemented paid features |
| docs/PRODUCTION_AUDIT.md 158–162 | Stale «verification is in progress» footer; must be updated or archived for a release |
| docs/runs/self-audit.txt 1–15 | Saved v0.2.0 one-skill stdout, older context-billing vocabulary, no immutable provenance |
| docs/runs/live-audit-2026-09-28.md 1–17 | GitHub run link, five library metrics and earlier model assumptions |
| docs/runs/live-audit-2026-09-28.md 18–47 | ECC historical stdout, earlier listing accounting; retain only as labeled historical example |
| LICENSE 1–21 | MIT copyright, redistribution requirements, warranty/liability language; resale allowed if notice retained |
| .gitignore 1–8 | Python caches/bytecode, egg-info, build/dist, venv, pytest cache; no runtime logic |

## Бінарні й згенеровані матеріали

| Файл | Функція / ідентифікація початкового артефакту |
| --- | --- |
| docs/assets/budget-ecc.svg | 1 physical line, 3504 B; XML/CSS з історичним 386-entry / 2027-token / 1319% chart; не тягне мережу; рядок містить усі style/rect/text/line elements |
| docs/assets/live-audit-card.png | 303532 B; готова historical растрова картка, а не вихідний код |
| docs/assets/skillrot-explainer.gif | 1855296 B; готова animation від попереднього renderer/content, не перегенерована змінами HTML |
| docs/assets/skillrot-explainer.mp4 | 959337 B; готовий historical video, аналогічно не оновлюється від редагування HTML |

SVG SHA-256: `827062e3511771c6d00a0605b8c39976cb567429cbc556a57f3673ee6863689f`.
PNG SHA-256: `106b6d75463667abd616306bcc966a0e6317ebc55680acf5865f30d927cdc798`.
GIF SHA-256: `ae82a1bb1ed504eab12c37f39bf330a5090808afcd9f4996b7831fbd475bcf66`.
MP4 SHA-256: `6af185d6c5fcdabea61b6c3b74bff12d76a4e449ac4d4af84cdcbb62629591fb`.

## Що доводять тести й чого вони не доводять

Усі чотири модулі використовують стандартний unittest і тимчасові реальні filesystem
fixtures. Це корисні тести поведінки: exit codes, report fields, manifested inventory,
privacy-related evidence attribution, malformed syntax та Unicode output. Вони не
перевіряють runtime loader Claude через реальний Claude session, live invocation quality,
повний YAML spec, Agensi review або всі можливі Agent Skills архіви.

`tests/test_skillrot.py` має 751 рядок: imports/path injection/helpers/GOOD fixture у
1–42, 21 test class blocks у 45–747 і direct unittest entry point 750–751. Частина
перевірок викликає public CLI, частина — внутрішні functions для точних invariant.

`tests/test_frontmatter_hardening.py` має 242 рядки: imports/path injection 1–10,
class helpers 13–25, bounded-parser/portable cases 27–238, entry point 241–242.
Він перевіряє quoted/comment/block/list/map shapes, invalid syntax, field types,
Unicode names, absolute-vs-relative directory comparison й invalid UTF-8.

`tests/test_discovery_cli.py` має 495 рядків: imports/helpers 1–47, discovery tests
50–322, operational tests 325–491, entry point 494–495. Test harness із ExitStack
підміняє home/cwd та budget env, captures stdout/stderr і intercepts argparse exit.
Symlink containment test у Windows за потреби створює temp junction через mklink;
прибирає тільки fixture TemporaryDirectory.

`tests/test_accounting_usage.py` має 173 рядки: imports/entry fixture 1–16, accounting
19–74, transcript evidence 77–127, hostile report text 130–147, collision boundary
150–169, entry point 172–173. Перевіряє reconciled costs, unknown-vs-zero, ambiguity,
XML/terminal control safety й exact Unicode duplicate groups.

Нижче кожен метод має власний рядковий діапазон. Англійські імена збережені точно,
щоб знаходити regression без неоднозначного перекладу. Scope class пояснює групу;
назва методу вказує очікувану властивість. Усі class-level lines між methods —
структура unittest та порожні separators, а не пропущені обчислення.

## Початкові gaps перед marketplace delivery — до виправлень

1. Немає збирача/перевірки downloadable Agent Skill ZIP; CLI wheel не заміняє його.
   Потрібен невеликий self-contained archive з SKILL, CLI, rules, LICENSE і manifest.
2. SKILL command залежить від Claude-only variable `CLAUDE_SKILL_DIR`. Для оголошеної
   підтримки інших agents потрібна host-neutral інструкція знаходження script, а
   default inventory/profile і надалі слід чесно називати Claude-specific.
3. Наявна версія dev; стабільний bundle треба узгодити з CLI й pyproject та реально
   smoke-test після extraction у каталог із пробілами/Unicode, поза checkout.
4. Старі PNG/GIF/MP4 і saved stdout не є новими production metrics; рекламі потрібен
   новий reproducible fixture/demo або явний historical label у самих assets.
5. Старий production audit ще каже, що verification триває. Перед передачею користувачу
   треба записати fresh results і не змішувати pre-hardening findings із станом release.

Немає підстав переписувати перевірену delivery-частину з нуля. Потрібні конкретні
доповнення до її контракту: skill archive, portable instructions, installed/extracted
smoke coverage, coherent version та нове evidence-based presentation.

## Повний індекс тестових блоків

Діапазони фінального source tree 0.4.0. Фінальна suite має 213 tests.

### tests/test_accounting_usage.py

| Рядки | Scope / перевірка |
| --- | --- |
| 12–16 | Допоміжний метод/fixture: `entry` |
| 19–74 | Клас unittest: `ListingAccountingRegressionTests` |
| 20–25 | Regression: `ListingAccountingRegressionTests.test_unfilled_budget_does_not_bill_a_dropped_description` |
| 27–34 | Regression: `ListingAccountingRegressionTests.test_aggregate_and_per_entry_costs_use_the_same_usage_order` |
| 36–38 | Regression: `ListingAccountingRegressionTests.test_hidden_skill_has_zero_requested_listing_cost` |
| 40–43 | Regression: `ListingAccountingRegressionTests.test_name_only_override_bills_only_the_name` |
| 45–55 | Regression: `ListingAccountingRegressionTests.test_json_costs_reconcile_with_hidden_and_dropped_entries` |
| 57–66 | Regression: `ListingAccountingRegressionTests.test_shadowed_command_is_not_billed_twice_in_json` |
| 68–74 | Regression: `ListingAccountingRegressionTests.test_json_unicode_is_safe_in_legacy_windows_pipes` |
| 77–127 | Клас unittest: `TranscriptEvidenceRegressionTests` |
| 78–82 | Допоміжний метод/fixture: `TranscriptEvidenceRegressionTests.counts` |
| 84–87 | Regression: `TranscriptEvidenceRegressionTests.test_tool_call_key_order_and_spacing_do_not_change_usage` |
| 89–94 | Regression: `TranscriptEvidenceRegressionTests.test_nested_assistant_tool_blocks_are_counted` |
| 96–99 | Regression: `TranscriptEvidenceRegressionTests.test_user_command_json_whitespace_is_irrelevant` |
| 101–107 | Regression: `TranscriptEvidenceRegressionTests.test_unrelated_records_and_invalid_json_are_not_invocations` |
| 109–114 | Regression: `TranscriptEvidenceRegressionTests.test_tool_result_content_is_not_recursively_counted_as_an_invocation` |
| 116–120 | Regression: `TranscriptEvidenceRegressionTests.test_bare_local_command_is_not_credited_to_namespaced_plugins` |
| 122–127 | Regression: `TranscriptEvidenceRegressionTests.test_ambiguous_bare_usage_has_no_attributed_plugin_invocations` |
| 130–147 | Клас unittest: `UntrustedReportTextTests` |
| 131–140 | Regression: `UntrustedReportTextTests.test_escaped_yaml_controls_cannot_corrupt_svg_xml` |
| 142–147 | Regression: `UntrustedReportTextTests.test_untrusted_names_cannot_emit_terminal_escape_sequences` |
| 150–169 | Клас unittest: `CollisionBoundaryRegressionTests` |
| 151–155 | Regression: `CollisionBoundaryRegressionTests.test_body_description_fallback_keeps_when_to_use` |
| 157–164 | Regression: `CollisionBoundaryRegressionTests.test_exact_duplicates_survive_the_common_word_cutoff` |
| 166–169 | Regression: `CollisionBoundaryRegressionTests.test_unicode_duplicate_descriptions_are_detected` |

### tests/test_discovery_cli.py

| Рядки | Scope / перевірка |
| --- | --- |
| 18–25 | Допоміжний метод/fixture: `write_skill` |
| 28–30 | Допоміжний метод/fixture: `write_json` |
| 33–47 | Допоміжний метод/fixture: `run_cli` |
| 50–333 | Клас unittest: `DiscoveryBoundaryTests` |
| 51–53 | Допоміжний метод/fixture: `DiscoveryBoundaryTests.setUp` |
| 55–56 | Допоміжний метод/fixture: `DiscoveryBoundaryTests.tearDown` |
| 58–61 | Допоміжний метод/fixture: `DiscoveryBoundaryTests.plugin` |
| 63–66 | Regression: `DiscoveryBoundaryTests.test_plain_skills_folder_does_not_invent_plugin_namespace` |
| 68–73 | Regression: `DiscoveryBoundaryTests.test_other_harness_paths_do_not_invent_plugin_namespace` |
| 75–77 | Regression: `DiscoveryBoundaryTests.test_generic_plugins_directory_is_not_plugin_ownership_evidence` |
| 79–86 | Regression: `DiscoveryBoundaryTests.test_default_roots_only_include_the_modeled_claude_profile` |
| 88–92 | Regression: `DiscoveryBoundaryTests.test_scan_all_overrides_shallow_installed_discovery` |
| 94–97 | Regression: `DiscoveryBoundaryTests.test_empty_plugin_manifest_does_not_count_documentation_mirrors` |
| 99–102 | Regression: `DiscoveryBoundaryTests.test_explicit_empty_skills_does_not_enable_root_skill_fallback` |
| 104–108 | Regression: `DiscoveryBoundaryTests.test_existing_empty_skills_directory_disables_root_skill_fallback` |
| 110–116 | Regression: `DiscoveryBoundaryTests.test_plugin_json_requires_a_name` |
| 118–126 | Regression: `DiscoveryBoundaryTests.test_missing_explicit_manifest_components_are_operational_errors` |
| 128–135 | Regression: `DiscoveryBoundaryTests.test_missing_local_marketplace_source_is_an_operational_error` |
| 137–141 | Regression: `DiscoveryBoundaryTests.test_remote_only_marketplace_does_not_count_documentation_mirrors` |
| 143–156 | Regression: `DiscoveryBoundaryTests.test_required_marketplace_fields_cannot_be_silently_omitted` |
| 158–164 | Regression: `DiscoveryBoundaryTests.test_explicit_empty_marketplace_is_accepted_alongside_other_inputs` |
| 166–187 | Regression: `DiscoveryBoundaryTests.test_marketplace_component_extensions_with_plugin_json_are_diagnosed` |
| 189–198 | Regression: `DiscoveryBoundaryTests.test_marketplace_strict_flag_must_be_boolean` |
| 200–209 | Regression: `DiscoveryBoundaryTests.test_empty_remote_source_identifier_is_diagnosed` |
| 211–223 | Regression: `DiscoveryBoundaryTests.test_strict_false_conflict_in_non_listing_component_is_diagnosed` |
| 225–232 | Regression: `DiscoveryBoundaryTests.test_nested_plugin_commands_keep_path_qualified_names` |
| 234–242 | Regression: `DiscoveryBoundaryTests.test_manifest_skill_paths_cannot_escape_checkout` |
| 244–252 | Regression: `DiscoveryBoundaryTests.test_marketplace_source_cannot_escape_checkout` |
| 254–261 | Regression: `DiscoveryBoundaryTests.test_manifest_command_path_cannot_escape_checkout` |
| 263–282 | Regression: `DiscoveryBoundaryTests.test_manifest_symlink_path_cannot_escape_checkout` |
| 284–293 | Regression: `DiscoveryBoundaryTests.test_malformed_manifest_shapes_are_operational_errors` |
| 295–302 | Regression: `DiscoveryBoundaryTests.test_invalid_manifest_json_is_not_a_recursive_scan` |
| 304–311 | Regression: `DiscoveryBoundaryTests.test_direct_skill_audit_diagnoses_its_malformed_owning_manifest` |
| 313–333 | Regression: `DiscoveryBoundaryTests.test_manifest_json_parser_recursion_is_an_operational_error` |
| 319–324 | Допоміжний метод/fixture: `DiscoveryBoundaryTests.test_manifest_json_parser_recursion_is_an_operational_error.loads` |
| 336–502 | Клас unittest: `OperationalCliTests` |
| 337–344 | Допоміжний метод/fixture: `OperationalCliTests.setUp` |
| 346–347 | Допоміжний метод/fixture: `OperationalCliTests.tearDown` |
| 349–352 | Regression: `OperationalCliTests.test_a_missing_input_among_valid_inputs_is_an_operational_failure` |
| 354–358 | Regression: `OperationalCliTests.test_svg_write_failure_is_an_operational_failure` |
| 360–371 | Regression: `OperationalCliTests.test_invalid_numeric_options_are_rejected_before_audit` |
| 373–384 | Regression: `OperationalCliTests.test_malformed_nested_settings_are_operational_failures` |
| 386–394 | Regression: `OperationalCliTests.test_malformed_plugin_registry_is_an_operational_failure` |
| 396–409 | Regression: `OperationalCliTests.test_distinct_scoped_plugin_roots_are_an_explicit_profile_limitation` |
| 411–421 | Regression: `OperationalCliTests.test_repeated_registry_records_for_one_physical_root_are_accepted` |
| 423–430 | Regression: `OperationalCliTests.test_malformed_marketplace_registry_is_an_operational_failure` |
| 432–437 | Regression: `OperationalCliTests.test_unresolved_enabled_plugin_does_not_report_a_clean_inventory` |
| 439–444 | Regression: `OperationalCliTests.test_absent_enabled_plugins_does_not_inventory_disabled_cache` |
| 446–457 | Regression: `OperationalCliTests.test_plugin_overrides_do_not_change_plugin_listing` |
| 459–466 | Regression: `OperationalCliTests.test_no_transcript_evidence_does_not_claim_never_invoked` |
| 468–479 | Regression: `OperationalCliTests.test_text_output_falls_back_safely_on_ascii_streams` |
| 469–474 | Клас unittest: `OperationalCliTests.test_text_output_falls_back_safely_on_ascii_streams.AsciiStream` |
| 472–474 | Допоміжний метод/fixture: `OperationalCliTests.test_text_output_falls_back_safely_on_ascii_streams.AsciiStream.write` |
| 481–491 | Regression: `OperationalCliTests.test_closed_output_pipe_does_not_print_a_traceback` |
| 493–502 | Regression: `OperationalCliTests.test_help_and_version_handle_closed_output_pipes` |
| 505–506 | Module entry point |

### tests/test_frontmatter_hardening.py

| Рядки | Scope / перевірка |
| --- | --- |
| 13–238 | Клас unittest: `FrontmatterHardeningTests` |
| 14–15 | Допоміжний метод/fixture: `FrontmatterHardeningTests.parse` |
| 17–22 | Допоміжний метод/fixture: `FrontmatterHardeningTests.findings` |
| 24–25 | Допоміжний метод/fixture: `FrontmatterHardeningTests.errors` |
| 27–32 | Regression: `FrontmatterHardeningTests.test_boolean_comments_preserve_invocation_controls` |
| 34–37 | Regression: `FrontmatterHardeningTests.test_quoted_keys_cannot_hide_nonportable_fields` |
| 39–42 | Regression: `FrontmatterHardeningTests.test_comment_marker_inside_quotes_is_text` |
| 44–48 | Regression: `FrontmatterHardeningTests.test_quoted_escapes_decode_without_losing_trigger_text` |
| 50–53 | Regression: `FrontmatterHardeningTests.test_multiline_quoted_scalar_folds_newlines` |
| 55–58 | Regression: `FrontmatterHardeningTests.test_multiline_quoted_scalar_preserves_blank_line` |
| 60–63 | Regression: `FrontmatterHardeningTests.test_multiline_double_quote_backslash_joins_lines` |
| 65–68 | Regression: `FrontmatterHardeningTests.test_plain_scalar_preserves_blank_line_paragraph` |
| 70–74 | Regression: `FrontmatterHardeningTests.test_indented_block_delimiter_does_not_end_frontmatter` |
| 76–79 | Regression: `FrontmatterHardeningTests.test_flat_flow_list_preserves_quoted_comment_characters` |
| 81–84 | Regression: `FrontmatterHardeningTests.test_indentless_block_sequence_is_supported` |
| 86–90 | Regression: `FrontmatterHardeningTests.test_plain_continuation_comments_do_not_become_routing_text` |
| 92–97 | Regression: `FrontmatterHardeningTests.test_plain_continuations_preserve_quotes_and_boolean_looking_text` |
| 99–103 | Regression: `FrontmatterHardeningTests.test_empty_flow_items_and_sequence_indicator_are_invalid` |
| 105–108 | Regression: `FrontmatterHardeningTests.test_top_level_comments_do_not_split_a_metadata_mapping` |
| 110–118 | Regression: `FrontmatterHardeningTests.test_flow_delimiters_require_quoted_items` |
| 120–123 | Regression: `FrontmatterHardeningTests.test_literal_scalar_preserves_indentation_and_comments` |
| 125–128 | Regression: `FrontmatterHardeningTests.test_folded_scalar_preserves_paragraph_break` |
| 130–132 | Regression: `FrontmatterHardeningTests.test_block_scalar_cannot_silently_change_uneven_indentation` |
| 134–143 | Regression: `FrontmatterHardeningTests.test_supported_block_tool_list_is_not_flattened_with_dashes` |
| 145–147 | Regression: `FrontmatterHardeningTests.test_simple_metadata_string_map_passes_portable` |
| 149–154 | Regression: `FrontmatterHardeningTests.test_metadata_nonstring_value_is_not_silently_stringified` |
| 156–158 | Regression: `FrontmatterHardeningTests.test_scalar_metadata_is_not_a_valid_map` |
| 160–174 | Regression: `FrontmatterHardeningTests.test_invalid_or_unsupported_yaml_cannot_pass_validation` |
| 176–179 | Regression: `FrontmatterHardeningTests.test_missing_description_is_warning_for_claude` |
| 181–184 | Regression: `FrontmatterHardeningTests.test_empty_frontmatter_still_requires_portable_fields` |
| 186–190 | Regression: `FrontmatterHardeningTests.test_nonstring_routing_fields_are_rejected` |
| 192–193 | Regression: `FrontmatterHardeningTests.test_quoted_numeric_description_is_a_string` |
| 195–197 | Regression: `FrontmatterHardeningTests.test_portable_description_limit_is_1024` |
| 199–201 | Regression: `FrontmatterHardeningTests.test_description_limit_includes_quoted_whitespace` |
| 203–207 | Regression: `FrontmatterHardeningTests.test_portable_name_constraints_and_directory_match` |
| 209–211 | Regression: `FrontmatterHardeningTests.test_portable_unicode_lowercase_name_matches_directory` |
| 213–227 | Regression: `FrontmatterHardeningTests.test_portable_relative_and_absolute_paths_match_the_same_directory` |
| 229–231 | Regression: `FrontmatterHardeningTests.test_portable_compatibility_limit_is_error` |
| 233–238 | Regression: `FrontmatterHardeningTests.test_invalid_utf8_is_an_unreadable_file` |

### tests/test_production_edges.py

| Рядки | Scope / перевірка |
| --- | --- |
| 17–67 | Клас unittest: `TypedFrontmatterEdgeTests` |
| 18–25 | Допоміжний метод/fixture: `TypedFrontmatterEdgeTests.skill` |
| 27–33 | Regression: `TypedFrontmatterEdgeTests.test_collection_cannot_become_a_string_via_plain_continuation` |
| 35–39 | Regression: `TypedFrontmatterEdgeTests.test_collection_comments_do_not_erase_type_evidence` |
| 41–45 | Regression: `TypedFrontmatterEdgeTests.test_metadata_boolean_and_null_keys_are_not_string_keys` |
| 47–52 | Regression: `TypedFrontmatterEdgeTests.test_quoted_boolean_and_null_metadata_keys_remain_strings` |
| 54–59 | Regression: `TypedFrontmatterEdgeTests.test_boolean_collections_are_flagged_and_do_not_hide_the_skill` |
| 61–67 | Regression: `TypedFrontmatterEdgeTests.test_folded_keep_chomping_preserves_trailing_blank_lines` |
| 70–347 | Клас unittest: `OperationalSourceBoundaryTests` |
| 71–77 | Допоміжний метод/fixture: `OperationalSourceBoundaryTests.setUp` |
| 79–80 | Допоміжний метод/fixture: `OperationalSourceBoundaryTests.tearDown` |
| 82–90 | Допоміжний метод/fixture: `OperationalSourceBoundaryTests.cli` |
| 92–97 | Regression: `OperationalSourceBoundaryTests.test_missing_explicit_transcript_directory_is_an_operational_failure` |
| 99–103 | Regression: `OperationalSourceBoundaryTests.test_file_is_not_an_explicit_transcript_directory` |
| 105–109 | Regression: `OperationalSourceBoundaryTests.test_no_usage_does_not_require_an_explicit_transcript_path` |
| 111–115 | Regression: `OperationalSourceBoundaryTests.test_operational_error_paths_cannot_emit_terminal_controls` |
| 117–129 | Regression: `OperationalSourceBoundaryTests.test_c1_controls_cannot_escape_reports_or_diagnostics` |
| 131–135 | Regression: `OperationalSourceBoundaryTests.test_argparse_errors_cannot_emit_terminal_controls` |
| 137–147 | Regression: `OperationalSourceBoundaryTests.test_svg_status_path_cannot_emit_terminal_controls` |
| 149–175 | Regression: `OperationalSourceBoundaryTests.test_svg_status_is_safe_when_the_filesystem_accepts_a_control_path` |
| 156–159 | Допоміжний метод/fixture: `OperationalSourceBoundaryTests.test_svg_status_is_safe_when_the_filesystem_accepts_a_control_path.resolve` |
| 161–162 | Допоміжний метод/fixture: `OperationalSourceBoundaryTests.test_svg_status_is_safe_when_the_filesystem_accepts_a_control_path.exists` |
| 164–165 | Допоміжний метод/fixture: `OperationalSourceBoundaryTests.test_svg_status_is_safe_when_the_filesystem_accepts_a_control_path.write_text` |
| 177–183 | Regression: `OperationalSourceBoundaryTests.test_svg_cannot_overwrite_an_audited_skill` |
| 185–194 | Regression: `OperationalSourceBoundaryTests.test_svg_cannot_overwrite_a_hardlinked_audited_skill` |
| 196–206 | Допоміжний метод/fixture: `OperationalSourceBoundaryTests.deny_scandir` |
| 201–204 | Допоміжний метод/fixture: `OperationalSourceBoundaryTests.deny_scandir.guarded` |
| 208–218 | Regression: `OperationalSourceBoundaryTests.test_recursive_inventory_failure_cannot_report_a_clean_partial_library` |
| 220–225 | Regression: `OperationalSourceBoundaryTests.test_shallow_inventory_surfaces_denied_skill_directory` |
| 227–242 | Regression: `OperationalSourceBoundaryTests.test_plugin_skill_inventory_surfaces_denied_component_directory` |
| 244–257 | Regression: `OperationalSourceBoundaryTests.test_plugin_command_inventory_surfaces_denied_nested_directory` |
| 259–266 | Regression: `OperationalSourceBoundaryTests.test_local_command_inventory_surfaces_denied_nested_directory` |
| 268–269 | Regression: `OperationalSourceBoundaryTests.test_absent_optional_commands_directory_stays_empty` |
| 271–280 | Допоміжний метод/fixture: `OperationalSourceBoundaryTests.directory_link` |
| 282–296 | Regression: `OperationalSourceBoundaryTests.test_recursive_inventory_does_not_follow_child_directory_links` |
| 298–308 | Regression: `OperationalSourceBoundaryTests.test_recursive_directory_link_cycle_terminates_without_duplicate_inventory` |
| 310–318 | Regression: `OperationalSourceBoundaryTests.test_bundle_footprint_does_not_count_directory_link_cycles` |
| 320–327 | Regression: `OperationalSourceBoundaryTests.test_bundle_footprint_excludes_files_behind_child_directory_links` |
| 329–347 | Regression: `OperationalSourceBoundaryTests.test_discovered_path_resolution_loop_is_an_operational_failure` |
| 332–337 | Допоміжний метод/fixture: `OperationalSourceBoundaryTests.test_discovered_path_resolution_loop_is_an_operational_failure.resolve` |
| 350–351 | Module entry point |

### tests/test_skill_bundle.py

| Рядки | Scope / перевірка |
| --- | --- |
| 23–185 | Клас unittest: `SkillBundleTests` |
| 24–27 | Допоміжний метод/fixture: `SkillBundleTests.setUp` |
| 29–35 | Допоміжний метод/fixture: `SkillBundleTests.builder_module` |
| 37–41 | Допоміжний метод/fixture: `SkillBundleTests.run_builder` |
| 43–49 | Regression: `SkillBundleTests.test_builder_cli_works_outside_the_checkout` |
| 51–73 | Regression: `SkillBundleTests.test_archive_resources_have_one_root_and_complete_checksums` |
| 75–106 | Regression: `SkillBundleTests.test_archives_are_byte_deterministic_and_exclude_repository_noise` |
| 108–134 | Regression: `SkillBundleTests.test_extracted_local_cli_audits_real_files_outside_the_checkout` |
| 136–147 | Regression: `SkillBundleTests.test_both_extracted_skill_frontmatters_are_portable` |
| 149–178 | Regression: `SkillBundleTests.test_symlink_or_junction_resource_is_rejected_instead_of_embedded` |
| 180–185 | Regression: `SkillBundleTests.test_unknown_profile_is_rejected_without_an_archive` |

### tests/test_skillrot.py

| Рядки | Scope / перевірка |
| --- | --- |
| 17–22 | Допоміжний метод/fixture: `run_cli` |
| 25–30 | Допоміжний метод/fixture: `write_skill` |
| 45–81 | Клас unittest: `FrontmatterTests` |
| 46–51 | Regression: `FrontmatterTests.test_parses_scalars_and_body` |
| 53–57 | Regression: `FrontmatterTests.test_leading_blank_line_breaks_frontmatter` |
| 59–62 | Regression: `FrontmatterTests.test_missing_frontmatter` |
| 64–66 | Regression: `FrontmatterTests.test_unterminated_frontmatter` |
| 68–71 | Regression: `FrontmatterTests.test_folded_block_scalar` |
| 73–77 | Regression: `FrontmatterTests.test_nested_map_captured_as_key` |
| 79–81 | Regression: `FrontmatterTests.test_quotes_stripped` |
| 84–200 | Клас unittest: `RuleTests` |
| 85–87 | Допоміжний метод/fixture: `RuleTests.setUp` |
| 89–90 | Допоміжний метод/fixture: `RuleTests.tearDown` |
| 92–95 | Допоміжний метод/fixture: `RuleTests.rules_for` |
| 97–100 | Regression: `RuleTests.test_clean_skill_has_no_errors` |
| 102–103 | Regression: `RuleTests.test_sr001_frontmatter_not_first_line` |
| 105–106 | Regression: `RuleTests.test_sr002_missing_description` |
| 108–111 | Regression: `RuleTests.test_sr003_listing_cap` |
| 113–117 | Regression: `RuleTests.test_sr003_counts_when_to_use_toward_the_cap` |
| 119–122 | Regression: `RuleTests.test_sr004_unreachable_skill` |
| 124–127 | Regression: `RuleTests.test_sr004_not_raised_when_only_one_is_set` |
| 129–134 | Regression: `RuleTests.test_boolean_synonyms_accepted` |
| 136–139 | Regression: `RuleTests.test_sr005_invalid_boolean` |
| 141–143 | Regression: `RuleTests.test_sr022_description_without_trigger` |
| 145–146 | Regression: `RuleTests.test_sr022_silent_when_trigger_present` |
| 148–151 | Regression: `RuleTests.test_sr023_oversized_body` |
| 153–154 | Regression: `RuleTests.test_sr025_thin_description` |
| 156–160 | Regression: `RuleTests.test_sr010_portable_rejects_extra_fields` |
| 162–165 | Regression: `RuleTests.test_sr011_compatibility_cap` |
| 167–169 | Regression: `RuleTests.test_sr012_unknown_field` |
| 171–175 | Regression: `RuleTests.test_sr020_duplicate_command_names` |
| 177–185 | Regression: `RuleTests.test_sr021_near_duplicate_descriptions` |
| 187–193 | Regression: `RuleTests.test_sr021_ignores_distinct_descriptions` |
| 195–200 | Regression: `RuleTests.test_sr024_never_fired` |
| 203–224 | Клас unittest: `UsageTests` |
| 204–214 | Regression: `UsageTests.test_counts_skill_invocations_in_transcripts` |
| 216–217 | Regression: `UsageTests.test_missing_transcript_dir_is_not_an_error` |
| 219–224 | Regression: `UsageTests.test_resolve_usage_falls_back_to_bare_name` |
| 227–253 | Клас unittest: `BudgetTests` |
| 228–233 | Regression: `BudgetTests.test_listing_cost_is_capped_at_the_spec_limit` |
| 235–249 | Regression: `BudgetTests.test_totals_add_up` |
| 251–253 | Regression: `BudgetTests.test_zero_context_window_does_not_divide_by_zero` |
| 256–307 | Клас unittest: `DiscoveryTests` |
| 257–268 | Regression: `DiscoveryTests.test_plugin_command_is_namespaced_from_manifest` |
| 270–275 | Regression: `DiscoveryTests.test_plugin_name_falls_back_past_a_version_directory` |
| 277–283 | Regression: `DiscoveryTests.test_frontmatter_name_sets_the_plugin_command_leaf` |
| 285–289 | Regression: `DiscoveryTests.test_same_skill_is_not_counted_twice` |
| 291–294 | Regression: `DiscoveryTests.test_a_direct_file_path_is_accepted` |
| 296–307 | Regression: `DiscoveryTests.test_relative_path_still_yields_a_command_name` |
| 310–354 | Клас unittest: `CliTests` |
| 311–314 | Допоміжний метод/fixture: `CliTests.setUp` |
| 316–317 | Допоміжний метод/fixture: `CliTests.tearDown` |
| 319–324 | Regression: `CliTests.test_json_output_is_valid` |
| 326–329 | Regression: `CliTests.test_exit_zero_on_clean_library` |
| 331–334 | Regression: `CliTests.test_fail_on_error_exits_nonzero` |
| 336–343 | Regression: `CliTests.test_fail_over_budget_exits_nonzero_only_when_over` |
| 345–346 | Regression: `CliTests.test_missing_path_exits_two` |
| 348–354 | Regression: `CliTests.test_render_is_plain_text_without_color` |
| 357–395 | Клас unittest: `ClusterTests` |
| 358–361 | Допоміжний метод/fixture: `ClusterTests.make` |
| 363–368 | Regression: `ClusterTests.test_identical_descriptions_form_one_cluster` |
| 370–375 | Regression: `ClusterTests.test_distinct_descriptions_do_not_cluster` |
| 377–385 | Regression: `ClusterTests.test_separate_duplicate_pairs_stay_separate` |
| 387–388 | Regression: `ClusterTests.test_single_skill_library_has_no_clusters` |
| 390–395 | Regression: `ClusterTests.test_one_finding_per_cluster_not_per_pair` |
| 398–411 | Клас unittest: `SymlinkStubTests` |
| 399–400 | Regression: `SymlinkStubTests.test_detects_a_path_only_file` |
| 402–404 | Regression: `SymlinkStubTests.test_ignores_real_markdown` |
| 406–411 | Regression: `SymlinkStubTests.test_reported_as_sr008_not_sr001` |
| 414–433 | Клас unittest: `RenderLimitTests` |
| 415–420 | Допоміжний метод/fixture: `RenderLimitTests.setUp` |
| 422–423 | Допоміжний метод/fixture: `RenderLimitTests.tearDown` |
| 425–433 | Regression: `RenderLimitTests.test_findings_are_capped_per_rule` |
| 436–454 | Клас unittest: `FoldedScalarTests` |
| 437–444 | Regression: `FoldedScalarTests.test_plain_scalar_folds_indented_continuations` |
| 446–454 | Regression: `FoldedScalarTests.test_folded_description_is_seen_by_the_trigger_rule` |
| 457–464 | Клас unittest: `TriggerSourceTests` |
| 458–464 | Regression: `TriggerSourceTests.test_sr022_silent_when_trigger_is_in_when_to_use` |
| 467–500 | Клас unittest: `ListingBudgetTests` |
| 468–471 | Допоміжний метод/fixture: `ListingBudgetTests.make` |
| 473–480 | Regression: `ListingBudgetTests.test_names_are_always_counted_even_over_budget` |
| 482–487 | Regression: `ListingBudgetTests.test_name_only_skills_reported_as_sr030` |
| 489–492 | Regression: `ListingBudgetTests.test_no_sr030_when_everything_fits` |
| 494–500 | Regression: `ListingBudgetTests.test_most_used_descriptions_survive_the_budget` |
| 503–515 | Клас unittest: `BundleBytesTests` |
| 504–515 | Regression: `BundleBytesTests.test_nested_skill_is_not_counted_in_parent_bundle` |
| 518–530 | Клас unittest: `CommandNameTests` |
| 519–523 | Regression: `CommandNameTests.test_frontmatter_name_beats_directory_for_local_skills` |
| 525–530 | Regression: `CommandNameTests.test_same_name_in_two_dirs_is_a_command_collision` |
| 533–542 | Клас unittest: `ShallowDiscoveryTests` |
| 534–542 | Regression: `ShallowDiscoveryTests.test_shallow_root_scans_one_level_only` |
| 545–603 | Клас unittest: `ManifestDiscoveryTests` |
| 546–560 | Допоміжний метод/fixture: `ManifestDiscoveryTests.make_marketplace` |
| 562–567 | Regression: `ManifestDiscoveryTests.test_marketplace_counts_only_what_the_manifest_installs` |
| 569–572 | Regression: `ManifestDiscoveryTests.test_scan_all_still_counts_every_skill_md` |
| 574–586 | Regression: `ManifestDiscoveryTests.test_root_plugin_counts_when_marketplace_source_is_remote` |
| 588–595 | Regression: `ManifestDiscoveryTests.test_remote_only_marketplace_does_not_count_local_catalog` |
| 597–603 | Regression: `ManifestDiscoveryTests.test_plugin_root_skill_md_loads_as_single_skill` |
| 606–652 | Клас unittest: `CommandFileTests` |
| 607–612 | Допоміжний метод/fixture: `CommandFileTests.make_plugin` |
| 614–618 | Regression: `CommandFileTests.test_plugin_commands_join_the_listing` |
| 620–627 | Regression: `CommandFileTests.test_manifest_commands_key_replaces_the_default_folder` |
| 629–636 | Regression: `CommandFileTests.test_local_command_names_follow_the_path` |
| 638–642 | Regression: `CommandFileTests.test_command_without_frontmatter_is_not_an_error` |
| 644–652 | Regression: `CommandFileTests.test_skill_and_command_with_one_name_list_once` |
| 655–681 | Клас unittest: `ListingVisibilityTests` |
| 656–660 | Допоміжний метод/fixture: `ListingVisibilityTests.make` |
| 662–667 | Regression: `ListingVisibilityTests.test_disable_model_invocation_is_not_billed` |
| 669–676 | Regression: `ListingVisibilityTests.test_overrides_off_and_name_only` |
| 678–681 | Regression: `ListingVisibilityTests.test_missing_description_falls_back_to_first_body_line` |
| 684–727 | Клас unittest: `InstalledPluginTests` |
| 685–708 | Regression: `InstalledPluginTests.test_enabled_plugins_resolve_through_cache_and_directory_marketplaces` |
| 710–711 | Regression: `InstalledPluginTests.test_no_enabled_plugins_does_not_scan_disabled_cache` |
| 713–727 | Regression: `InstalledPluginTests.test_settings_merge_project_over_user` |
| 730–736 | Клас unittest: `TypedCommandUsageTests` |
| 731–736 | Regression: `TypedCommandUsageTests.test_user_typed_slash_commands_count_as_invocations` |
| 739–747 | Клас unittest: `SvgTests` |
| 740–747 | Regression: `SvgTests.test_svg_is_well_formed_xml` |

## Підсумок реалізованої доставки: нові файли й змінені блоки

Початкові findings вище залишені як знімок проблем, від яких починалася робота.
Після реалізації існує окремий builder Agent Skill, два wrappers і сім delivery
regressions. Фінальний номер версії та інтеграційні результати фіксує
`RELEASE.md`; початковий hash не слід сприймати як hash фінального ядра.

### scripts/build_skill_bundle.py — 144 рядки

| Рядки | Поведінка та причина |
| --- | --- |
| 1–9 | Опис local/Agensi команд; future annotations для Python 3.9 |
| 11–21 | Лише standard-library imports; немає network client або package installer |
| 24 | ROOT походить від фізичного шляху builder, а не shell cwd |
| 25–43 | Короткий README local archive: unpack, Python, absolute paths, Claude model, privacy, hashes |
| 44–57 | Явний allowlist. Local: SKILL/CLI/rules/license. Agensi: wrapper/readme/rules/license. Рекурсивний repository scan не визначає payload |
| 60–69 | `_read_text`: перевіряє root та кожен component через lstat; забороняє symlinks і Windows reparse points/junctions |
| 70–77 | Resolved containment, UTF-8 reading/universal-newline normalization, відхилення NUL, повернення canonical UTF-8 bytes |
| 80–90 | `_version`: AST читає тільки string literal assignment `__version__`; module не import/execute; безпечний filename pattern |
| 93–101 | `build_bundle(output_dir, profile)` відхиляє невідомий profile, читає version/resources, додає короткий local README |
| 102–107 | Sorted manifest schema 1, name/version/profile, SHA256 й byte size кожного resource; manifest виключений з власного hash list |
| 108–113 | Створює явно заданий output dir і temp file в ньому; визначає versioned archive filename |
| 114–121 | ZIP_STORED: уникнення залежності від compression library; sorted members, один `skillrot/` root, timestamp 1980-01-01, Unix regular-file mode 0644 |
| 122–126 | Atomic replacement готового ZIP; finally прибирає тільки власний temp file; повертає Path artifact |
| 129–140 | CLI choices local/agensi, output default dist; clean operational exit 2, ASCII-safe errors/path output |
| 143–144 | Entry point SystemExit(main()) |

Пакет стабільний побітово для однакових canonical resource bytes і version/profile.
Зміна mtime або LF/CRLF checkout не змінює архів. Він не є secrets scanner: allowlist
виключає undeclared `.env`, Git, приватні JSON, caches, старі archives і media, але не
дає магічної гарантії, якщо secret вручну внесено в дозволений source file.
SHA256 manifest перевіряє цілісність ресурсів і не є підписом або доказом автора.
Archive content не виконується при збірці.

### tests/test_skill_bundle.py — 189 рядків

Imports/ROOT/BUILDER 1–20; unittest class 23–185; entry point 188–189. Індекс усіх
методів наведено вище. Сім regression contracts:

1. Builder запускається поза checkout і створює один versioned ZIP.
2. Обидва profiles містять рівно потрібні ресурси під одним root; manifest має точні
   SHA256 і розміри, обчислені незалежно тестом із реально прочитаних member bytes.
3. Реальні шумові файли не потрапляють до payload; changed mtimes і CRLF serialization
   не змінюють ZIP; timestamps і modes фіксовані.
4. Local ZIP extract у Unicode/space path; реальний enclosed CLI аудіює інший fixture
   поза source checkout, повертає JSON schema/version й валідний результат.
5. Обидва extracted `SKILL.md` проходять supported portable validation з directory match.
6. Symlink source або, на Windows без відповідного privilege, реальний directory
   junction відхиляється, а не вбудовується в artifact.
7. Невідомий profile дає exit 2 без artifact і traceback.

RED був зафіксований до builder: test_builder_cli_works_outside_the_checkout дав
`2 != 0`, бо bundle command ще не існував. Після реалізації усі сім tests проходять
на Windows; junction fallback забезпечив реальну link-boundary перевірку без skip.
Це перевірка доставленого CLI й структури wrapper, не live MCP/agent activation test.

### Фінальні wrappers і workflow

| Файл / рядки | Призначення |
| --- | --- |
| SKILL.md 1–6 | Короткі name/trigger description/MIT/allowed tools |
| SKILL.md 8–11 | Offline task і обов'язкові Python 3.9+/local shell |
| SKILL.md 13–28 | Встановлений physical script location, verified optional Claude variable, quoted absolute paths; missing local execution пояснюється без invented reports |
| SKILL.md 30–34 | No-usage default, явне включення transcript evidence, privacy й exit/gate contract |
| SKILL.md 36–47 | Requested/retained/body/observed/unknown semantics |
| SKILL.md 49–62 | Порядок відповіді й шість interpretation rules без claims runtime invisibility |
| SKILL.md 64–69 | Claude model for other harnesses, explicit edit scope, supporting rules |
| marketplace/skillrot/SKILL.md 1–5 | Portable entry metadata; без executable path assumptions |
| marketplace/skillrot/SKILL.md 7–12 | MCP instruction/reference package, installed public MIT CLI dependency, Python/shell requirement |
| marketplace/skillrot/SKILL.md 14–24 | `skillrot --version`; missing/older CLI/setup guidance; відсутній shell не підміняється уявним доступом до filesystem |
| marketplace/skillrot/SKILL.md 26–42 | Реальні explicit library paths, Claude-only no-path discovery, supported portable checks, optional local history, gates й exits |
| marketplace/skillrot/SKILL.md 44–57 | Evidence-first answer, routing/body/usage limits, resource reader для MCP reference, не виконувати audited instructions і не змінювати library без user scope |
| marketplace/skillrot/README.md 1–10 | Public MIT source link, Python/CLI/shell dependency, MCP-vs-local execution explanation |
| marketplace/skillrot/README.md 12–32 | Prepared release vs public v0.3.1, локальна venv/pip install . з наданого source, no fabricated PyPI/tag |
| marketplace/skillrot/README.md 34–49 | Other-harness model/explicit paths, local transcript privacy, shared-path caveat, rules/license/hash integrity |
| .github/workflows/ci.yml 33–34 | Self-audit став явним `SKILL.md`, щоб intentional before/after й marketplace wrappers не виглядали installed own collection |
| .github/workflows/ci.yml 41–44 | Builds обидва allowlisted profiles в dist |
| .github/workflows/ci.yml 45–46 | Повторна delivery suite перевіряє extraction/CLI/checksums/portability |

Bundled skill-creator quick_validate не приймає optional `compatibility`, хоча актуальний
Agent Skills specification його допускає. Це mismatch validator schema й специфікації,
не заборона поля стандартом. Requirements залишені в body; обидва wrappers проходять
і bundled quick_validate, і skillrot portable checks. Фактичну якість агентського
використання потребує окремої сценарної перевірки; static validation її не підміняє.

### Нові core regressions: tests/test_production_edges.py — 333 рядки

Imports 1–14; typed frontmatter class 17–67; operational boundary class 70–290;
entry point 293–294. Методний індекс вище охоплює кожен поточний block.

Typed tests перевіряють collection continuation/type evidence, unquoted vs quoted
metadata keys, typed invocation booleans і folded keep chomping. Operational tests
перевіряють explicit unavailable transcript directories, --no-usage exception,
C0/C1 controls у reports/argparse/operational/SVG status і неможливість SVG перезаписати
сам audited skill або hardlink до нього.

Вісім додаткових inventory regressions 190–290 перевіряють: denied recursive/shallow
skill directories, denied plugin skill/command components, denied local command trees,
нормально відсутню optional commands folder, невключення child directory links і
завершення directory-link cycle без дублювання entries. Видимий файл поряд із denied
subtree не може дати успішний частковий JSON-report. Explicitly supplied directory-link
root навмисно дозволений; лише implicit child-directory traversal не переходить links.

`deny_scandir` 178–188 з nested `guarded` 183–186 підміняє тільки filesystem enumeration
boundary; справжній directory layout, discovery/parser/CLI/report streams залишаються
реальними. `directory_link` 253–262 створює temp symlink або Windows junction fallback;
cycle termination test 280–290 запускає реальний subprocess з timeout 5 секунд.

Є expected Windows skip 137–147 для справжнього filename із control characters,
які NTFS не дозволяє; narrow write boundary double 149–157 перевіряє саме статусне
повідомлення на Windows. Fresh source suite має 213 tests, один цей expected skip.
Algorithm corrections і strict inventory helper пояснює core-звіт фінального 2064-line
ядра; ці тести не видаються за експерименти з live Claude loader.

### Генератор атласу: scripts/source_atlas.py — 208 рядків

| Рядки | Поведінка |
| --- | --- |
| 1–7 | Purpose/docstring, standard-library/no inspected execution contract, future annotations |
| 9–15 | argparse/AST/hashes/HTML/JSON/Path/typing imports |
| 18–20 | Python/TOML/YAML/HTML/manifest suffixes; excludes Git/venvs/development outputs і mypy/ruff/pytest caches |
| 23–28 | `expression`: AST unparse із fallback та обмеженням annotation string до 180 chars |
| 31–83 | `explain`: українські структурні описання function/class/import/assign/control-flow/return/raise/assert/docstring/loops/delete; fallback AST type |
| 86–99 | `python_lines`: AST walk, lineno/end_lineno; для вкладених statements обирає найменший span, найближчий до рядка |
| 102–115 | `annotate`: blank/comment/decorator/else/finally/Python description або continuation fallback |
| 116–129 | TOML/YAML structural descriptions; не виконує shell чи GitHub Actions semantics |
| 130–131 | Setuptools manifest structural annotation |
| 132–133 | Правильне пояснення suffixless `.gitignore` patterns як виключень tracking; попередній HTML fallback виправлений |
| 134–138 | HTML/style/script heuristic annotation, яке відсилає до ручного demo analysis |
| 141–155 | `generate`: sorted source traversal, включає `.gitignore`, skips caches/generated audit dirs, UTF-8 reads, exact SHA256/byte/line inventory; inspected module не імпортується |
| 156–162 | Escaped source/description у HTML rows зі file/line IDs, collapsible tables |
| 163–166 | Output directory й source-inventory.json schema 1/files/counts |
| 167–176 | HTML/CSS local standalone document; fixed table layout і окремий overflow довгих code lines залишають пояснення видимими |
| 177–185 | Українська metadata/context, explanation caveats, query input/expand/collapse controls |
| 186–192 | Local JS case-insensitive block search та expand/collapse; без network calls |
| 193–195 | Вставляє counts/sections, пише SOURCE_ATLAS.html, друкує inventory summary |
| 198–204 | CLI --root/--output; за замовчуванням repository root і docs/audit |
| 207–208 | Entry point main |

Автоматичні AST-анотації пояснюють **синтаксичну роль** кожного рядка, а не доводять
семантичну правильність, безпеку чи runtime сумісність. Для багаторядкових виразів
пояснення може повторюватись; YAML/HTML annotations є heuristics для навігації.
Обґрунтування рішень, algorithm invariants і gaps містяться в ручних core/delivery
reports, а correctness evidence — у regressions/build/extraction checks. Inventory
містить SHA256 саме source snapshot; після code changes його слід регенерувати.

SHA256 фінального генератора:
`3575ca5a365f225a83f809269e744c4c8753fb490115add38c4c0610ed02a527`.
Root перевірив rendered browser search/expand і видимість explanation column; це
UI acceptance цього generated document, а не додатковий доказ correctness CLI.

## Завершення source distribution і фінальні допоміжні контракти

### MANIFEST.in — 12 рядків

| Рядок | Ефект |
| --- | --- |
| 1 | Включає root skill, LICENSE, changelog, contributing і security policy до sdist |
| 2 | Включає rules, потрібні обом delivery profiles |
| 3 | Включає Python development scripts, зокрема builder/smoke/source atlas |
| 4 | Включає marketplace Markdown inputs |
| 5 | Включає Python tests; вони мають працювати з extracted source tree |
| 6 | Виключає Python bytecode/cache files за extension |
| 7 | Не включає presentation binaries docs/assets |
| 8 | Не включає generated source atlas docs/audit |

Це source-distribution policy, не runtime dependency list. Wheel і далі є single-module
CLI. Окремі local/Agensi ZIP мають ще вужчий resource allowlist. Вихідний sdist без
цих inputs міг збирати wheel, але не міг виконати нову archive regression suite; тепер
це перевіряється реальним unpack/run/build у package smoke, а не припущенням.

### scripts/smoke_package.py — фінальні 218 рядків

Початкові 161 рядок пояснені вище як baseline. Нижче точна карта остаточної версії:

| Рядки | Поведінка |
| --- | --- |
| 1–9 | Docstring і future annotations |
| 11–22 | Standard-library imports; додані sys для same-interpreter execution і tarfile для sdist |
| 25–30 | InstalledPackageTests class metadata |
| 32–62 | Setup: exactly one wheel/sdist, version/dependency/license checks, temp venv, offline wheel installation, fixture |
| 64–71 | Static write_skill fixture |
| 73–81 | Sanitized subprocess env, installed launcher, cwd/timeout/encoding |
| 83–86 | Exit/traceback assertions |
| 88–94 | Installed version/help |
| 96–107 | Clean JSON schema/model contract |
| 109–113 | SVG XML |
| 115–124 | Finding/budget gates |
| 126–131 | Missing/partial input operational failure |
| 133–136 | SVG write operational failure |
| 138–143 | Numeric argument errors |
| 145–150 | Unicode path through cp1251 output |
| 153–154 | SourceDistributionTests class; uses same resolved dist dir |
| 156–170 | Exactly one sdist, temp workspace, single archive root, six required delivery inputs explicitly checked |
| 171–183 | Checks resolved member containment and rejects links; extracts directories and regular files manually, closing extracted handles |
| 184–190 | Sanitizes inherited import/budget environment; runs all included tests through current Python outside original checkout with timeout120 |
| 191–203 | Executes builder for each profile from extracted source; exactly one ZIP per profile, correct manifest profile і skill entry |
| 206–214 | CLI parser, resolved dist shared by both test classes; combines8 installed tests й1 sdist test, returns suite result |
| 217–218 | Entry point SystemExit(main()) |

Новий sdist test запускає **реальні** extracted inputs, не mocked file existence.
Це дев'ятий smoke case; результати final clean build/root verification записуються в
RELEASE.md. Раніші8-test baseline результати не слід підміняти ними.

### Фінальна документація release preparation

| Файл / діапазон | Вміст |
| --- | --- |
| README.md 1–17 | Поточна0.4.0 preparation, public0.3.1 й readiness link |
| README.md 18–43 | Source/публічний pinned install, мінімальні prerequisites |
| README.md 44–84 | Ручний local install, verified ZIP build/extraction, відокремлений Agensi MCP profile |
| README.md 85–105 | Estimates requested/retained/body й practical library review |
| README.md 106–160 | CLI examples, manifest/discovery/settings profiles, other-harness limits |
| README.md 161–185 | Tokenization assumptions, history null/zero, explicit --transcripts directory failure |
| README.md 186–223 | YAML subset/portable constraints/rule reference |
| README.md 224–262 | Exit/JSON/schema/CI; SVG не перезаписує discovered sources/hardlinks |
| README.md 263–275 | Static і host-specific alternatives |
| README.md 276–288 | Current controlled before/after й окремі historical assets |
| README.md 289–298 | Project reverse-engineering/research/launch/security і contributor links |
| CONTRIBUTING.md 1–17 | Single-file policy, tests, exact self-audit й typing |
| CONTRIBUTING.md 18–43 | Wheel/sdist smoke, included source suite і source-tree profile build |
| CONTRIBUTING.md 44–55 | Exit/schema/evidence compatibility |
| CONTRIBUTING.md 56–77 | Both ZIP build commands, source atlas, actual-vs-generated validation і release/publication boundaries |
| CHANGELOG.md 1–47 | Prepared0.4.0 changes, newer core/delivery fixes, prior uncommitted hardening й compatibility limits |
| CHANGELOG.md 48–54 | Public0.3.1/0.3.0 історія |
| SECURITY.md 1–26 | Static/offline scope, transcript/report privacy, filesystem/model limits, vulnerability reporting, preparation vs release |

Технічні сценарії, packaging і source atlas завершені локально. Реальні MCP activation,
Agensi account/review, відповідний public CLI release і нове remote CI підтвердження
залишаються окремими зовнішніми станами. Ні report, ні hashes не видають їх за виконані.

Фінально повторено в цій delivery-перевірці: 213 source tests на CPython 3.14.5 і 3.9.25,
0 failures, один очікуваний Windows filename skip; mypy 2.2.0 — 11 files, 0 issues; обидва
SKILL wrappers — portable audit без errors/warnings. Остаточні artifact hashes і smoke
results authoritative в RELEASE.md.


## Остаточне закриття integration review

Після попереднього snapshot 210 tests додано ще три відтворені regressions: точний
підрахунок bundle bytes за junction cycle та external supporting link, і controlled
RuntimeError на discovered path resolve. Кінцевий стан: 213 source tests, ядро
2064 рядки, SHA256 c73ec50a59708a1323fb32889de9dad3114d1093f76694688dd6eaad91fd842e.
Повний актуальний індекс цих тестів наведено вище; старі baseline observations
залишені історичними. Фінальні wheel/sdist і обидва ZIP незалежно перевірено;
9 package/source smoke checks проходять на Python 3.9.25 і 3.14.5.
Построковий atlas: 17 файлів, 5394 рядки, hashes і line counts перевірені.
Детальна acceptance evidence та зовнішні кроки публікації — RELEASE.md.


## Publication packaging update

The public release manifest additionally includes the release guide and controlled
examples/reports/charts in the sdist. These four additive manifest lines do not
change runtime behavior or the frozen CLI hash. Account screenshots, local preflight
notes and private planning records are excluded from the public commit.


## CI portability verification

The public matrix exposed two runtime-dependent test assumptions. The JSON
regression forces RecursionError only at the decoder boundary; a valid unused
deep JSON field is not required to fail parsing. The terminal-status fixture models
only its target filesystem consistently, including resolve/exists/write. Production
file protection, real filename/link tests and frozen CLI bytes are unchanged.
