# Реверс-інженерія ядра skillrot

Дата дослідження: 13 жовтня 2026 року. Прочитано весь `skillrot.py`, усі чотири файли тестів, поточні правила й метадані пакета. Аудит починався з робочої копії, яка вже мала незакомічені зміни; вони збережені. Це аналіз реальної реалізації, а не висновки лише з README.

Початковий знімок ядра: 1 980 фізичних рядків, версія `0.4.0.dev0`, SHA-256 `904182c260224f775044b0ff6caac3634b4ed98c22370b1d727542ddc01a685f`. Це збережений baseline для відтворення дефектів. Опис функцій, діапазони та построкова карта нижче оновлені до кінцевої реалізації; попередні баги окремо позначені як baseline.

## Що це за продукт і де його цінність

skillrot — локальний статичний аналізатор бібліотек Agent Skills із моделлю контекстного listing для Claude Code. Це CLI та імпортований Python-модуль; `SKILL.md` є оболонкою, через яку агент може запускати цей CLI. Ядро не є LLM-агентом, маршрутизатором, менеджером платежів, SaaS або інсталятором інших skills. Воно читає Markdown, frontmatter, локальні JSON settings/manifest/registry та, за бажанням, JSONL-історію викликів. На виході дає текстовий звіт, JSON і автономний SVG.

Основний користувач — розробник або власник великої бібліотеки skills. За десятків/сотень встановлених описів він отримує відповідь на конкретні питання: скільки контексту орієнтовно просить бібліотека; які описи можуть не поміститися; які навички приховані налаштуваннями; де дублюються command names; де описи надто схожі; які метадані не відповідають підтримуваному формату; для яких skills у доступних transcripts не знайдено викликів. Для автора бібліотеки додаткова цінність — `--portable` і CI gate.

Читання локальне. Ядро не робить HTTP-запитів, не відправляє skill-тексти чи transcripts зовнішнім сервісам, не запускає скриптів з audited skills і не редагує skills. Запис можливий лише для явно переданого `--svg`. Встановлення Python-пакета через pip є окремою операцією від запуску аналізатора.

Вартість токенів — оцінка `round(кількість_символів / chars_per_token)`, мінімум один токен для непорожнього тексту. Це не токенізація конкретної моделі та не грошовий рахунок провайдера. `SR021`, `SR022`, `SR023`, `SR025` — review heuristics. `SR030` — результат моделі обмеженого listing; інструмент не бачить реальний prompt поточної сесії. Нуль спостережених викликів не доводить, що skill зайвий. Ці обмеження є частиною чесного позиціонування продукту.

## Потік даних від запуску до результату

1. `main()` створює argparse parser, читає аргументи й перевіряє числові межі.
2. `_run_audit()` обирає явні paths або локальний профіль Claude Code. У default mode зливає user/project/local settings, визначає enabled plugins і додає legacy commands.
3. `discover()` читає manifests або сканує Markdown, прибирає повторні фізичні файли й паралельно викликає `load_skill()`.
4. `load_skill()` викликає обмежений YAML parser, визначає походження, namespace і command, зберігає тіло та розмір bundle.
5. Для default mode застосовуються local `skillOverrides`. Параметри listing беруться з CLI, settings та environment за визначеним пріоритетом.
6. `usage_counts()` структурно читає JSONL; `resolve_usage()` співвідносить точні й однозначні bare names із command names.
7. `budget()` рахує requested та retained listing costs. `analyze()` формує findings для окремих файлів і колекції.
8. `_run_audit()` за потреби записує SVG, друкує text/JSON і застосовує CI exit policy. `main()` перетворює operational errors у exit 2, а закритий stdout pipe — у нормальне завершення.

Архітектура послідовна: discovery → структурні дані → чисті функції оцінювання/правил → presentation. Один файл великий, але поточний розмір і zero-dependency delivery самі по собі не обґрунтовують переписування. Виявлені проблеми виправляються на межах parser/output із регресійними тестами.

## Розбір усіх класів, функцій і верхньорівневих блоків

### Рядки 1–94: контракт модуля, imports і параметри

Рядок 1 — Unix shebang; Windows використовує Python launcher/console entry point. 2–9 описують offline audit та Python 3.9+. 11 відкладає обчислення annotations: це дозволяє типізувати код без передчасного звернення до оголошених нижче об’єктів. 13–25 імпортують виключно standard library: argparse для CLI, fnmatch для hostcase patterns, stat для Windows reparse attributes, json для settings/transcripts/report, math для finite checks, os/sys для filesystem/environment/streams, re для синтаксису/heuristics, ThreadPoolExecutor для читання файлів, dataclasses для моделей, Path/PureWindowsPath для platform-neutral containment, typing для контрактів. 27 задає версію, яка має збігатися з `pyproject.toml`.

33–34 визначають caps 1536 і 500. 38–45 — шість portable fields; 48–66 — їх union із Claude-specific fields. 68–70 задають boolean fields і accepted spellings. 74–78 містять англомовні trigger cues. 80–89 задають default context 200000, body budget 500, similarity 0.8, chars/token 4, listing fraction 0.01. 91–94 задають stopwords. Ці числа не вимірюються автоматично на інстальованому host: вони є параметрами підтримуваної моделі й потребують актуальних source citations у `docs/RULES.md`.

### Рядки 96–107: `_KEY_RE`, `_FrontmatterValue`, `__new__`

Regex розпізнає top-level ключ як double-quoted, single-quoted або обмежений plain identifier, двокрапку й залишок значення. `_FrontmatterValue` наслідує `str`, тому зберігає публічний контракт `Dict[str, str]`, але додає `kind` і `members`. `__new__` створює рядок через superclass, прикріплює YAML-kind (`string`, `boolean`, `number`, `null`, `timestamp`, `sequence`, `mapping`) та первинні члени колекції. Це важлива відмінність від сліпого перетворення всіх YAML значень у strings: `description: true` не має мовчки пройти як рядок.

### Рядки 110–131: `_yaml_comment`

Функція відрізає відокремлений `# comment`, зберігаючи `#` усередині quoted scalar або flow-list item. Початковий quote визначає поточний режим; escape у double quotes пропускає наступний символ; doubled single quote пропускає обидва символи. Для flow sequence quote відкривається лише у позиції, подібній до початку item. Коментар починається лише на початку або після whitespace. Повернення робить `rstrip()` зовнішнього тексту. Це лексер підмножини YAML, не загальний YAML tokenizer.

### Рядки 134–197: `_strip_quotes`

134–137 видаляють зовнішній whitespace/comment та повертають plain text без обробки, якщо quotes не відкрилися. 138–144 готують таблицю стандартних YAML escape sequences і output buffer. 145–155 шукають закриття quote; doubled apostrophe стає одним apostrophe, а сторонній текст після закриття спричиняє ValueError. 156–183 обробляють double-quoted escapes: continuation backslash+newline склеює рядки; `x/u/U` вимагають точну довжину hex; surrogate range відкидається; звичайний escape мусить бути у таблиці. 184–193 складають multiline quoted text за YAML folding rules: одиничний newline стає space, порожні рядки залишають paragraph breaks. 194–196 додають звичайний символ і рухають cursor. 197 відхиляє незакриту quote.

### Рядки 200–254: `_yaml_scalar`

200–203 обробляють quoted scalar як typed string. 204–205 відхиляють anchors, aliases, tags, flow mappings, reserved syntax і lone sequence indicator. 206–242 розбирають flat `[a, b]`: bracket має закриватися; scanner зберігає quoting/escapes, comma завершує item, порожні внутрішні items і nested delimiters у plain item відхиляються, кожен item розбирається рекурсивно, після чого string rendering об’єднується spaces, а kind залишається `sequence`. Це дозволяє Claude tool-list forms без втрати знання, що вони не portable scalar.

243–244 не дозволяють plain `: `, бо це неоднозначна/invalid mapping syntax. 245–253 класифікують порожнє/null, booleans, numbers і timestamps; при цьому первинне текстове значення зберігається. 254 повертає typed string wrapper. Серед початкових дефектів — collection із multiline continuation могла бути пізніше перетворена у звичайний рядок у `parse_frontmatter()`; root cause лежить там, а не у цього scanner.

### Рядки 257–262: `_yaml_key`

Новий helper розбирає ключ через той самий typed scalar parser, вимагає kind string та повертає actual string key. Bare boolean/null-looking keys відхиляються як unsupported typed keys; quoted `"true"` і `"null"` лишаються валідними. Helper застосований до top-level та metadata mappings, тому string-key contract збережено до portable validation.

### Рядки 265–294: `_yaml_block`

266–270 знаходять indentation першого непорожнього child line, відхиляють subsequent content із меншим відступом та знімають спільний indentation. Для literal `|` 271–272 з’єднують рядки literal newlines. Для folded `>` 273–286 одиничні переходи між ordinary lines стають spaces; paragraph breaks і more-indented content лишаються newlines. 288–293 реалізують strip/clip/keep chomping, 294 повертає string wrapper. У baseline підтверджено крайовий дефект `>+` із trailing blank lines: keep chomping губив один newline. Тепер `last_content` відрізняє blank paragraph перед later content від trailing blank lines. Незалежна матриця 54 literal/folded strip/clip/keep cases збігається з PyYAML; runtime dependency не додано.

### Рядки 297–412: `parse_frontmatter`

297–305 задають контракт `(frontmatter, body, problems)` і прямо пояснюють supported YAML subset. 307–314 вимагають opening delimiter на first line; якщо його немає, знаходять misplaced delimiter у перших 20 lines або `no-frontmatter` й повертають весь input body. 316–323 знаходять unindented closing `---`/`...`; незакритий header лишається body з `unterminated-frontmatter`. 325–328 відокремлюють body і відхиляють literal YAML control characters. 329–348 пропускають blank/comments, зіставляють key regex, збирають indented/indentless-sequence children і фіксують source location.

349–355 перевіряють tabs, string-key types, дублікати keys і meaningful children. 356–357 передають block scalar у `_yaml_block`. 358–385 обробляють block collections: усі meaningful lines повинні мати однаковий indentation; sequence items повинні мати `- ` і не містити nested collections; mapping підтримується лише для `metadata`; mapping keys мають бути strings і не можуть повторюватись. 386–387 обробляють multiline quoted scalar. 388–407 отримують first typed value, відкидають sequence continuation, накопичують paragraphs/comments і зберігають literal plain-continuation text. У цьому блоці baseline collection kind міг загубитися; саме цей шлях дозволяв invalid multiline sequence пройти portable. 408–410 ловлять ValueError, додають SR009-compatible problem і відкидають весь metadata map, не залишаючи частково валідних полів. 412 повертає успішний map та body.

Parser зберігає лише підтримувану підмножину, навмисно fail-closed для unknown syntax. Valid host YAML outside subset може отримати SR009; це потрібно пояснювати в продукті. `splitlines()` також нормалізує різні line-break characters. Поточний map string-key contract у baseline не перевіряв YAML kinds для metadata keys `true/null`; потрібна typed-key validation, щоб дійсний string map не підмінявся text rendering.

### Рядки 417–467: `Skill` та шість properties

`Skill` — дані одного physical entry. `path/root` зберігають location, `origin` — personal/project/plugin/scanned/command, `command` — invocation name, `frontmatter/body/problems` — parse result, `plugin` — owner namespace, `bundle_bytes` — own file footprint, `kind` відрізняє skills від commands, `override` зберігає supported setting. `default_factory=list` запобігає спільному mutable problems між instances.

`description` (432–433) і `when_to_use` (436–437) дістають trimmed values. `routing_text` (440–449) при missing description бере first nonempty body line, знімає Markdown heading hashes і додає `when_to_use`; повне тіло не потрапляє в always-on listing. `in_listing` (452–458) виключає `off`, `user-invocable-only` та true disable-model-invocation. `listing_text` (461–463) формує human-readable `command: routing`; budget helpers рахує ім’я та description окремо. `body_lines` (466–467) рахує лише nonblank lines.

### Рядки 470–508: plugin inference та `_classify`

`_is_version_dir` (470–471) розпізнає optional-v версії для manifest-free cache inference. `_plugin_name_for` (474–491) піднімається від skill folder до ancestors; якщо знаходить `.claude-plugin/plugin.json`, строго читає/валідує його і вимагає name. Якщо manifest немає, дозволяє ownership inference лише для versioned `plugins/.../<version>/skills/...`. Самого generic folder `skills` недостатньо. `_classify` (494–508) нормалізує slash/case, шукає owner, тоді розрізняє plugin, home `.claude/skills`, project `.claude/skills` та scanned. Ідентичний текст skill поза configured profile залишається scanned: це запобігає вигаданому namespace для Cursor/Codex folders.

### Рядки 511–561: footprint, directory name й `Entry`

`_PRUNE_DIRS` прибирає `.git`, node_modules, pycache та venv. `_bundle_bytes` (514–547) виконує `os.walk`, не включає вкладений folder із власним `SKILL.md`, pruning застосовує до dirs in place, перед descent робить lstat children і відкидає symlink/Windows reparse dirs, потім сумує stat sizes доступних files; stat errors пропускає. Це кількість file bytes, не allocated disk sectors і не payload, що весь завантажиться в prompt. На дуже великих repositories traversal може бути повільним; resource ceilings відсутні. `_directory_name` (550–558) усуває `.`/`..` fallback через resolved parent. `Entry` (536) — `(Path, plugin|None, kind, command|None)` до читання file contents.

### Рядки 565–608: `load_skill`

573–579 читають UTF-8, перетворюють OSError/UnicodeError у synthetic unreadable Skill із SR007-compatible problem; це не мовчазне omission. 580 викликає parser. 581–594 підтримують legacy command files: missing frontmatter нормальне, path-derived command має перевагу над `name`, byte footprint — лише цей file. 595–603 визначають skill origin/owner, беруть frontmatter name або directory fallback та один раз додають plugin namespace. 604–608 створюють Skill і рахують own bundle. Audit не виконує Markdown instructions; input content є даними.

### Рядки 611–639: проектні roots і commands

`_project_dirs` (611–619) повертає cwd та parents до першого `.git` directory/file; поза git repo повертає тільки cwd. Це підтримує nested project scopes, але не є універсальним scanner усіх ancestor settings поза repository. `default_roots` (622–629) додає home Claude skills/plugins та project Claude skills, після чого лишає існуючі directories; alternative agent folders не вважаються автоматично інстальованими Claude skills. `command_entries` (632–639) рекурсивно знаходить `.md` legacy commands, формує colon-qualified command із relative path без suffix. Неприсутній command directory дає empty list.

### Рядки 642–756: operational errors, JSON і containment

`AuditError` (642–643) відрізняє operational input failure від finding severity. `_read_json` (683–696) відсутній optional file повертає як None; present invalid/unreadable/non-object input спричиняє AuditError, включно з nonfinite JSON constants і RecursionError. `_as_paths` (699–708) дозволяє string або array of strings та відкидає blank paths. `_within_root` (711–716) порівнює resolved paths, тому symlink/junction поза root не обходить containment. `_manifest_path` (719–726) до filesystem resolve перевіряє Windows drive/UNC syntax навіть на Unix, absolute syntax і `..`; лише relative local descendants можуть стати component/source path.

`_validate_plugin_manifest` (729–734) перевіряє name type/nonblank і shapes skills/commands. `_marketplace_entries` (737–756) вимагає plugins array із object entries, name/source, boolean strict та nonblank remote source type. Remote descriptor не означає автоматичний download. Контроль source/component paths — важливий security boundary для audit чужого checkout.

### Рядки 759–858: `_plugin_entries`, `manifest_skill_files`

`_plugin_entries` читає manifest. Наявність одночасно plugin.json та marketplace listing component extensions діагностує, бо supported profile не може чесно злити їх; strict:false conflicts теж operational errors. Name береться з manifest, explicit argument/entry або root fallback. Skills включають conventional `skills` plus explicit component directories, із one-level skill discovery або component folder власного SKILL.md. Missing explicit dirs — errors. Root SKILL.md fallback можливий лише коли немає explicit skills/conventional skills folder; docs mirrors не підтягуються випадково.

Commands manifest key замінює default `commands` folder, підтримує file/dir paths, рекурсивні `.md`, containment та plugin:path-qualified names. `manifest_skill_files` (830–858) незалежно перевіряє root plugin і marketplace; local string sources resolving within checkout додаються, remote sources пропускаються. Результат None означає «manifest layout не розпізнано» й дозволяє recursive scan; empty list означає «layout розпізнано, але немає local installable entries» і забороняє підмінити inventory документацією.

### Рядки 861–968: settings merge та enabled plugins

`_validate_settings` (861–880) задає supported override states; enabledPlugins/skillOverrides/env мають бути objects, plugin flags booleans, override strings known states, env values strings, listing fraction finite `(0,1]`. Configured max-description cap, відмінний від supported 1536, — явна profile limitation.

`load_settings` (883–898) читає user settings, від repository ancestor до nearest project додає project та local files; later scalar values win, dictionary values merge by key. Validator застосовується до кожного source, щоб invalid early layer не ховався під later valid override. `installed_plugin_entries` (901–968) не сканує disabled cache; enabled name@marketplace resolving робить через installed registry або known marketplace catalog. Shapes цих файлів перевіряються. Повторні records одного resolved root deduplicate; distinct roots повертають explicit scoped-profile limitation, бо автоматичний вибір scope тут не реалізований. Missing local enabled plugin — operational error; це не «чистий» неповний inventory.

### Рядки 971–1019: `discover`

Root-файл читається напряму як skill. Shallow installed root бере `*/SKILL.md`. Plugin/marketplace root використовує manifest result. Unknown root сканується recursive; `--all` змушує recursive SKILL.md scan й оминає manifest file selection. Plugin ownership manifests усе ще валідуються при classification. Recursive child directory symlinks/junctions пропускаються, explicit linked roots дозволені. File paths resolve та deduplicate незалежно від repeated roots або root+direct-file input. File loading I/O bound, тому ThreadPoolExecutor використовує до min(32, cpu*4, count) workers. `pool.map` зберігає discovery order: output детермінований навіть при parallel reads. Uncaught operational error з worker propagates до main.

### Рядки 1024–1088: usage evidence та matching

Regex `_TYPED_COMMAND_RE` розпізнає XML-like `<command-name>/name</command-name>`, а не будь-який slash у prose. `usage_counts` (1028–1071) читає доступні JSONL lines по одному, skips malformed JSON/records, знаходить root tool_use Skill або assistant content tool blocks, та user text commands. Tool results не скануються рекурсивно, тому foreign embedded transcript не стає invocation evidence. OSError окремого transcript пропускається. Імена з input перевіряються як nonblank strings. Дані зберігаються тільки як aggregated counts.

`resolve_usage` (1074–1088) exact names мають перевагу. Bare leaf fallback допускається, лише якщо supplied skills мають одного command owner для цього leaf; `deploy` не credit-иться одночасно `one:deploy` та `two:deploy`. Without skills parameter лишається старий standalone fallback behavior для API compatibility. Records можуть бути неповними, новий install може не мати історії, а mirrors/replayed session data можуть спотворити counts; це evidence, не usage telemetry service.

### Рядки 1093–1211: findings, token estimate і description clusters

`SEVERITIES` визначає sorting error → warn → info. `Finding` (1097–1103) — rule/severity/command/path/message/fix; тут немає auto-fix mutation. `estimate_tokens` (1106–1115) повертає 0 для empty та minimum 1 для nonempty, використовуючи Python round. `_content_words` (1118–1120) Unicode casefold, Unicode alphanumeric word regex, length >2 та stopwords. `_jaccard` (1123–1127) повертає intersection/union або 0 для empty sets. `_looks_like_symlink_stub` (1133–1136) розпізнає one-line path ending md/markdown; це heuristic, не Git mode check.

`cluster_by_description` (1139–1200) — graph connected components через union-find. Спочатку індексує word → skill indexes; max common-word frequency floor 50/5% обмежує candidate explosion. Exact nonempty word bags union-яться незалежно від pruning. Approximate pairs порівнюються лише за доступними discriminative words та threshold Jaccard; components sort-яться command name. Transitive cluster не означає, що кожна пара всередині має threshold overlap. Common-only near pairs можуть бути пропущені; empty/stopword-only descriptions не утворюють duplicates. `_truthy` (1203–1211) приводить string до accepted boolean spelling або None; у baseline не враховував collection kind, що давало false visibility для `[true]`.

### Рядки 1214–1417: `analyze`, кожне правило

Внутрішній `add` прив’язує finding до skill source path. Перший цикл перевіряє input/frontmatter та authoring. Unreadable SR007 припиняє подальшу перевірку цього skill; invalid YAML отримує SR009, а decoded metadata discarded, тому missing fields можуть породити secondary findings.

| Правило | Умова в реалізації | Severity та смисл |
| --- | --- | --- |
| SR001 | no/misplaced frontmatter | error; explicit metadata не прочитається за правилом first line |
| SR002 | skill без nonempty description | warn Claude / error portable; body fallback залишається можливим |
| SR003 | description + when_to_use >1536 | error supported model cap; actual retained text truncates |
| SR004 | disable true та user-invocable false | error; обидва normal invocation paths disabled |
| SR005 | bool field spelling не розпізнано | warn; prefer true/false |
| SR006 | no closing delimiter | error; header incomplete |
| SR007 | failed UTF-8/read | error; content unavailable |
| SR008 | path-only symlink stub | error heuristic; verify actual Git symlink |
| SR009 | invalid/unsupported parser syntax | error; no partial metadata accepted |
| SR010 | portable field outside six | error; Claude-only controls потребують іншого publishing mode |
| SR011 | portable compatibility >500 | error |
| SR012 | unknown nonportable field | info; typo/custom metadata review |
| SR013 | portable missing/invalid/mismatching name | error; 1–64 lowercase alnum/hyphen, no edge/repeated hyphen, directory match |
| SR014 | required field YAML kind/limit invalid | error; strings, description≤1024, compatibility nonempty, metadata string map |
| SR020 | repeated case-insensitive command name | warn; resolution conflict, одна command identity |
| SR021 | lexical connected component | warn heuristic; differentiate scope/triggers |
| SR022 | no known English trigger cue | warn heuristic; useful non-English trigger може не match |
| SR023 | nonblank body lines >budget | warn; progressive-disclosure review |
| SR024 | no matched invocation with usable history | info; does not prove uselessness |
| SR025 | description length <15 | warn heuristic |
| SR030 | description predicted dropped under budget | info; command name retained |

Legacy commands skip Agent Skills authoring requirements. `when_to_use` враховується в trigger check і listing cap. Portable description length перевіряє raw stored scalar, тому quoted edge whitespace також входить у limit, хоча display description trimmed. Command conflicts include even hidden entries; description overlap considers only described in_listing entries. SR024 baseline analyze API з explicit `{}` emits no observed calls, тоді як CLI перетворює empty/unavailable counts на None й не видає SR024 для кожного skill без evidence. Наприкінці findings stable sort за severity/rule/command.

### Рядки 1422–1561: Budget і узгоджене accounting

`Budget` (1423–1458) тримає discovered totals, names, requested descriptions, unloaded bodies, footprint, configured window/budget та commands/hidden/retained_desc. `requested_tokens` — names+all requested capped descriptions. `always_on_tokens` використовує actual simulated retained descriptions; legacy fallback caps aggregate description total лише коли exact retained total not supplied. `overflows` порівнює requested із budget, а percentages явно guard division by zero.

`_name_tokens` (1461–1463) оцінює command plus separator. `_desc_tokens` (1466–1469) name-only override →0, інакше routing_text[:1536]. `listing_tokens` (1472–1476) hidden→0; eligible →name+desc before collection budget. `_listed` (1479–1490) deduplicates case-insensitive names, skips hidden, skill wins over legacy command. За двох skills однакового command перший discovery entry retained; інструмент описує supported deterministic precedence model, не бачить live router.

`name_only_skills` (1493–1517) спочатку резервує всі names, навіть якщо names alone перевищують budget. Description candidates exclude deliberate name-only/empty routing. Sorting: most usage first, then cheapest description; same tie лишає discovery order. Greedy packing додає description only whole, тому unused budget не має billed tokens. Функція повертає predicted dropped Skill objects.

`retained_listing_costs` (1520–1532) uses object identity keys, щоб два discovered entries одного command не отримали обидва retained cost. Keys internal only. `budget` (1535–1561) computes configured fraction unless fixed tokens supplied, requested names/desc from `_listed`, bodies/bytes from every discovered entry, а retained total з того самого per-entry model. Це забезпечує `sum(JSON retained_listing_tokens) == budget.always_on_tokens`. Bodies — можливі loaded later, не always-on fee.

### Рядки 1566–1689: текстовий звіт

COLORS містить control sequences тільки presentation-owned styles. `_paint` (1572–1575) додає ці styles лише за enabled. `_human_bytes` (1578–1584) переводить bytes у base1024 B/KB/MB/GB; labels традиційні, не SI. `_display_text` (1587–1593) показує C0/DEL/C1 controls, surrogates і invalid BMP XML chars як visible escaped notation; це захищає audited metadata від terminal control injection й malformed SVG.

`render` (1596–1689) будує strings buffer. Local bold/dim closures застосовують styles. Count summary відображає skills/commands, hidden, estimated retained tokens/window share, requested budget share, predicted overflow, potential body cost/bytes. Top ranks requested costs, поруч показує retained costs і evidence. Findings grouped severity, per-rule limit default20, skipped remainder counts із --full hint. Command/message/fix text проходять sanitization. Footer explicitly states estimates/no live session. Missing color на nonTTY/NO_COLOR handled caller. Baseline operational stderr path не використовував `_display_text`, тому захист мав непокритий output boundary.

### Рядки 1692–1754: `to_json`

Payload schema_version1 включає package version, modeled harness/estimated flag, chars ratio/cap/usage available, aggregate budget, per-entry listing/body/visibility/origin/plugin/path/override/invocations та findings. Counts null означають немає usable evidence; 0 — evidence dataset є, matched calls немає. Requested listing_tokens можуть лишатися nonzero для shadowed eligible entry, тоді retained_listing_tokens0 чесно показує collection-level outcome. `json.dumps(...ensure_ascii=True, allow_nan=False)` зберігає Unicode через escapes у cp1251/ASCII streams і забороняє invalid JSON nonfinite numbers. Формат machine-readable; no SQL/network/persistence side effects.

### Рядки 1759–1836: SVG

`_svg_escape` sanitizes controls і XML `&<>`. `to_svg` (1763–1836) ranks eligible descriptions, sets canvas/row geometry, scales by max(requested,budget,1), renders requested listing bar plus dashed budget line and heaviest requested per-entry bars. Style theme uses prefers-color-scheme; generated content is self-contained. `bar_row` creates escaped labels/numbers; dynamic audited text is in text nodes, fill values internal constants. Footer closing SVG returns one string; caller owns disk write. Bars show requested, summary says retained. Це diagnostic chart, не графік actual token usage telemetry.

### Рядки 1841–1940: parser, numeric validation й streams

`_ReportArgumentParser._print_message` (1841–1844) використовує shared stream writer для help/errors, щоб legacy encodings та closed pipes також працювали. `build_parser` (1848–1900) визначає paths/json/portable/no-usage/transcripts/top/context-window/body-lines/similarity/chars-per-token/budget-fraction/svg/all/fail-on/fail-over-budget/full/no-color/version. Defaults мають deterministic behavior; --fail-on defaultnever не перетворює кожен warning у failure без explicit CI policy.

`_validate_cli_args` (1903–1915) обмежує positive context within sys.maxsize, nonnegative top/body threshold, finite chars/token0.1–100, similarity0–1, fraction(0,1]. `_ClosedOutputPipe` (1918–1919) відділяє broken stdout від іншого I/O failure. `_write_stream` (1922–1940) writes/flushes, catches UnicodeEncodeError і uses backslashreplace, recognizes Windows redirected EINVAL та BrokenPipeError only for stdout, closes stream and raises sentinel. Інші write errors propagate operationally; successful output encoding fallback не ламає ASCII JSON escapes.

### Рядки 1943–1952: `_protect_audited_sources`

Новий guard перед SVG write зіставляє resolved output із усіма discovered skill/legacy command paths та, для existing target, перевіряє filesystem samefile identity. Це відхиляє пряме перезаписування, symlink aliases та hardlinks до audited Markdown. Нерозв’язний symlink cycle дає operational error. Guard не є універсальним output sandbox: explicitly requested SVG target може бути іншою existing output file, і захист тут конкретно стосується discovered skill/command sources.

### Рядки 1955–2064: `_run_audit`, `main`, module entry

`_run_audit` спочатку вибирає roots/settings/extra. Explicit paths означають authored content audit, settings не підвантажуються як installed configuration. Default profile читає settings/enabled plugins, removes plugin cache root from generic scan, shallow scans local install dirs та adds home/project legacy commands. No roots/entries, missing input або empty local discovery — AuditError. Overrides apply лише nonplugin entries. Fraction priority: CLI → settings →default. Character budget із environment first then settings env applies only absent explicit budget fraction, ASCII positive int within sys.maxsize converts to token budget.

Usage None при --no-usage або zero usable counts. Totals and findings share the same assumptions. Optional --svg writes explicit UTF-8 file and status to stderr; write failure raises AuditError. JSON або text пишеться через safe stream writer. Color autoenable only TTY absent NO_COLOR. Finding failure threshold чи overbudget gate → exit1, normal reports →0. `main` catches closed pipe→0, AuditError/OSError→diagnostic stderr+2. Argparse own bad syntax exits2. Last module guard calls sys.exit(main()), console entry point uses same return code.

## Результати перевірки та підтверджені дефекти початкового знімка

Базова команда `python -m unittest discover -s tests -v` пройшла: 179 tests, приблизно 2.1 seconds на локальному Python 3.14. Це перевірка поточної dirty working copy; вона не доводить підтримку всіх заявлених Python/OS, для чого потрібна CI matrix. Не змінили жодного existing test/core file під час initial audit.

Порівняння supported YAML з локальним PyYAML використовувалось тільки як незалежний test oracle у аудиті. Runtime dependency продукту PyYAML не додано. Synthetic performance check exact duplicate descriptions: 100 →~0.0006s, 1000 →~0.0035s, 10000 →~0.036s; кожна колекція утворила один correct cluster. Це окремий microbenchmark CPU stage, не обіцянка часу повного disk scan.

| Пріоритет | Відтворення | Actual baseline | Root cause / потрібна зміна |
| --- | --- | --- | --- |
| P2 | `description: []` plus indented `Use when asked.` | --portable passes без error; full YAML ParserError | continuation не може додаватися після completed collection; не стирати typed kind |
| P2 | `description: [Use when asked.]` plus indented `continued` | invalid YAML стає string і passes | reject multiline continuation of collection before rendering |
| P2 | `metadata:` → indented `true: text` або `null: text` | string map accepted хоча real key boolean/null | validate key YAML type; quoted `"true"`/`"null"` залишити legitimate strings |
| P2 | `disable-model-invocation: [true]` | zero findings та excluded listing | bool consumers must reject collection kind; SR005 не має приймати flattened sequence |
| P2 | CLI missing path із `ESC ]52;... BEL` | raw control sequence in operational stderr | sanitize untrusted diagnostic/error text and written SVG path, not just report |
| P3 | folded `>+` scalar із trailing blank line | губиться один newline | separate fold and chomping handling; compare literal/folded strip/clip/keep matrix |

Мінімальні приклади відтворювалися temporary memory/files; дані audited skills не виконувались. Parent implementer отримав findings і precise root causes. Статус «виправлено» потрібно встановити лише після regression test before/after та updated full suite.

## Межі, ризики та сумісність

Zero-dependency single module має низький поріг запуску й простий supply chain. File read failures стають findings, malformed registry/settings стають operational errors, path containment захищає manifest-selected scan, report text sanitized. Це добрі основи для production CLI. Повний rewrite зараз збільшив би compatibility risk без доказового виграшу.

Remaining constraints: supported YAML subset; approximate chars-based tokenization; English trigger heuristic; common-word pruning може пропустити approximate similarity; connected components не pairwise equivalence; no live routing evaluation; no install-scope resolution for multiple roots; no resource ceiling для SKILL.md/JSON/transcript line sizes; traversal великих own bundles може коштувати час; partial unreadable transcripts silently skipped; provenance/coverage history не серіалізується; explicit paths не застосовують installed settings. Деякі з цих пунктів — свідомі product boundaries, а не дефекти. Їх не можна приховати advertising claims.

Backwards compatibility anchors: `Dict[str,str]` parser map, Skill/Budget/Finding constructor order/defaults, existing rule IDs, CLI option names/exit statuses, JSON schema_version1, command names/frontmatter-name precedence, no runtime dependencies, Python3.9+, data-only audit і requested/retained distinction. Додавати capabilities варто через additive fields/options із documented schema change, коли вона потрібна. Filename cleanup/module split не має непомітно ламати `import skillrot`, console script або single-file invocation.

## Розбір усіх тестів

`tests/test_skillrot.py`: 751 lines, 83 test methods. Helpers `run_cli` capture stdout/stderr; `write_skill` створює real temp layout; GOOD fixture має trigger and body. FrontmatterTests охоплює scalars/body, first-line marker, missing/unterminated, folded, shallow metadata, quotes. RuleTests перевіряє кожний початковий SR правило через real discovery, invocation combinations, portable fields, collision/descriptions/usage. UsageTests покриває root tool records, missing history, bare fallback. BudgetTests перевіряє cap/sums/zero denominator. DiscoveryTests перевіряє plugin manifests/cache fallback/name precedence/duplicates/direct file/relative path. CliTests перевіряє JSON, exit0/1/2, overbudget та no-color. ClusterTests перевіряє exact grouping, distinct/separate pairs, singleton та one-finding-per-component. Решта classes перевіряє symlink stubs, render truncation, plain folding, when_to_use triggers, named budget retention, nested own footprint, local command collision, shallow install scope, manifest discovery/remote-only semantics, legacy command paths/precedence/skip-authoring, hidden/name-only/body fallback, enabled plugin registry/merge, typed commands, XML SVG.

`tests/test_frontmatter_hardening.py`: 242 lines, 35 methods. Real temporary skills plus `parse/findings/errors` helpers. Covers comments in booleans, quoted keys/comments/escapes, quoted multiline fold/paragraph/backslash, plain continuation comments/literals, unindented delimiters, flow tools and indentation, empty items/nesting rejection, literal/folded semantics, shallow metadata typed values, unsupported anchors/tags/mappings, duplicates/tabs/controls/surrogates, required fields/type/caps, Unicode names, portable directory-relative paths та unreadable UTF-8. Baseline suite не перевіряла metadata key kinds, sequence+continuation і typed collection boolean values — саме там підтверджено gaps.

`tests/test_discovery_cli.py`: 495 lines, 42 methods. Helpers реалізують real filesystem layouts/settings JSON та environment/home/cwd patching. DiscoveryBoundaryTests перевіряє namespace evidence, only-Claude roots, scan_all, empty manifests/fallback distinctions, missing components/local sources, remote mirrors, marketplace required fields/extensions/strict flag, nested commands, traversal/absolute/UNC/symlink/junction containment, malformed/very deeply nested JSON. OperationalCliTests перевіряє missing among valid inputs, SVG failures, numeric finite bounds, settings/registries malformed shapes, scoped-root limitations/dedup, unresolved/disabled cache, plugin override exclusion, unknown invocation null, ASCII fallback, real subprocess broken-pipe для report/help/version. Це meaningful boundary tests, а не assertions, що повторюють implementation strings без behavior check.

`tests/test_accounting_usage.py`: 173 lines, 19 methods. Entry helper створює pure data instances. Accounting regression tests verify whole-description packing, common usage order aggregate/per-entry, zero hidden cost, deliberate name-only cost, JSON reconciliation/shadowed entries і Windows Unicode-safe ASCII JSON. Transcript tests verify key-order independence, nested assistant calls, command tags, malformed/unrelated content exclusion, tool_result exclusion і ambiguity-safe matching. UntrustedReportTextTests перевіряє XML controls/terminal metadata sanitization. CollisionBoundary tests verify fallback+when_to_use, exact duplicates despite common-word pruning at 50/51/300 size та Unicode word matching.

У наступному додатку кожен test method має власні line bounds, fixture/arrange/action/assertion structure та exact source. Це дозволяє перевірити, що «прочитано всі тести» означає розглянуті реальні branches та assertions.


<!-- FINAL_RANGES -->

## Кінцева реалізація та статус регресій

У межах цієї роботи виправлено всі підтверджені parser/visibility/output дефекти з таблиці baseline. Completed flow sequence більше не приймає scalar continuation; `_yaml_key` зберігає string-key вимогу; collection booleans дають SR005 і не приховують skill мовчки; folded `>+` зберігає trailing blank lines. Terminal text екранує C0, DEL та C1 у report, argparse, operational stderr і SVG-write status. Layout newlines/tabs зберігаються тільки у trusted multi-line argparse presentation. JSON лишається ASCII escaped.

Явний `--transcripts` повинен позначати existing directory, якщо usage увімкнене; missing path або file дає exit2 без JSON report. `--no-usage` вимикає читання та цю вимогу. Default unavailable history і `usage_counts()` public API зберігають попередню nonfatal behavior. SVG output не може alias-ити discovered SKILL.md або legacy command input, включно з real hardlinks. SR021 message тепер чесно описує transitive linked components: endpoints не зобов’язані мати threshold overlap між собою.

Новий `tests/test_production_edges.py` пройшов RED→GREEN. Initial run мав 18 failed subcases; додатковий status test теж спочатку провалився. C1 follow-up відтворив ще 6 failed subcases у report/stderr до fix. Targeted suite має 16 methods; 15 виконались успішно на Windows, один real POSIX control-character filename case skipped, а відповідний presentation boundary перевірений окремим narrow filesystem double. Hardlink protection перевірений на реальних NTFS files. Initial 179 tests були green до змін; після інтеграції першого bundle work повний suite був green (201, потім додавався C1 regression). `python -m mypy skillrot.py`, py_compile та scoped git diff --check пройшли. Підсумковий integration suite/версії/архіви належать актуальному `docs/RELEASE.md`; цифра initial run не підміняє release evidence.

Full YAML, live loader/router state, exact tokenization, partial history coverage та distinct install scopes залишаються явними межами. Override `on` із `disable-model-invocation` не отримав вигаданої precedence: офіційний опис interaction недостатньо точний, тому попередня conservative model збережена. No resource ceiling для великих Markdown/JSON/JSONL залишається. Ці межі слід врахувати при публікації claims.

`tests/test_production_edges.py` додає окрему перевірку invalid sequence continuation, коментарів без втрати sequence type, string/null/boolean mapping keys, quoted legitimate keys, collection boolean visibility, folded keep whitespace, explicit transcript file/missing path/no-usage, C0/C1 diagnostics і report, argv diagnostic safety, successful SVG-status formatting, direct/hardlink source preservation. Нові archive tests належать delivery workflow; їхня поточна inventory також наведена в додатку для повноти source map.




<!-- INVENTORY_RANGES -->

## Inventory correctness після незалежного review
+
+Незалежний reviewer відтворив real Windows ACL case на Python3.14.5 і3.10: visible skill плюс nested denied directory давали partial inventory, zero findings та exit0, бо Path.rglob/glob пригнічували directory enumeration errors. Виправлення має portable narrow-scandir regressions: recursive skill roots, shallow installed dirs, plugin skills, plugin recursive commands і local commands. Усі п’ять checks спочатку провалилися, після fix пройшли. Окремий real Windows junction case також був RED: external child skill за junction помилково включався; тепер implicit recursive traversal не виходить через child directory links.
+
+### Рядки 646–680: `_inventory_files`
+
+Єдиний inventory helper керує explicit stack `(directory, depth)`, відкриває directory через os.scandir context manager та обробляє errors як AuditError. Host-specific fnmatch зберігає case-insensitive matching Windows і case-sensitive matching POSIX, result sort за Path зберігає output order. Recursive matching охоплює root і descendants, але не follows child directory symlinks. Windows FILE_ATTRIBUTE_REPARSE_POINT також prune-иться, бо older Python сприймає junction як звичайний directory навіть із follow_symlinks=False. Direct root може бути linked directory, бо користувач обрав його явно. Shallow mode перевіряє лише один рівень skill directories, дозволяє linked installation на цьому рівні, не рекурсує нижче. Missing/not-directory optional component root повертає empty; PermissionError, nested disappearance та інші enumeration failures стають exit2 замість clean partial report.
+
+Helper застосований до generic recursive/shallow discovery, legacy local commands, manifest plugin skills і plugin commands. `usage_counts` transcript partial-coverage semantics та `_bundle_bytes` best-effort traversal не змінено: вони лишаються окремими documented boundaries. --all help тепер каже, що обходить manifest file selection, але ownership validation зберігається. Нові tests також перевіряють normal absent optional commands, real junction cycle termination, skipped recursive external link та accepted explicit linked root.
+
+Свіжа інтеграція після цього виправлення: 210 tests OK, один real POSIX control-character filename test skipped на Windows; 24 production-edge methods; mypy core, py_compile та diff-check OK. Runtime dependencies відсутні, version0.4.0 збережено. Цей проміжний core мав2050 physical lines; exact hash і source inventory знаходяться нижче. Actual ACL recheck/оновлені packages залишаються частиною parent release acceptance.
+


<!-- BUNDLE_LINK_RANGES -->
+
+## Точність власного bundle footprint після незалежного review
+
+Другий реальний Windows case показав, що os.walk у `_bundle_bytes` заходив у child junction dirs. У regression fixture власний SKILL.md має58 bytes, assets/data.txt128 bytes, а assets/cycle junction повторював assets: baseline показував8250 замість незалежно очікуваних186. Інший child junction до external directory із4096 bytes давав4154 замість58. Обидва tests були RED до fix і GREEN після.
+
+Виправлено лише own-footprint traversal: child dirs проходять os.lstat, symbolic-link mode та Windows FILE_ATTRIBUTE_REPARSE_POINT prune-яться перед descent. Явно обраний linked root лишається допустимим. Existing vendor/VCS exclusions, nested-skill ownership, best-effort stat errors і accounting formulas збережені. File bytes не є filesystem allocated sectors; optional unreadable/stat-inaccessible contents можуть пропускатися. Це окрема best-effort size metric; strict inventory errors продовжують давати operational failure.
+
+Фінальна перевірка після bounded footprint fix:212 tests OK, один POSIX filename case skipped на Windows;26 production-edge methods; mypy core, py_compile і diff-check OK. Version0.4.0 та inventory helper semantics збережені. Цей проміжний core мав2062 physical lines; поточний exact hash наведений у source map нижче.
+


<!-- RESOLVE_RANGES -->
+
+## Завершальна межа помилки Path.resolve
+
+[Офіційний Python3.9 pathlib contract](https://docs.python.org/3.9/library/pathlib.html#pathlib.Path.resolve) документує RuntimeError для нескінченного циклу resolution. У discover dedupe baseline ловив тільки OSError, тому older Python RuntimeError міг вийти до traceback. Narrow behavioral regression підміняє лише exact discovered SKILL.md.resolve; решта paths/files/CLI залишаються реальними. До fix test був RED із escaped RuntimeError, після fix result — exit2, emptystdout, sanitized operational diagnostic, без traceback. Discovery тепер локально конвертує саме цей documented RuntimeError до AuditError; broad RuntimeError swallowing у main не додано. Existing OSError fallback збережений.
+
+Незалежний reviewer додатково відтворив actual Windows self-junction resolution case на Python3.9; це підтверджує, що regression відповідає runtime boundary. Остаточна fresh source-suite перевірка:213 tests OK на actualPython3.9.25 і3.14.5, один POSIX control-filename case skipped на Windows;27 production-edge methods. mypy core, py_compile та diff-check OK. Version0.4.0 збережено; кінцеве ядро2064 physical lines, exact hash/source map нижче. Inventory і footprint fixes збережені, додаткових feature changes немає.
+

<!-- GENERATED_SOURCE_MAP_BEGIN -->

## Повна inventory функцій і класів

Nested helpers включені окремо: їхні ефекти не приховані за outer-function описом.

| Символ | Рядки | Контракт/роль |
| --- | --- | --- |
| <code>_FrontmatterValue</code> | 98–107 | Keep the public string mapping while retaining YAML types for validation. |
| <code>_FrontmatterValue.__new__</code> | 103–107 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>_yaml_comment</code> | 110–131 | Remove a separated comment, respecting a scalar's opening quotes. |
| <code>_strip_quotes</code> | 134–197 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>_yaml_scalar</code> | 200–254 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>_yaml_key</code> | 257–262 | Keep mapping keys as YAML strings, including explicitly quoted keys. |
| <code>_yaml_block</code> | 265–294 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>parse_frontmatter</code> | 297–412 | Parse a bounded YAML subset, reporting invalid/unsupported syntax. Supports scalar strings, flat lists and shallow metadata maps. This is not a full YAML validator. Unsupported syntax discards the metadata rather than supplying apparently valid values to the audit. |
| <code>Skill</code> | 417–467 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>Skill.description</code> | 431–433 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>Skill.when_to_use</code> | 435–437 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>Skill.routing_text</code> | 439–449 | What the listing shows after the name: description + when_to_use, or, with no description, the first non-empty line of the body (as documented). |
| <code>Skill.in_listing</code> | 451–458 | Whether the skill is advertised to the model at all. `disable-model-invocation: true` and the skillOverrides states "off" and "user-invocable-only" keep it out of context entirely. |
| <code>Skill.listing_text</code> | 460–463 | The text the harness puts in the always-on skill listing. |
| <code>Skill.body_lines</code> | 465–467 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>_is_version_dir</code> | 470–471 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>_plugin_name_for</code> | 474–491 | Walk up from a skill directory to name the plugin that ships it. |
| <code>_classify</code> | 494–508 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>_bundle_bytes</code> | 514–547 | Bytes of the skill's own files. Prunes VCS/vendor noise and never descends into a nested skill (a subdirectory carrying its own SKILL.md), so a plugin root or a whole repository dropped in as one skill reports its own footprint rather than the entire tree. Without this, a repo-root SKILL.md billed gigabytes and the walk dominated runtime. |
| <code>_directory_name</code> | 550–558 | The skill's own directory name, resolved so `.` and `..` don't leak through. |
| <code>load_skill</code> | 565–608 | Load one SKILL.md, or one commands/*.md file when kind == "command". `plugin` is the owning plugin when a manifest named it; otherwise it is inferred from the path. `command` is a precomputed name (commands take theirs from the file path, not from frontmatter). |
| <code>_project_dirs</code> | 611–619 | The start directory and its parents up to the repository root: Claude Code loads project skills from .claude/ in each. Outside a repo, just the start. |
| <code>default_roots</code> | 622–629 | Install directories for the Claude Code profile this tool models. |
| <code>command_entries</code> | 632–639 | Legacy command files: commands/deploy.md is /deploy and commands/frontend/component.md is /frontend:component. |
| <code>AuditError</code> | 642–643 | An operational input failure: an incomplete audit must not look clean. |
| <code>_inventory_files</code> | 646–680 | Enumerate inventory without silently suppressing directory read errors. Recursive scans do not descend into child symlink/reparse directories; explicit roots are followed. Shallow installed roots inspect one level of skill directories, including linked installations, but never recurse deeper. Missing optional component roots are normal; inaccessible roots are errors. |
| <code>_read_json</code> | 683–696 | Read an optional JSON object; present but invalid input is an error. |
| <code>_read_json.reject_constant</code> | 685–686 | JSON parse hook: відкидає NaN/Infinity як operational invalid input. |
| <code>_as_paths</code> | 699–708 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>_within_root</code> | 711–716 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>_manifest_path</code> | 719–726 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>_validate_plugin_manifest</code> | 729–734 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>_marketplace_entries</code> | 737–756 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>_plugin_entries</code> | 759–827 | Everything one plugin adds to the listing: skills and commands. Skills: default `skills/&lt;name&gt;/SKILL.md`, plus any manifest `skills` paths (a folder of skill folders, or one folder holding SKILL.md); a plugin with only a root SKILL.md loads as a single skill. Commands: `commands/*.md`, unless the manifest `commands` key replaces that default. With no plugin.json, the marketplace entry is the manifest. Unsupported manifest shapes are diagnosed rather than silently skipped. |
| <code>manifest_skill_files</code> | 830–858 | Skills and commands a marketplace or plugin checkout would install. Returns None when `root` is neither, so the caller falls back to a plain recursive scan. Without this, a repo's translated docs and mirrors for other harnesses (docs/ja-JP/skills, .gemini/skills, ...) were counted as installed skills and inflated the bill several times over. ponytail: only local (string) plugin sources resolve; github/url sources are not in this checkout, so they are skipped rather than fetched. |
| <code>_validate_settings</code> | 861–880 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>load_settings</code> | 883–898 | Merge Claude Code settings: user, then project, then local (later wins; enabledPlugins, skillOverrides and env merge key by key). |
| <code>installed_plugin_entries</code> | 901–968 | Skills and commands of the plugins enabled in settings. Resolves each `name@marketplace` through installed_plugins.json (the install cache) and, for directory marketplaces loaded in place, through known_marketplaces.json. An absent enabledPlugins setting means no enabled plugins; blindly scanning the cache would count disabled installations. |
| <code>discover</code> | 971–1019 | Find and load every unique skill under the roots, plus `extra` entries. A root in `shallow_roots` is scanned one level deep (`*/SKILL.md`), the way Claude Code loads an install directory: a whole repo dropped into `~/.claude/skills/foo/` is one skill at `foo/SKILL.md`, not every nested SKILL.md it happens to contain. A marketplace or plugin checkout is read through its manifest, so only what Claude Code would install is counted. Any other root is scanned recursively; `scan_all` forces that everywhere. |
| <code>usage_counts</code> | 1028–1071 | Count real invocations in local Claude Code transcripts: Skill tool calls made by the model, plus /commands the user typed. |
| <code>resolve_usage</code> | 1074–1088 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>Finding</code> | 1096–1103 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>estimate_tokens</code> | 1106–1115 | Character-ratio token estimate. No tokenizer dependency. Useful for ranking listings, not exact. Pass --chars-per-token to recalibrate, or feed --json into a real tokenizer when you need precise numbers. |
| <code>_content_words</code> | 1118–1120 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>_jaccard</code> | 1123–1127 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>_looks_like_symlink_stub</code> | 1133–1136 | A git symlink checked out as a plain file: one line holding a path. |
| <code>cluster_by_description</code> | 1139–1200 | Group skills whose descriptions overlap past `similarity`. Exact word bags are grouped first, including large duplicate collections. Approximate pairs use an index of discriminative words to bound the work; descriptions made entirely of collection-wide common words can still hide approximate matches. This is a word-overlap heuristic, not a routing eval. |
| <code>cluster_by_description.find</code> | 1165–1169 | Знаходить representative union-find компонента з path compression. |
| <code>cluster_by_description.union</code> | 1171–1174 | Зливає два components; менший representative index зберігає deterministic identity. |
| <code>_truthy</code> | 1203–1211 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>analyze</code> | 1214–1417 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>analyze.add</code> | 1225–1226 | Додає Finding з rule/severity/message/fix та actual skill command/source path. |
| <code>Budget</code> | 1422–1458 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>Budget.requested_tokens</code> | 1435–1438 | What the whole listing would cost if nothing were dropped. |
| <code>Budget.always_on_tokens</code> | 1440–1446 | Estimated retained names and descriptions in the configured model. |
| <code>Budget.overflows</code> | 1448–1450 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>Budget.context_percent</code> | 1452–1454 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>Budget.budget_percent</code> | 1456–1458 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>_name_tokens</code> | 1461–1463 | The listing names each entry by the command you'd type. |
| <code>_desc_tokens</code> | 1466–1469 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>listing_tokens</code> | 1472–1476 | Requested cost of an eligible entry, before collection budget/precedence. |
| <code>_listed</code> | 1479–1490 | The entries eligible for the estimated listing: one per command name. When a skill and a command file share a name, the skill wins, so the duplicate never reaches the listing (SR020 still reports it). |
| <code>name_only_skills</code> | 1493–1517 | Listed skills whose description won't fit the listing budget. Names of everything in the listing are always kept; the remaining budget fills with descriptions most-used first (Claude Code drops the least-used ones), tie-broken by the cheaper description so more of them fit. Skills hidden from the model, or set to name-only on purpose, are not reported. |
| <code>retained_listing_costs</code> | 1520–1532 | Per-entry costs for the same estimated retention model used by SR030. Identity keys distinguish shadowed entries with the same command name. They are internal only and are never serialized. |
| <code>budget</code> | 1535–1561 | Size the listing. Only skills advertised to the model count toward it; `listing_budget_tokens` pins the budget (SLASH_COMMAND_TOOL_CHAR_BUDGET). |
| <code>_paint</code> | 1572–1575 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>_human_bytes</code> | 1578–1584 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>_display_text</code> | 1587–1593 | Render controls in untrusted file metadata as visible escape notation. |
| <code>render</code> | 1596–1689 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>render.bold</code> | 1608–1609 | Presentation-owned bold style через shared _paint з урахуванням color flag. |
| <code>render.dim</code> | 1611–1612 | Presentation-owned dim style через shared _paint з урахуванням color flag. |
| <code>to_json</code> | 1692–1754 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>_svg_escape</code> | 1759–1760 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>to_svg</code> | 1763–1836 | A self-contained, theme-aware budget chart. One bar for the listing (filled to the budget line, overflow hatched) and a ranked bar per heaviest skill. No dependencies: the ranking is the point, the numbers are the 4-char-per-token estimate the rest of the tool uses. |
| <code>to_svg.bar_row</code> | 1782–1790 | Рендерить один scaled SVG bar і escaped label/numeric note; audited text не стає markup. |
| <code>_ReportArgumentParser</code> | 1841–1845 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>_ReportArgumentParser._print_message</code> | 1842–1845 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>build_parser</code> | 1848–1900 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>_validate_cli_args</code> | 1903–1915 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>_ClosedOutputPipe</code> | 1918–1919 | Only a stdout write can turn a closed pipe into normal termination. |
| <code>_write_stream</code> | 1922–1940 | Keep reports usable on narrow terminal encodings without losing JSON. |
| <code>_protect_audited_sources</code> | 1943–1952 | Refuse a chart target that aliases a discovered skill or command file. |
| <code>_run_audit</code> | 1955–2048 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |
| <code>main</code> | 2051–2060 | Typed API/property; повний behavior розібраний у відповідному розділі вище. |

## Построкова карта кінцевого ядра

Файл `skillrot.py`, version `0.4.0`, **2064 рядків**, SHA-256 `c73ec50a59708a1323fb32889de9dad3114d1093f76694688dd6eaad91fd842e`. Кожен фізичний рядок присутній рівно один раз. У багаторядковій інструкції пояснення відноситься до найвужчого AST statement; nested functions мають власний owner. Source code наведений без пропусків.

| Рядок | Власник | Точний source | Роль рядка/інструкції |
| --- | --- | --- | --- |
| 1 | <code>&lt;module&gt;</code> | <code>#!/usr/bin/env python3</code> | Unix interpreter directive; Python module execution нижче platform-neutral. |
| 2 | <code>&lt;module&gt;</code> | <code>"""skillrot - offline audits of skill libraries and estimated listing pressure.</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 3 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 4 | <code>&lt;module&gt;</code> | <code>Model the supported Claude Code listing profile, check skill authoring and</code> | Продовження інструкції 2: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 5 | <code>&lt;module&gt;</code> | <code>collection conflicts, and optionally inspect local invocation evidence.</code> | Продовження інструкції 2: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 6 | <code>&lt;module&gt;</code> | <code>Token and routing estimates do not inspect a running agent session.</code> | Продовження інструкції 2: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 7 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 8 | <code>&lt;module&gt;</code> | <code>Zero dependencies. Python 3.9+.</code> | Продовження інструкції 2: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 9 | <code>&lt;module&gt;</code> | <code>"""</code> | Продовження інструкції 2: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 10 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 11 | <code>&lt;module&gt;</code> | <code>from __future__ import annotations</code> | Імпорт standard library або допоміжного контракту: from __future__ import annotations |
| 12 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 13 | <code>&lt;module&gt;</code> | <code>import argparse</code> | Імпорт standard library або допоміжного контракту: import argparse |
| 14 | <code>&lt;module&gt;</code> | <code>import fnmatch</code> | Імпорт standard library або допоміжного контракту: import fnmatch |
| 15 | <code>&lt;module&gt;</code> | <code>import json</code> | Імпорт standard library або допоміжного контракту: import json |
| 16 | <code>&lt;module&gt;</code> | <code>import math</code> | Імпорт standard library або допоміжного контракту: import math |
| 17 | <code>&lt;module&gt;</code> | <code>import os</code> | Імпорт standard library або допоміжного контракту: import os |
| 18 | <code>&lt;module&gt;</code> | <code>import re</code> | Імпорт standard library або допоміжного контракту: import re |
| 19 | <code>&lt;module&gt;</code> | <code>import stat</code> | Імпорт standard library або допоміжного контракту: import stat |
| 20 | <code>&lt;module&gt;</code> | <code>import sys</code> | Імпорт standard library або допоміжного контракту: import sys |
| 21 | <code>&lt;module&gt;</code> | <code>from concurrent.futures import ThreadPoolExecutor</code> | Імпорт standard library або допоміжного контракту: from concurrent.futures import ThreadPoolExecutor |
| 22 | <code>&lt;module&gt;</code> | <code>from dataclasses import dataclass, field</code> | Імпорт standard library або допоміжного контракту: from dataclasses import dataclass, field |
| 23 | <code>&lt;module&gt;</code> | <code>from pathlib import Path, PureWindowsPath</code> | Імпорт standard library або допоміжного контракту: from pathlib import Path, PureWindowsPath |
| 24 | <code>&lt;module&gt;</code> | <code>from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple</code> | Імпорт standard library або допоміжного контракту: from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple |
| 25 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 26 | <code>&lt;module&gt;</code> | <code>__version__ = "0.4.0"</code> | Обчислює та зберігає __version__ ← '0.4.0' |
| 27 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 28 | <code>&lt;module&gt;</code> | <code># --- Spec constants -------------------------------------------------------</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 29 | <code>&lt;module&gt;</code> | <code># Sourced from the Claude Code skills reference and the Agent Skills spec.</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 30 | <code>&lt;module&gt;</code> | <code># docs/RULES.md carries the citation behind every rule.</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 31 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 32 | <code>&lt;module&gt;</code> | <code>LISTING_CHAR_CAP = 1536      # description + when_to_use, truncated in the listing</code> | Обчислює та зберігає LISTING_CHAR_CAP ← 1536 |
| 33 | <code>&lt;module&gt;</code> | <code>COMPATIBILITY_CAP = 500      # Agent Skills spec limit on `compatibility`</code> | Обчислює та зберігає COMPATIBILITY_CAP ← 500 |
| 34 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 35 | <code>&lt;module&gt;</code> | <code># The six fields accepted by claude.ai uploads, the Skills API and</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 36 | <code>&lt;module&gt;</code> | <code># package_skill.py. Anything else is a hard error on those paths.</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 37 | <code>&lt;module&gt;</code> | <code>PORTABLE_FIELDS = {</code> | Обчислює та зберігає PORTABLE_FIELDS ← {'name', 'description', 'license', 'compatibility', 'metadata', 'allowed-tools'} |
| 38 | <code>&lt;module&gt;</code> | <code>    "name",</code> | Продовження інструкції 37: Обчислює та зберігає PORTABLE_FIELDS ← {'name', 'description', 'license', 'compatibility', 'metadata', 'allowed-tools'} |
| 39 | <code>&lt;module&gt;</code> | <code>    "description",</code> | Продовження інструкції 37: Обчислює та зберігає PORTABLE_FIELDS ← {'name', 'description', 'license', 'compatibility', 'metadata', 'allowed-tools'} |
| 40 | <code>&lt;module&gt;</code> | <code>    "license",</code> | Продовження інструкції 37: Обчислює та зберігає PORTABLE_FIELDS ← {'name', 'description', 'license', 'compatibility', 'metadata', 'allowed-tools'} |
| 41 | <code>&lt;module&gt;</code> | <code>    "compatibility",</code> | Продовження інструкції 37: Обчислює та зберігає PORTABLE_FIELDS ← {'name', 'description', 'license', 'compatibility', 'metadata', 'allowed-tools'} |
| 42 | <code>&lt;module&gt;</code> | <code>    "metadata",</code> | Продовження інструкції 37: Обчислює та зберігає PORTABLE_FIELDS ← {'name', 'description', 'license', 'compatibility', 'metadata', 'allowed-tools'} |
| 43 | <code>&lt;module&gt;</code> | <code>    "allowed-tools",</code> | Продовження інструкції 37: Обчислює та зберігає PORTABLE_FIELDS ← {'name', 'description', 'license', 'compatibility', 'metadata', 'allowed-tools'} |
| 44 | <code>&lt;module&gt;</code> | <code>}</code> | Продовження інструкції 37: Обчислює та зберігає PORTABLE_FIELDS ← {'name', 'description', 'license', 'compatibility', 'metadata', 'allowed-tools'} |
| 45 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 46 | <code>&lt;module&gt;</code> | <code># Every field Claude Code itself accepts.</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 47 | <code>&lt;module&gt;</code> | <code>KNOWN_FIELDS = PORTABLE_FIELDS &#124; {</code> | Обчислює та зберігає KNOWN_FIELDS ← PORTABLE_FIELDS &#124; {'when_to_use', 'argument-hint', 'arguments', 'disable-model-invocation', 'user-invocable', 'disallowed-tools', 'model', 'effort', 'context', 'agent', 'background', 'hooks', 'paths'… |
| 48 | <code>&lt;module&gt;</code> | <code>    "when_to_use",</code> | Продовження інструкції 47: Обчислює та зберігає KNOWN_FIELDS ← PORTABLE_FIELDS &#124; {'when_to_use', 'argument-hint', 'arguments', 'disable-model-invocation', 'user-invocable', 'disallowed-tools', 'model', 'effort', 'context', 'agent', 'background', 'hooks', 'paths'… |
| 49 | <code>&lt;module&gt;</code> | <code>    "argument-hint",</code> | Продовження інструкції 47: Обчислює та зберігає KNOWN_FIELDS ← PORTABLE_FIELDS &#124; {'when_to_use', 'argument-hint', 'arguments', 'disable-model-invocation', 'user-invocable', 'disallowed-tools', 'model', 'effort', 'context', 'agent', 'background', 'hooks', 'paths'… |
| 50 | <code>&lt;module&gt;</code> | <code>    "arguments",</code> | Продовження інструкції 47: Обчислює та зберігає KNOWN_FIELDS ← PORTABLE_FIELDS &#124; {'when_to_use', 'argument-hint', 'arguments', 'disable-model-invocation', 'user-invocable', 'disallowed-tools', 'model', 'effort', 'context', 'agent', 'background', 'hooks', 'paths'… |
| 51 | <code>&lt;module&gt;</code> | <code>    "disable-model-invocation",</code> | Продовження інструкції 47: Обчислює та зберігає KNOWN_FIELDS ← PORTABLE_FIELDS &#124; {'when_to_use', 'argument-hint', 'arguments', 'disable-model-invocation', 'user-invocable', 'disallowed-tools', 'model', 'effort', 'context', 'agent', 'background', 'hooks', 'paths'… |
| 52 | <code>&lt;module&gt;</code> | <code>    "user-invocable",</code> | Продовження інструкції 47: Обчислює та зберігає KNOWN_FIELDS ← PORTABLE_FIELDS &#124; {'when_to_use', 'argument-hint', 'arguments', 'disable-model-invocation', 'user-invocable', 'disallowed-tools', 'model', 'effort', 'context', 'agent', 'background', 'hooks', 'paths'… |
| 53 | <code>&lt;module&gt;</code> | <code>    "disallowed-tools",</code> | Продовження інструкції 47: Обчислює та зберігає KNOWN_FIELDS ← PORTABLE_FIELDS &#124; {'when_to_use', 'argument-hint', 'arguments', 'disable-model-invocation', 'user-invocable', 'disallowed-tools', 'model', 'effort', 'context', 'agent', 'background', 'hooks', 'paths'… |
| 54 | <code>&lt;module&gt;</code> | <code>    "model",</code> | Продовження інструкції 47: Обчислює та зберігає KNOWN_FIELDS ← PORTABLE_FIELDS &#124; {'when_to_use', 'argument-hint', 'arguments', 'disable-model-invocation', 'user-invocable', 'disallowed-tools', 'model', 'effort', 'context', 'agent', 'background', 'hooks', 'paths'… |
| 55 | <code>&lt;module&gt;</code> | <code>    "effort",</code> | Продовження інструкції 47: Обчислює та зберігає KNOWN_FIELDS ← PORTABLE_FIELDS &#124; {'when_to_use', 'argument-hint', 'arguments', 'disable-model-invocation', 'user-invocable', 'disallowed-tools', 'model', 'effort', 'context', 'agent', 'background', 'hooks', 'paths'… |
| 56 | <code>&lt;module&gt;</code> | <code>    "context",</code> | Продовження інструкції 47: Обчислює та зберігає KNOWN_FIELDS ← PORTABLE_FIELDS &#124; {'when_to_use', 'argument-hint', 'arguments', 'disable-model-invocation', 'user-invocable', 'disallowed-tools', 'model', 'effort', 'context', 'agent', 'background', 'hooks', 'paths'… |
| 57 | <code>&lt;module&gt;</code> | <code>    "agent",</code> | Продовження інструкції 47: Обчислює та зберігає KNOWN_FIELDS ← PORTABLE_FIELDS &#124; {'when_to_use', 'argument-hint', 'arguments', 'disable-model-invocation', 'user-invocable', 'disallowed-tools', 'model', 'effort', 'context', 'agent', 'background', 'hooks', 'paths'… |
| 58 | <code>&lt;module&gt;</code> | <code>    "background",</code> | Продовження інструкції 47: Обчислює та зберігає KNOWN_FIELDS ← PORTABLE_FIELDS &#124; {'when_to_use', 'argument-hint', 'arguments', 'disable-model-invocation', 'user-invocable', 'disallowed-tools', 'model', 'effort', 'context', 'agent', 'background', 'hooks', 'paths'… |
| 59 | <code>&lt;module&gt;</code> | <code>    "hooks",</code> | Продовження інструкції 47: Обчислює та зберігає KNOWN_FIELDS ← PORTABLE_FIELDS &#124; {'when_to_use', 'argument-hint', 'arguments', 'disable-model-invocation', 'user-invocable', 'disallowed-tools', 'model', 'effort', 'context', 'agent', 'background', 'hooks', 'paths'… |
| 60 | <code>&lt;module&gt;</code> | <code>    "paths",</code> | Продовження інструкції 47: Обчислює та зберігає KNOWN_FIELDS ← PORTABLE_FIELDS &#124; {'when_to_use', 'argument-hint', 'arguments', 'disable-model-invocation', 'user-invocable', 'disallowed-tools', 'model', 'effort', 'context', 'agent', 'background', 'hooks', 'paths'… |
| 61 | <code>&lt;module&gt;</code> | <code>    "shell",</code> | Продовження інструкції 47: Обчислює та зберігає KNOWN_FIELDS ← PORTABLE_FIELDS &#124; {'when_to_use', 'argument-hint', 'arguments', 'disable-model-invocation', 'user-invocable', 'disallowed-tools', 'model', 'effort', 'context', 'agent', 'background', 'hooks', 'paths'… |
| 62 | <code>&lt;module&gt;</code> | <code>    "version",</code> | Продовження інструкції 47: Обчислює та зберігає KNOWN_FIELDS ← PORTABLE_FIELDS &#124; {'when_to_use', 'argument-hint', 'arguments', 'disable-model-invocation', 'user-invocable', 'disallowed-tools', 'model', 'effort', 'context', 'agent', 'background', 'hooks', 'paths'… |
| 63 | <code>&lt;module&gt;</code> | <code>}</code> | Продовження інструкції 47: Обчислює та зберігає KNOWN_FIELDS ← PORTABLE_FIELDS &#124; {'when_to_use', 'argument-hint', 'arguments', 'disable-model-invocation', 'user-invocable', 'disallowed-tools', 'model', 'effort', 'context', 'agent', 'background', 'hooks', 'paths'… |
| 64 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 65 | <code>&lt;module&gt;</code> | <code>BOOL_FIELDS = ("disable-model-invocation", "user-invocable", "background")</code> | Обчислює та зберігає BOOL_FIELDS ← ('disable-model-invocation', 'user-invocable', 'background') |
| 66 | <code>&lt;module&gt;</code> | <code>TRUE_WORDS = {"true", "yes", "on", "1"}</code> | Обчислює та зберігає TRUE_WORDS ← {'true', 'yes', 'on', '1'} |
| 67 | <code>&lt;module&gt;</code> | <code>FALSE_WORDS = {"false", "no", "off", "0"}</code> | Обчислює та зберігає FALSE_WORDS ← {'false', 'no', 'off', '0'} |
| 68 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 69 | <code>&lt;module&gt;</code> | <code># Cues that tell the router *when* to reach for a skill. A description with</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 70 | <code>&lt;module&gt;</code> | <code># none of these describes what a skill is, not when it applies.</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 71 | <code>&lt;module&gt;</code> | <code>TRIGGER_CUES = (</code> | Обчислює та зберігає TRIGGER_CUES ← ('use when', 'use this when', 'used when', 'when the user', 'when you', 'when asked', 'when working', 'when a ', 'when the ', 'invoke when', 'trigger', 'for when', 'apply when', 'activates when', 'ca… |
| 72 | <code>&lt;module&gt;</code> | <code>    "use when", "use this when", "used when", "when the user", "when you",</code> | Продовження інструкції 71: Обчислює та зберігає TRIGGER_CUES ← ('use when', 'use this when', 'used when', 'when the user', 'when you', 'when asked', 'when working', 'when a ', 'when the ', 'invoke when', 'trigger', 'for when', 'apply when', 'activates when', 'ca… |
| 73 | <code>&lt;module&gt;</code> | <code>    "when asked", "when working", "when a ", "when the ", "invoke when",</code> | Продовження інструкції 71: Обчислює та зберігає TRIGGER_CUES ← ('use when', 'use this when', 'used when', 'when the user', 'when you', 'when asked', 'when working', 'when a ', 'when the ', 'invoke when', 'trigger', 'for when', 'apply when', 'activates when', 'ca… |
| 74 | <code>&lt;module&gt;</code> | <code>    "trigger", "for when", "apply when", "activates when", "call this when",</code> | Продовження інструкції 71: Обчислює та зберігає TRIGGER_CUES ← ('use when', 'use this when', 'used when', 'when the user', 'when you', 'when asked', 'when working', 'when a ', 'when the ', 'invoke when', 'trigger', 'for when', 'apply when', 'activates when', 'ca… |
| 75 | <code>&lt;module&gt;</code> | <code>)</code> | Продовження інструкції 71: Обчислює та зберігає TRIGGER_CUES ← ('use when', 'use this when', 'used when', 'when the user', 'when you', 'when asked', 'when working', 'when a ', 'when the ', 'invoke when', 'trigger', 'for when', 'apply when', 'activates when', 'ca… |
| 76 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 77 | <code>&lt;module&gt;</code> | <code>DEFAULT_CONTEXT_WINDOW = 200_000</code> | Обчислює та зберігає DEFAULT_CONTEXT_WINDOW ← 200000 |
| 78 | <code>&lt;module&gt;</code> | <code>DEFAULT_BODY_LINE_BUDGET = 500</code> | Обчислює та зберігає DEFAULT_BODY_LINE_BUDGET ← 500 |
| 79 | <code>&lt;module&gt;</code> | <code>DEFAULT_SIMILARITY = 0.80</code> | Обчислює та зберігає DEFAULT_SIMILARITY ← 0.8 |
| 80 | <code>&lt;module&gt;</code> | <code>DEFAULT_CHARS_PER_TOKEN = 4.0</code> | Обчислює та зберігає DEFAULT_CHARS_PER_TOKEN ← 4.0 |
| 81 | <code>&lt;module&gt;</code> | <code># Claude Code sizes the always-on skill listing at 1% of the context window and</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 82 | <code>&lt;module&gt;</code> | <code># drops the least-used descriptions when it overflows (skillListingBudgetFraction,</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 83 | <code>&lt;module&gt;</code> | <code># SLASH_COMMAND_TOOL_CHAR_BUDGET). Skill names are always kept.</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 84 | <code>&lt;module&gt;</code> | <code>DEFAULT_BUDGET_FRACTION = 0.01</code> | Обчислює та зберігає DEFAULT_BUDGET_FRACTION ← 0.01 |
| 85 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 86 | <code>&lt;module&gt;</code> | <code>STOPWORDS = {</code> | Обчислює та зберігає STOPWORDS ← {'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'in', 'into', 'is', 'it', 'of', 'on', 'or', 'that', 'the', 'this', 'to', 'use', 'used', 'using', 'when', 'with', 'you', 'your'} |
| 87 | <code>&lt;module&gt;</code> | <code>    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",</code> | Продовження інструкції 86: Обчислює та зберігає STOPWORDS ← {'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'in', 'into', 'is', 'it', 'of', 'on', 'or', 'that', 'the', 'this', 'to', 'use', 'used', 'using', 'when', 'with', 'you', 'your'} |
| 88 | <code>&lt;module&gt;</code> | <code>    "into", "is", "it", "of", "on", "or", "that", "the", "this", "to", "use",</code> | Продовження інструкції 86: Обчислює та зберігає STOPWORDS ← {'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'in', 'into', 'is', 'it', 'of', 'on', 'or', 'that', 'the', 'this', 'to', 'use', 'used', 'using', 'when', 'with', 'you', 'your'} |
| 89 | <code>&lt;module&gt;</code> | <code>    "used", "using", "when", "with", "you", "your",</code> | Продовження інструкції 86: Обчислює та зберігає STOPWORDS ← {'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'in', 'into', 'is', 'it', 'of', 'on', 'or', 'that', 'the', 'this', 'to', 'use', 'used', 'using', 'when', 'with', 'you', 'your'} |
| 90 | <code>&lt;module&gt;</code> | <code>}</code> | Продовження інструкції 86: Обчислює та зберігає STOPWORDS ← {'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'in', 'into', 'is', 'it', 'of', 'on', 'or', 'that', 'the', 'this', 'to', 'use', 'used', 'using', 'when', 'with', 'you', 'your'} |
| 91 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 92 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 93 | <code>&lt;module&gt;</code> | <code># --- Frontmatter parsing --------------------------------------------------</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 94 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 95 | <code>&lt;module&gt;</code> | <code>_KEY_RE = re.compile(r'''^((?:"(?:[^"\\]&#124;\\.)*"&#124;'(?:[^']&#124;'')*'&#124;[A-Za-z_][A-Za-z0-9_.-]*))\s*:\s*(.*)$''')</code> | Обчислює та зберігає _KEY_RE ← re.compile('^((?:"(?:[^"\\\\]&#124;\\\\.)*"&#124;\'(?:[^\']&#124;\'\')*\'&#124;[A-Za-z_][A-Za-z0-9_.-]*))\\s*:\\s*(.*)$') |
| 96 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 97 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 98 | <code>_FrontmatterValue</code> | <code>class _FrontmatterValue(str):</code> | Оголошення класу `_FrontmatterValue` та базових класів; модель даних/поведінка розібрана вище. |
| 99 | <code>_FrontmatterValue</code> | <code>    """Keep the public string mapping while retaining YAML types for validation."""</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 100 | <code>_FrontmatterValue</code> | <code>    kind: str</code> | Типізує kind як str |
| 101 | <code>_FrontmatterValue</code> | <code>    members: object</code> | Типізує members як object |
| 102 | <code>_FrontmatterValue</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 103 | <code>_FrontmatterValue.__new__</code> | <code>    def __new__(cls, value: str, kind: str = "string", members=None):</code> | Оголошення функції `__new__` та її аргументів; детальний контракт розібраний вище. |
| 104 | <code>_FrontmatterValue.__new__</code> | <code>        instance = super().__new__(cls, value)</code> | Обчислює та зберігає instance ← super().__new__(cls, value) |
| 105 | <code>_FrontmatterValue.__new__</code> | <code>        instance.kind = kind</code> | Обчислює та зберігає instance.kind ← kind |
| 106 | <code>_FrontmatterValue.__new__</code> | <code>        instance.members = members</code> | Обчислює та зберігає instance.members ← members |
| 107 | <code>_FrontmatterValue.__new__</code> | <code>        return instance</code> | Завершує поточну функцію та повертає instance |
| 108 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 109 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 110 | <code>_yaml_comment</code> | <code>def _yaml_comment(value: str) -&gt; str:</code> | Оголошення функції `_yaml_comment` та її аргументів; детальний контракт розібраний вище. |
| 111 | <code>_yaml_comment</code> | <code>    """Remove a separated comment, respecting a scalar's opening quotes."""</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 112 | <code>_yaml_comment</code> | <code>    quote = value[:1] if value[:1] in ("'", '"') else None</code> | Обчислює та зберігає quote ← value[:1] if value[:1] in ("'", '"') else None |
| 113 | <code>_yaml_comment</code> | <code>    flow = value.startswith("[")</code> | Обчислює та зберігає flow ← value.startswith('[') |
| 114 | <code>_yaml_comment</code> | <code>    i = 1 if quote else 0</code> | Обчислює та зберігає i ← 1 if quote else 0 |
| 115 | <code>_yaml_comment</code> | <code>    while i &lt; len(value):</code> | Продовжує цикл поки i &lt; len(value) |
| 116 | <code>_yaml_comment</code> | <code>        char = value[i]</code> | Обчислює та зберігає char ← value[i] |
| 117 | <code>_yaml_comment</code> | <code>        if quote:</code> | Умовна гілка: quote; відповідний block виконується тільки коли умова true. |
| 118 | <code>_yaml_comment</code> | <code>            if quote == '"' and char == "\\":</code> | Умовна гілка: quote == '"' and char == '\\'; відповідний block виконується тільки коли умова true. |
| 119 | <code>_yaml_comment</code> | <code>                i += 2</code> | Оновлює накопичене значення: i += 2 |
| 120 | <code>_yaml_comment</code> | <code>                continue</code> | Пропускає решту цієї ітерації; переходить до наступного елемента. |
| 121 | <code>_yaml_comment</code> | <code>            if char == quote:</code> | Умовна гілка: char == quote; відповідний block виконується тільки коли умова true. |
| 122 | <code>_yaml_comment</code> | <code>                if quote == "'" and value[i:i + 2] == "''":</code> | Умовна гілка: quote == "'" and value[i:i + 2] == "''"; відповідний block виконується тільки коли умова true. |
| 123 | <code>_yaml_comment</code> | <code>                    i += 2</code> | Оновлює накопичене значення: i += 2 |
| 124 | <code>_yaml_comment</code> | <code>                    continue</code> | Пропускає решту цієї ітерації; переходить до наступного елемента. |
| 125 | <code>_yaml_comment</code> | <code>                quote = None</code> | Обчислює та зберігає quote ← None |
| 126 | <code>_yaml_comment</code> | <code>        elif flow and char in "\"'" and (i == 0 or value[i - 1] in " [,\t"):</code> | Наступна умовна гілка, коли попередній if/elif не виконався. |
| 127 | <code>_yaml_comment</code> | <code>            quote = char</code> | Обчислює та зберігає quote ← char |
| 128 | <code>_yaml_comment</code> | <code>        elif char == "#" and (i == 0 or value[i - 1].isspace()):</code> | Наступна умовна гілка, коли попередній if/elif не виконався. |
| 129 | <code>_yaml_comment</code> | <code>            return value[:i].rstrip()</code> | Завершує поточну функцію та повертає value[:i].rstrip() |
| 130 | <code>_yaml_comment</code> | <code>        i += 1</code> | Оновлює накопичене значення: i += 1 |
| 131 | <code>_yaml_comment</code> | <code>    return value.rstrip()</code> | Завершує поточну функцію та повертає value.rstrip() |
| 132 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 133 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 134 | <code>_strip_quotes</code> | <code>def _strip_quotes(value: str) -&gt; str:</code> | Оголошення функції `_strip_quotes` та її аргументів; детальний контракт розібраний вище. |
| 135 | <code>_strip_quotes</code> | <code>    value = _yaml_comment(value.strip())</code> | Обчислює та зберігає value ← _yaml_comment(value.strip()) |
| 136 | <code>_strip_quotes</code> | <code>    if not value or value[0] not in "\"'":</code> | Умовна гілка: not value or value[0] not in '"\''; відповідний block виконується тільки коли умова true. |
| 137 | <code>_strip_quotes</code> | <code>        return value</code> | Завершує поточну функцію та повертає value |
| 138 | <code>_strip_quotes</code> | <code>    quote = value[0]</code> | Обчислює та зберігає quote ← value[0] |
| 139 | <code>_strip_quotes</code> | <code>    output: List[str] = []</code> | Типізує output як List[str]; initial value [] |
| 140 | <code>_strip_quotes</code> | <code>    escapes = {"0": "\0", "a": "\a", "b": "\b", "t": "\t", "n": "\n",</code> | Обчислює та зберігає escapes ← {'0': '\x00', 'a': '\x07', 'b': '\x08', 't': '\t', 'n': '\n', 'v': '\x0b', 'f': '\x0c', 'r': '\r', 'e': '\x1b', ' ': ' ', '"': '"', '/': '/', '\\': '\\', 'N': '\x85', '_': '\xa0', 'L': '\u2028', 'P':… |
| 141 | <code>_strip_quotes</code> | <code>               "v": "\v", "f": "\f", "r": "\r", "e": "\x1b", " ": " ",</code> | Продовження інструкції 140: Обчислює та зберігає escapes ← {'0': '\x00', 'a': '\x07', 'b': '\x08', 't': '\t', 'n': '\n', 'v': '\x0b', 'f': '\x0c', 'r': '\r', 'e': '\x1b', ' ': ' ', '"': '"', '/': '/', '\\': '\\', 'N': '\x85', '_': '\xa0', 'L': '\u2028', 'P':… |
| 142 | <code>_strip_quotes</code> | <code>               '"': '"', "/": "/", "\\": "\\", "N": "\x85", "_": "\xa0",</code> | Продовження інструкції 140: Обчислює та зберігає escapes ← {'0': '\x00', 'a': '\x07', 'b': '\x08', 't': '\t', 'n': '\n', 'v': '\x0b', 'f': '\x0c', 'r': '\r', 'e': '\x1b', ' ': ' ', '"': '"', '/': '/', '\\': '\\', 'N': '\x85', '_': '\xa0', 'L': '\u2028', 'P':… |
| 143 | <code>_strip_quotes</code> | <code>               "L": "\u2028", "P": "\u2029"}</code> | Продовження інструкції 140: Обчислює та зберігає escapes ← {'0': '\x00', 'a': '\x07', 'b': '\x08', 't': '\t', 'n': '\n', 'v': '\x0b', 'f': '\x0c', 'r': '\r', 'e': '\x1b', ' ': ' ', '"': '"', '/': '/', '\\': '\\', 'N': '\x85', '_': '\xa0', 'L': '\u2028', 'P':… |
| 144 | <code>_strip_quotes</code> | <code>    i = 1</code> | Обчислює та зберігає i ← 1 |
| 145 | <code>_strip_quotes</code> | <code>    while i &lt; len(value):</code> | Продовжує цикл поки i &lt; len(value) |
| 146 | <code>_strip_quotes</code> | <code>        char = value[i]</code> | Обчислює та зберігає char ← value[i] |
| 147 | <code>_strip_quotes</code> | <code>        if char == quote:</code> | Умовна гілка: char == quote; відповідний block виконується тільки коли умова true. |
| 148 | <code>_strip_quotes</code> | <code>            if quote == "'" and value[i:i + 2] == "''":</code> | Умовна гілка: quote == "'" and value[i:i + 2] == "''"; відповідний block виконується тільки коли умова true. |
| 149 | <code>_strip_quotes</code> | <code>                output.append("'")</code> | Виконує виклик output.append: output.append("'") |
| 150 | <code>_strip_quotes</code> | <code>                i += 2</code> | Оновлює накопичене значення: i += 2 |
| 151 | <code>_strip_quotes</code> | <code>                continue</code> | Пропускає решту цієї ітерації; переходить до наступного елемента. |
| 152 | <code>_strip_quotes</code> | <code>            if value[i + 1:].strip():</code> | Умовна гілка: value[i + 1:].strip(); відповідний block виконується тільки коли умова true. |
| 153 | <code>_strip_quotes</code> | <code>                raise ValueError("text after a quoted scalar")</code> | Відхиляє unsupported/failed input або передає error вище: ValueError('text after a quoted scalar') |
| 154 | <code>_strip_quotes</code> | <code>            return "".join(output)</code> | Завершує поточну функцію та повертає ''.join(output) |
| 155 | <code>_strip_quotes</code> | <code>        if char == "\\" and quote == '"':</code> | Умовна гілка: char == '\\' and quote == '"'; відповідний block виконується тільки коли умова true. |
| 156 | <code>_strip_quotes</code> | <code>            i += 1</code> | Оновлює накопичене значення: i += 1 |
| 157 | <code>_strip_quotes</code> | <code>            if i &gt;= len(value):</code> | Умовна гілка: i &gt;= len(value); відповідний block виконується тільки коли умова true. |
| 158 | <code>_strip_quotes</code> | <code>                break</code> | Припиняє найближчий цикл; наступні елементи цього циклу не обробляються. |
| 159 | <code>_strip_quotes</code> | <code>            escaped = value[i]</code> | Обчислює та зберігає escaped ← value[i] |
| 160 | <code>_strip_quotes</code> | <code>            if escaped == "\n":</code> | Умовна гілка: escaped == '\n'; відповідний block виконується тільки коли умова true. |
| 161 | <code>_strip_quotes</code> | <code>                i += 1</code> | Оновлює накопичене значення: i += 1 |
| 162 | <code>_strip_quotes</code> | <code>                while i &lt; len(value) and value[i] in " \t":</code> | Продовжує цикл поки i &lt; len(value) and value[i] in ' \t' |
| 163 | <code>_strip_quotes</code> | <code>                    i += 1</code> | Оновлює накопичене значення: i += 1 |
| 164 | <code>_strip_quotes</code> | <code>                continue</code> | Пропускає решту цієї ітерації; переходить до наступного елемента. |
| 165 | <code>_strip_quotes</code> | <code>            if escaped in "xuU":</code> | Умовна гілка: escaped in 'xuU'; відповідний block виконується тільки коли умова true. |
| 166 | <code>_strip_quotes</code> | <code>                length = {"x": 2, "u": 4, "U": 8}[escaped]</code> | Обчислює та зберігає length ← {'x': 2, 'u': 4, 'U': 8}[escaped] |
| 167 | <code>_strip_quotes</code> | <code>                digits = value[i + 1:i + 1 + length]</code> | Обчислює та зберігає digits ← value[i + 1:i + 1 + length] |
| 168 | <code>_strip_quotes</code> | <code>                if len(digits) != length or not re.fullmatch(r"[0-9a-fA-F]+", digits):</code> | Умовна гілка: len(digits) != length or not re.fullmatch('[0-9a-fA-F]+', digits); відповідний block виконується тільки коли умова true. |
| 169 | <code>_strip_quotes</code> | <code>                    raise ValueError("invalid quoted Unicode escape")</code> | Відхиляє unsupported/failed input або передає error вище: ValueError('invalid quoted Unicode escape') |
| 170 | <code>_strip_quotes</code> | <code>                try:</code> | Межа обробки винятків: виконати block і застосувати specified handlers. |
| 171 | <code>_strip_quotes</code> | <code>                    codepoint = int(digits, 16)</code> | Обчислює та зберігає codepoint ← int(digits, 16) |
| 172 | <code>_strip_quotes</code> | <code>                    if 0xD800 &lt;= codepoint &lt;= 0xDFFF:</code> | Умовна гілка: 55296 &lt;= codepoint &lt;= 57343; відповідний block виконується тільки коли умова true. |
| 173 | <code>_strip_quotes</code> | <code>                        raise ValueError("surrogates are not Unicode scalar values")</code> | Відхиляє unsupported/failed input або передає error вище: ValueError('surrogates are not Unicode scalar values') |
| 174 | <code>_strip_quotes</code> | <code>                    output.append(chr(codepoint))</code> | Виконує виклик output.append: output.append(chr(codepoint)) |
| 175 | <code>_strip_quotes</code> | <code>                except ValueError:</code> | Handler для зазначеного типу винятку; operational finding/fallback залежить від body нижче. |
| 176 | <code>_strip_quotes</code> | <code>                    raise ValueError("invalid quoted Unicode code point")</code> | Відхиляє unsupported/failed input або передає error вище: ValueError('invalid quoted Unicode code point') |
| 177 | <code>_strip_quotes</code> | <code>                i += length + 1</code> | Оновлює накопичене значення: i += length + 1 |
| 178 | <code>_strip_quotes</code> | <code>                continue</code> | Пропускає решту цієї ітерації; переходить до наступного елемента. |
| 179 | <code>_strip_quotes</code> | <code>            if escaped not in escapes:</code> | Умовна гілка: escaped not in escapes; відповідний block виконується тільки коли умова true. |
| 180 | <code>_strip_quotes</code> | <code>                raise ValueError("unsupported or invalid quoted escape")</code> | Відхиляє unsupported/failed input або передає error вище: ValueError('unsupported or invalid quoted escape') |
| 181 | <code>_strip_quotes</code> | <code>            output.append(escapes[escaped])</code> | Виконує виклик output.append: output.append(escapes[escaped]) |
| 182 | <code>_strip_quotes</code> | <code>        elif char == "\n":</code> | Наступна умовна гілка, коли попередній if/elif не виконався. |
| 183 | <code>_strip_quotes</code> | <code>            # YAML folds ordinary line breaks in quoted scalars.</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 184 | <code>_strip_quotes</code> | <code>            while output and output[-1] in " \t":</code> | Продовжує цикл поки output and output[-1] in ' \t' |
| 185 | <code>_strip_quotes</code> | <code>                output.pop()</code> | Виконує виклик output.pop: output.pop() |
| 186 | <code>_strip_quotes</code> | <code>            breaks = 0</code> | Обчислює та зберігає breaks ← 0 |
| 187 | <code>_strip_quotes</code> | <code>            while i &lt; len(value) and value[i] == "\n":</code> | Продовжує цикл поки i &lt; len(value) and value[i] == '\n' |
| 188 | <code>_strip_quotes</code> | <code>                breaks += 1</code> | Оновлює накопичене значення: breaks += 1 |
| 189 | <code>_strip_quotes</code> | <code>                i += 1</code> | Оновлює накопичене значення: i += 1 |
| 190 | <code>_strip_quotes</code> | <code>                while i &lt; len(value) and value[i] in " \t":</code> | Продовжує цикл поки i &lt; len(value) and value[i] in ' \t' |
| 191 | <code>_strip_quotes</code> | <code>                    i += 1</code> | Оновлює накопичене значення: i += 1 |
| 192 | <code>_strip_quotes</code> | <code>            output.append("\n" * (breaks - 1) if breaks &gt; 1 else " ")</code> | Виконує виклик output.append: output.append('\n' * (breaks - 1) if breaks &gt; 1 else ' ') |
| 193 | <code>_strip_quotes</code> | <code>            continue</code> | Пропускає решту цієї ітерації; переходить до наступного елемента. |
| 194 | <code>_strip_quotes</code> | <code>        else:</code> | Alternative branch для попередньої умови або завершення циклу без break. |
| 195 | <code>_strip_quotes</code> | <code>            output.append(char)</code> | Виконує виклик output.append: output.append(char) |
| 196 | <code>_strip_quotes</code> | <code>        i += 1</code> | Оновлює накопичене значення: i += 1 |
| 197 | <code>_strip_quotes</code> | <code>    raise ValueError("unterminated quoted scalar")</code> | Відхиляє unsupported/failed input або передає error вище: ValueError('unterminated quoted scalar') |
| 198 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 199 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 200 | <code>_yaml_scalar</code> | <code>def _yaml_scalar(value: str) -&gt; _FrontmatterValue:</code> | Оголошення функції `_yaml_scalar` та її аргументів; детальний контракт розібраний вище. |
| 201 | <code>_yaml_scalar</code> | <code>    value = _yaml_comment(value.strip())</code> | Обчислює та зберігає value ← _yaml_comment(value.strip()) |
| 202 | <code>_yaml_scalar</code> | <code>    if value[:1] in ("'", '"'):</code> | Умовна гілка: value[:1] in ("'", '"'); відповідний block виконується тільки коли умова true. |
| 203 | <code>_yaml_scalar</code> | <code>        return _FrontmatterValue(_strip_quotes(value))</code> | Завершує поточну функцію та повертає _FrontmatterValue(_strip_quotes(value)) |
| 204 | <code>_yaml_scalar</code> | <code>    if value.startswith(("&amp;", "*", "!", "{", "?", "%", "@", "`", "&#124;", "&gt;")) or re.match(r"^-(?:\s&#124;$)", value):</code> | Умовна гілка: value.startswith(('&amp;', '*', '!', '{', '?', '%', '@', '`', '&#124;', '&gt;')) or re.match('^-(?:\\s&#124;$)', value); відповідний block виконується тільки коли умова true. |
| 205 | <code>_yaml_scalar</code> | <code>        raise ValueError("anchors, aliases, tags, flow mappings or reserved syntax are unsupported")</code> | Відхиляє unsupported/failed input або передає error вище: ValueError('anchors, aliases, tags, flow mappings or reserved syntax are unsupported') |
| 206 | <code>_yaml_scalar</code> | <code>    if value.startswith("["):</code> | Умовна гілка: value.startswith('['); відповідний block виконується тільки коли умова true. |
| 207 | <code>_yaml_scalar</code> | <code>        # A bounded flat sequence supports common tools/arguments list syntax.</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 208 | <code>_yaml_scalar</code> | <code>        if not value.endswith("]"):</code> | Умовна гілка: not value.endswith(']'); відповідний block виконується тільки коли умова true. |
| 209 | <code>_yaml_scalar</code> | <code>            raise ValueError("unterminated flow sequence")</code> | Відхиляє unsupported/failed input або передає error вище: ValueError('unterminated flow sequence') |
| 210 | <code>_yaml_scalar</code> | <code>        items: List[_FrontmatterValue] = []</code> | Типізує items як List[_FrontmatterValue]; initial value [] |
| 211 | <code>_yaml_scalar</code> | <code>        token: List[str] = []</code> | Типізує token як List[str]; initial value [] |
| 212 | <code>_yaml_scalar</code> | <code>        quote = None</code> | Обчислює та зберігає quote ← None |
| 213 | <code>_yaml_scalar</code> | <code>        escaped = False</code> | Обчислює та зберігає escaped ← False |
| 214 | <code>_yaml_scalar</code> | <code>        content = value[1:-1]</code> | Обчислює та зберігає content ← value[1:-1] |
| 215 | <code>_yaml_scalar</code> | <code>        for index, char in enumerate(content + ","):</code> | Ітерує enumerate(content + ',') і зв’язує кожен елемент із (index, char) |
| 216 | <code>_yaml_scalar</code> | <code>            if escaped:</code> | Умовна гілка: escaped; відповідний block виконується тільки коли умова true. |
| 217 | <code>_yaml_scalar</code> | <code>                token.append(char)</code> | Виконує виклик token.append: token.append(char) |
| 218 | <code>_yaml_scalar</code> | <code>                escaped = False</code> | Обчислює та зберігає escaped ← False |
| 219 | <code>_yaml_scalar</code> | <code>            elif quote == '"' and char == "\\":</code> | Наступна умовна гілка, коли попередній if/elif не виконався. |
| 220 | <code>_yaml_scalar</code> | <code>                token.append(char)</code> | Виконує виклик token.append: token.append(char) |
| 221 | <code>_yaml_scalar</code> | <code>                escaped = True</code> | Обчислює та зберігає escaped ← True |
| 222 | <code>_yaml_scalar</code> | <code>            elif quote:</code> | Наступна умовна гілка, коли попередній if/elif не виконався. |
| 223 | <code>_yaml_scalar</code> | <code>                token.append(char)</code> | Виконує виклик token.append: token.append(char) |
| 224 | <code>_yaml_scalar</code> | <code>                if char == quote:</code> | Умовна гілка: char == quote; відповідний block виконується тільки коли умова true. |
| 225 | <code>_yaml_scalar</code> | <code>                    quote = None</code> | Обчислює та зберігає quote ← None |
| 226 | <code>_yaml_scalar</code> | <code>            elif char in "\"'":</code> | Наступна умовна гілка, коли попередній if/elif не виконався. |
| 227 | <code>_yaml_scalar</code> | <code>                token.append(char)</code> | Виконує виклик token.append: token.append(char) |
| 228 | <code>_yaml_scalar</code> | <code>                quote = char</code> | Обчислює та зберігає quote ← char |
| 229 | <code>_yaml_scalar</code> | <code>            elif char == ",":</code> | Наступна умовна гілка, коли попередній if/elif не виконався. |
| 230 | <code>_yaml_scalar</code> | <code>                part = "".join(token).strip()</code> | Обчислює та зберігає part ← ''.join(token).strip() |
| 231 | <code>_yaml_scalar</code> | <code>                if part:</code> | Умовна гілка: part; відповідний block виконується тільки коли умова true. |
| 232 | <code>_yaml_scalar</code> | <code>                    if part[:1] not in ("'", '"') and any(char in part for char in "[]{}"):</code> | Умовна гілка: part[:1] not in ("'", '"') and any((char in part for char in '[]{}')); відповідний block виконується тільки коли умова true. |
| 233 | <code>_yaml_scalar</code> | <code>                        raise ValueError("flow delimiters inside plain sequence items are unsupported")</code> | Відхиляє unsupported/failed input або передає error вище: ValueError('flow delimiters inside plain sequence items are unsupported') |
| 234 | <code>_yaml_scalar</code> | <code>                    items.append(_yaml_scalar(part))</code> | Виконує виклик items.append: items.append(_yaml_scalar(part)) |
| 235 | <code>_yaml_scalar</code> | <code>                elif index &lt; len(content):</code> | Наступна умовна гілка, коли попередній if/elif не виконався. |
| 236 | <code>_yaml_scalar</code> | <code>                    raise ValueError("empty flow sequence items are invalid")</code> | Відхиляє unsupported/failed input або передає error вище: ValueError('empty flow sequence items are invalid') |
| 237 | <code>_yaml_scalar</code> | <code>                token = []</code> | Обчислює та зберігає token ← [] |
| 238 | <code>_yaml_scalar</code> | <code>            else:</code> | Alternative branch для попередньої умови або завершення циклу без break. |
| 239 | <code>_yaml_scalar</code> | <code>                token.append(char)</code> | Виконує виклик token.append: token.append(char) |
| 240 | <code>_yaml_scalar</code> | <code>        if quote:</code> | Умовна гілка: quote; відповідний block виконується тільки коли умова true. |
| 241 | <code>_yaml_scalar</code> | <code>            raise ValueError("unterminated quote in flow sequence")</code> | Відхиляє unsupported/failed input або передає error вище: ValueError('unterminated quote in flow sequence') |
| 242 | <code>_yaml_scalar</code> | <code>        return _FrontmatterValue(" ".join(items), "sequence", items)</code> | Завершує поточну функцію та повертає _FrontmatterValue(' '.join(items), 'sequence', items) |
| 243 | <code>_yaml_scalar</code> | <code>    if re.search(r":(?:\s&#124;$)", value):</code> | Умовна гілка: re.search(':(?:\\s&#124;$)', value); відповідний block виконується тільки коли умова true. |
| 244 | <code>_yaml_scalar</code> | <code>        raise ValueError("a plain scalar containing ': ' must be quoted")</code> | Відхиляє unsupported/failed input або передає error вище: ValueError("a plain scalar containing ': ' must be quoted") |
| 245 | <code>_yaml_scalar</code> | <code>    kind = "string"</code> | Обчислює та зберігає kind ← 'string' |
| 246 | <code>_yaml_scalar</code> | <code>    if not value or value.lower() in ("null", "~"):</code> | Умовна гілка: not value or value.lower() in ('null', '~'); відповідний block виконується тільки коли умова true. |
| 247 | <code>_yaml_scalar</code> | <code>        kind = "null"</code> | Обчислює та зберігає kind ← 'null' |
| 248 | <code>_yaml_scalar</code> | <code>    elif value.lower() in TRUE_WORDS &#124; FALSE_WORDS:</code> | Наступна умовна гілка, коли попередній if/elif не виконався. |
| 249 | <code>_yaml_scalar</code> | <code>        kind = "boolean"</code> | Обчислює та зберігає kind ← 'boolean' |
| 250 | <code>_yaml_scalar</code> | <code>    elif re.fullmatch(r"[-+]?(?:[0-9][0-9_]*(?:\.[0-9_]*)?(?:[eE][-+]?[0-9]+)?&#124;\.[0-9_]+&#124;0[xob][0-9a-fA-F_]+&#124;\.inf&#124;\.nan)", value, re.I):</code> | Наступна умовна гілка, коли попередній if/elif не виконався. |
| 251 | <code>_yaml_scalar</code> | <code>        kind = "number"</code> | Обчислює та зберігає kind ← 'number' |
| 252 | <code>_yaml_scalar</code> | <code>    elif re.match(r"^\d{4}-\d\d-\d\d(?:$&#124;[Tt ])", value):</code> | Наступна умовна гілка, коли попередній if/elif не виконався. |
| 253 | <code>_yaml_scalar</code> | <code>        kind = "timestamp"</code> | Обчислює та зберігає kind ← 'timestamp' |
| 254 | <code>_yaml_scalar</code> | <code>    return _FrontmatterValue(value, kind)</code> | Завершує поточну функцію та повертає _FrontmatterValue(value, kind) |
| 255 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 256 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 257 | <code>_yaml_key</code> | <code>def _yaml_key(value: str) -&gt; str:</code> | Оголошення функції `_yaml_key` та її аргументів; детальний контракт розібраний вище. |
| 258 | <code>_yaml_key</code> | <code>    """Keep mapping keys as YAML strings, including explicitly quoted keys."""</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 259 | <code>_yaml_key</code> | <code>    key = _yaml_scalar(value)</code> | Обчислює та зберігає key ← _yaml_scalar(value) |
| 260 | <code>_yaml_key</code> | <code>    if key.kind != "string":</code> | Умовна гілка: key.kind != 'string'; відповідний block виконується тільки коли умова true. |
| 261 | <code>_yaml_key</code> | <code>        raise ValueError("mapping keys must be strings; quote boolean or null-looking keys")</code> | Відхиляє unsupported/failed input або передає error вище: ValueError('mapping keys must be strings; quote boolean or null-looking keys') |
| 262 | <code>_yaml_key</code> | <code>    return str(key)</code> | Завершує поточну функцію та повертає str(key) |
| 263 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 264 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 265 | <code>_yaml_block</code> | <code>def _yaml_block(value: str, children: List[str]) -&gt; _FrontmatterValue:</code> | Оголошення функції `_yaml_block` та її аргументів; детальний контракт розібраний вище. |
| 266 | <code>_yaml_block</code> | <code>    nonempty = [line for line in children if line.strip()]</code> | Обчислює та зберігає nonempty ← [line for line in children if line.strip()] |
| 267 | <code>_yaml_block</code> | <code>    indent = len(nonempty[0]) - len(nonempty[0].lstrip(" ")) if nonempty else 0</code> | Обчислює та зберігає indent ← len(nonempty[0]) - len(nonempty[0].lstrip(' ')) if nonempty else 0 |
| 268 | <code>_yaml_block</code> | <code>    if any(len(line) - len(line.lstrip(" ")) &lt; indent for line in nonempty):</code> | Умовна гілка: any((len(line) - len(line.lstrip(' ')) &lt; indent for line in nonempty)); відповідний block виконується тільки коли умова true. |
| 269 | <code>_yaml_block</code> | <code>        raise ValueError("block scalar indentation is inconsistent")</code> | Відхиляє unsupported/failed input або передає error вище: ValueError('block scalar indentation is inconsistent') |
| 270 | <code>_yaml_block</code> | <code>    block = [line[indent:] if line.strip() else "" for line in children]</code> | Обчислює та зберігає block ← [line[indent:] if line.strip() else '' for line in children] |
| 271 | <code>_yaml_block</code> | <code>    if value.startswith("&#124;"):</code> | Умовна гілка: value.startswith('&#124;'); відповідний block виконується тільки коли умова true. |
| 272 | <code>_yaml_block</code> | <code>        result = "\n".join(block)</code> | Обчислює та зберігає result ← '\n'.join(block) |
| 273 | <code>_yaml_block</code> | <code>    else:</code> | Alternative branch для попередньої умови або завершення циклу без break. |
| 274 | <code>_yaml_block</code> | <code>        result = ""</code> | Обчислює та зберігає result ← '' |
| 275 | <code>_yaml_block</code> | <code>        last_content = max((i for i, line in enumerate(block) if line), default=-1)</code> | Обчислює та зберігає last_content ← max((i for i, line in enumerate(block) if line), default=-1) |
| 276 | <code>_yaml_block</code> | <code>        for i, line in enumerate(block):</code> | Ітерує enumerate(block) і зв’язує кожен елемент із (i, line) |
| 277 | <code>_yaml_block</code> | <code>            result += line</code> | Оновлює накопичене значення: result += line |
| 278 | <code>_yaml_block</code> | <code>            if i + 1 &lt; len(block):</code> | Умовна гілка: i + 1 &lt; len(block); відповідний block виконується тільки коли умова true. |
| 279 | <code>_yaml_block</code> | <code>                following = block[i + 1]</code> | Обчислює та зберігає following ← block[i + 1] |
| 280 | <code>_yaml_block</code> | <code>                if line and following and not line.startswith(" ") and not following.startswith(" "):</code> | Умовна гілка: line and following and (not line.startswith(' ')) and (not following.startswith(' ')); відповідний block виконується тільки коли умова true. |
| 281 | <code>_yaml_block</code> | <code>                    result += " "</code> | Оновлює накопичене значення: result += ' ' |
| 282 | <code>_yaml_block</code> | <code>                elif not following and line and not line.startswith(" ") and i + 1 &lt; last_content:</code> | Наступна умовна гілка, коли попередній if/elif не виконався. |
| 283 | <code>_yaml_block</code> | <code>                    # The following blank line supplies the paragraph break.</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 284 | <code>_yaml_block</code> | <code>                    pass</code> | Свідомо порожня гілка; state/output на цьому кроці не змінюється. |
| 285 | <code>_yaml_block</code> | <code>                else:</code> | Alternative branch для попередньої умови або завершення циклу без break. |
| 286 | <code>_yaml_block</code> | <code>                    result += "\n"</code> | Оновлює накопичене значення: result += '\n' |
| 287 | <code>_yaml_block</code> | <code>    # Empty children produce the empty string. Default clip retains one newline.</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 288 | <code>_yaml_block</code> | <code>    if "-" in value:</code> | Умовна гілка: '-' in value; відповідний block виконується тільки коли умова true. |
| 289 | <code>_yaml_block</code> | <code>        result = result.rstrip("\n")</code> | Обчислює та зберігає result ← result.rstrip('\n') |
| 290 | <code>_yaml_block</code> | <code>    elif "+" not in value and children:</code> | Наступна умовна гілка, коли попередній if/elif не виконався. |
| 291 | <code>_yaml_block</code> | <code>        result = result.rstrip("\n") + "\n"</code> | Обчислює та зберігає result ← result.rstrip('\n') + '\n' |
| 292 | <code>_yaml_block</code> | <code>    elif children:</code> | Наступна умовна гілка, коли попередній if/elif не виконався. |
| 293 | <code>_yaml_block</code> | <code>        result += "\n"</code> | Оновлює накопичене значення: result += '\n' |
| 294 | <code>_yaml_block</code> | <code>    return _FrontmatterValue(result)</code> | Завершує поточну функцію та повертає _FrontmatterValue(result) |
| 295 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 296 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 297 | <code>parse_frontmatter</code> | <code>def parse_frontmatter(text: str) -&gt; Tuple[Dict[str, str], str, List[str]]:</code> | Оголошення функції `parse_frontmatter` та її аргументів; детальний контракт розібраний вище. |
| 298 | <code>parse_frontmatter</code> | <code>    """Parse a bounded YAML subset, reporting invalid/unsupported syntax.</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 299 | <code>parse_frontmatter</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 300 | <code>parse_frontmatter</code> | <code>    Supports scalar strings, flat lists and shallow metadata maps. This is not</code> | Продовження інструкції 298: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 301 | <code>parse_frontmatter</code> | <code>    a full YAML validator. Unsupported syntax discards the metadata rather than</code> | Продовження інструкції 298: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 302 | <code>parse_frontmatter</code> | <code>    supplying apparently valid values to the audit.</code> | Продовження інструкції 298: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 303 | <code>parse_frontmatter</code> | <code>    """</code> | Продовження інструкції 298: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 304 | <code>parse_frontmatter</code> | <code>    problems: List[str] = []</code> | Типізує problems як List[str]; initial value [] |
| 305 | <code>parse_frontmatter</code> | <code>    lines = text.splitlines()</code> | Обчислює та зберігає lines ← text.splitlines() |
| 306 | <code>parse_frontmatter</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 307 | <code>parse_frontmatter</code> | <code>    if not lines or lines[0].strip() != "---":</code> | Умовна гілка: not lines or lines[0].strip() != '---'; відповідний block виконується тільки коли умова true. |
| 308 | <code>parse_frontmatter</code> | <code>        # Claude Code reads frontmatter only when `---` is the very first line.</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 309 | <code>parse_frontmatter</code> | <code>        # Anything else and the whole file, markers included, becomes body.</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 310 | <code>parse_frontmatter</code> | <code>        if any(line.strip() == "---" for line in lines[:20]):</code> | Умовна гілка: any((line.strip() == '---' for line in lines[:20])); відповідний block виконується тільки коли умова true. |
| 311 | <code>parse_frontmatter</code> | <code>            problems.append("frontmatter-not-first-line")</code> | Виконує виклик problems.append: problems.append('frontmatter-not-first-line') |
| 312 | <code>parse_frontmatter</code> | <code>        else:</code> | Alternative branch для попередньої умови або завершення циклу без break. |
| 313 | <code>parse_frontmatter</code> | <code>            problems.append("no-frontmatter")</code> | Виконує виклик problems.append: problems.append('no-frontmatter') |
| 314 | <code>parse_frontmatter</code> | <code>        return {}, text, problems</code> | Завершує поточну функцію та повертає ({}, text, problems) |
| 315 | <code>parse_frontmatter</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 316 | <code>parse_frontmatter</code> | <code>    end = None</code> | Обчислює та зберігає end ← None |
| 317 | <code>parse_frontmatter</code> | <code>    for i in range(1, len(lines)):</code> | Ітерує range(1, len(lines)) і зв’язує кожен елемент із i |
| 318 | <code>parse_frontmatter</code> | <code>        if lines[i].rstrip() in ("---", "..."):</code> | Умовна гілка: lines[i].rstrip() in ('---', '...'); відповідний block виконується тільки коли умова true. |
| 319 | <code>parse_frontmatter</code> | <code>            end = i</code> | Обчислює та зберігає end ← i |
| 320 | <code>parse_frontmatter</code> | <code>            break</code> | Припиняє найближчий цикл; наступні елементи цього циклу не обробляються. |
| 321 | <code>parse_frontmatter</code> | <code>    if end is None:</code> | Умовна гілка: end is None; відповідний block виконується тільки коли умова true. |
| 322 | <code>parse_frontmatter</code> | <code>        problems.append("unterminated-frontmatter")</code> | Виконує виклик problems.append: problems.append('unterminated-frontmatter') |
| 323 | <code>parse_frontmatter</code> | <code>        return {}, text, problems</code> | Завершує поточну функцію та повертає ({}, text, problems) |
| 324 | <code>parse_frontmatter</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 325 | <code>parse_frontmatter</code> | <code>    body = "\n".join(lines[end + 1:])</code> | Обчислює та зберігає body ← '\n'.join(lines[end + 1:]) |
| 326 | <code>parse_frontmatter</code> | <code>    if any(ord(char) &lt; 32 and char != "\t" or ord(char) == 127</code> | Умовна гілка: any((ord(char) &lt; 32 and char != '\t' or ord(char) == 127 for line in lines[1:end] for char in line)); відповідний block виконується тільки коли умова true. |
| 327 | <code>parse_frontmatter</code> | <code>           for line in lines[1:end] for char in line):</code> | Продовження інструкції 326: Умовна гілка: any((ord(char) &lt; 32 and char != '\t' or ord(char) == 127 for line in lines[1:end] for char in line)); відповідний block виконується тільки коли умова true. |
| 328 | <code>parse_frontmatter</code> | <code>        return {}, body, ["invalid-frontmatter: literal control character in YAML"]</code> | Завершує поточну функцію та повертає ({}, body, ['invalid-frontmatter: literal control character in YAML']) |
| 329 | <code>parse_frontmatter</code> | <code>    fm: Dict[str, str] = {}</code> | Типізує fm як Dict[str, str]; initial value {} |
| 330 | <code>parse_frontmatter</code> | <code>    i = 1</code> | Обчислює та зберігає i ← 1 |
| 331 | <code>parse_frontmatter</code> | <code>    while i &lt; end:</code> | Продовжує цикл поки i &lt; end |
| 332 | <code>parse_frontmatter</code> | <code>        raw = lines[i]</code> | Обчислює та зберігає raw ← lines[i] |
| 333 | <code>parse_frontmatter</code> | <code>        if not raw.strip() or raw.lstrip().startswith("#"):</code> | Умовна гілка: not raw.strip() or raw.lstrip().startswith('#'); відповідний block виконується тільки коли умова true. |
| 334 | <code>parse_frontmatter</code> | <code>            i += 1</code> | Оновлює накопичене значення: i += 1 |
| 335 | <code>parse_frontmatter</code> | <code>            continue</code> | Пропускає решту цієї ітерації; переходить до наступного елемента. |
| 336 | <code>parse_frontmatter</code> | <code>        match = _KEY_RE.match(raw)</code> | Обчислює та зберігає match ← _KEY_RE.match(raw) |
| 337 | <code>parse_frontmatter</code> | <code>        if not match:</code> | Умовна гілка: not match; відповідний block виконується тільки коли умова true. |
| 338 | <code>parse_frontmatter</code> | <code>            problems.append("invalid-frontmatter: line {}: expected a top-level scalar key".format(i + 1))</code> | Виконує виклик problems.append: problems.append('invalid-frontmatter: line {}: expected a top-level scalar key'.format(i + 1)) |
| 339 | <code>parse_frontmatter</code> | <code>            return {}, body, problems</code> | Завершує поточну функцію та повертає ({}, body, problems) |
| 340 | <code>parse_frontmatter</code> | <code>        start = i</code> | Обчислює та зберігає start ← i |
| 341 | <code>parse_frontmatter</code> | <code>        i += 1</code> | Оновлює накопичене значення: i += 1 |
| 342 | <code>parse_frontmatter</code> | <code>        value = _yaml_comment(match.group(2).strip())</code> | Обчислює та зберігає value ← _yaml_comment(match.group(2).strip()) |
| 343 | <code>parse_frontmatter</code> | <code>        children: List[str] = []</code> | Типізує children як List[str]; initial value [] |
| 344 | <code>parse_frontmatter</code> | <code>        while i &lt; end and (not lines[i].strip() or lines[i][:1] in (" ", "\t")</code> | Продовжує цикл поки i &lt; end and (not lines[i].strip() or lines[i][:1] in (' ', '\t') or (not value and (lines[i].startswith('- ') or lines[i].lstrip().startswith('#')))) |
| 345 | <code>parse_frontmatter</code> | <code>                           or (not value and (lines[i].startswith("- ")</code> | Продовження інструкції 344: Продовжує цикл поки i &lt; end and (not lines[i].strip() or lines[i][:1] in (' ', '\t') or (not value and (lines[i].startswith('- ') or lines[i].lstrip().startswith('#')))) |
| 346 | <code>parse_frontmatter</code> | <code>                                              or lines[i].lstrip().startswith("#")))):</code> | Продовження інструкції 344: Продовжує цикл поки i &lt; end and (not lines[i].strip() or lines[i][:1] in (' ', '\t') or (not value and (lines[i].startswith('- ') or lines[i].lstrip().startswith('#')))) |
| 347 | <code>parse_frontmatter</code> | <code>            children.append(lines[i])</code> | Виконує виклик children.append: children.append(lines[i]) |
| 348 | <code>parse_frontmatter</code> | <code>            i += 1</code> | Оновлює накопичене значення: i += 1 |
| 349 | <code>parse_frontmatter</code> | <code>        try:</code> | Межа обробки винятків: виконати block і застосувати specified handlers. |
| 350 | <code>parse_frontmatter</code> | <code>            if any(line.startswith("\t") or re.match(r"^ +\t", line) for line in children):</code> | Умовна гілка: any((line.startswith('\t') or re.match('^ +\\t', line) for line in children)); відповідний block виконується тільки коли умова true. |
| 351 | <code>parse_frontmatter</code> | <code>                raise ValueError("tabs are not valid YAML indentation")</code> | Відхиляє unsupported/failed input або передає error вище: ValueError('tabs are not valid YAML indentation') |
| 352 | <code>parse_frontmatter</code> | <code>            key = _yaml_key(match.group(1))</code> | Обчислює та зберігає key ← _yaml_key(match.group(1)) |
| 353 | <code>parse_frontmatter</code> | <code>            if key in fm:</code> | Умовна гілка: key in fm; відповідний block виконується тільки коли умова true. |
| 354 | <code>parse_frontmatter</code> | <code>                raise ValueError("duplicate key '{}'".format(key))</code> | Відхиляє unsupported/failed input або передає error вище: ValueError("duplicate key '{}'".format(key)) |
| 355 | <code>parse_frontmatter</code> | <code>            meaningful = [line for line in children if line.strip() and not line.lstrip().startswith("#")]</code> | Обчислює та зберігає meaningful ← [line for line in children if line.strip() and (not line.lstrip().startswith('#'))] |
| 356 | <code>parse_frontmatter</code> | <code>            if value in ("&#124;", "&gt;", "&#124;-", "&gt;-", "&#124;+", "&gt;+"):</code> | Умовна гілка: value in ('&#124;', '&gt;', '&#124;-', '&gt;-', '&#124;+', '&gt;+'); відповідний block виконується тільки коли умова true. |
| 357 | <code>parse_frontmatter</code> | <code>                fm[key] = _yaml_block(value, children)</code> | Обчислює та зберігає fm[key] ← _yaml_block(value, children) |
| 358 | <code>parse_frontmatter</code> | <code>            elif value == "" and meaningful:</code> | Наступна умовна гілка, коли попередній if/elif не виконався. |
| 359 | <code>parse_frontmatter</code> | <code>                indent = len(meaningful[0]) - len(meaningful[0].lstrip(" "))</code> | Обчислює та зберігає indent ← len(meaningful[0]) - len(meaningful[0].lstrip(' ')) |
| 360 | <code>parse_frontmatter</code> | <code>                if any(len(line) - len(line.lstrip(" ")) != indent for line in meaningful):</code> | Умовна гілка: any((len(line) - len(line.lstrip(' ')) != indent for line in meaningful)); відповідний block виконується тільки коли умова true. |
| 361 | <code>parse_frontmatter</code> | <code>                    raise ValueError("nested or uneven collection indentation is unsupported")</code> | Відхиляє unsupported/failed input або передає error вище: ValueError('nested or uneven collection indentation is unsupported') |
| 362 | <code>parse_frontmatter</code> | <code>                if meaningful[0].lstrip().startswith("-"):</code> | Умовна гілка: meaningful[0].lstrip().startswith('-'); відповідний block виконується тільки коли умова true. |
| 363 | <code>parse_frontmatter</code> | <code>                    items = []</code> | Обчислює та зберігає items ← [] |
| 364 | <code>parse_frontmatter</code> | <code>                    for line in meaningful:</code> | Ітерує meaningful і зв’язує кожен елемент із line |
| 365 | <code>parse_frontmatter</code> | <code>                        item = re.fullmatch(r"\s*-\s+(.*)", line)</code> | Обчислює та зберігає item ← re.fullmatch('\\s*-\\s+(.*)', line) |
| 366 | <code>parse_frontmatter</code> | <code>                        if not item:</code> | Умовна гілка: not item; відповідний block виконується тільки коли умова true. |
| 367 | <code>parse_frontmatter</code> | <code>                            raise ValueError("invalid block sequence item")</code> | Відхиляє unsupported/failed input або передає error вище: ValueError('invalid block sequence item') |
| 368 | <code>parse_frontmatter</code> | <code>                        parsed = _yaml_scalar(item.group(1))</code> | Обчислює та зберігає parsed ← _yaml_scalar(item.group(1)) |
| 369 | <code>parse_frontmatter</code> | <code>                        if parsed.kind == "sequence":</code> | Умовна гілка: parsed.kind == 'sequence'; відповідний block виконується тільки коли умова true. |
| 370 | <code>parse_frontmatter</code> | <code>                            raise ValueError("nested collections are unsupported")</code> | Відхиляє unsupported/failed input або передає error вище: ValueError('nested collections are unsupported') |
| 371 | <code>parse_frontmatter</code> | <code>                        items.append(parsed)</code> | Виконує виклик items.append: items.append(parsed) |
| 372 | <code>parse_frontmatter</code> | <code>                    fm[key] = _FrontmatterValue(" ".join(items), "sequence", items)</code> | Обчислює та зберігає fm[key] ← _FrontmatterValue(' '.join(items), 'sequence', items) |
| 373 | <code>parse_frontmatter</code> | <code>                elif key == "metadata":</code> | Наступна умовна гілка, коли попередній if/elif не виконався. |
| 374 | <code>parse_frontmatter</code> | <code>                    members = {}</code> | Обчислює та зберігає members ← {} |
| 375 | <code>parse_frontmatter</code> | <code>                    for line in meaningful:</code> | Ітерує meaningful і зв’язує кожен елемент із line |
| 376 | <code>parse_frontmatter</code> | <code>                        item = _KEY_RE.match(line.lstrip())</code> | Обчислює та зберігає item ← _KEY_RE.match(line.lstrip()) |
| 377 | <code>parse_frontmatter</code> | <code>                        if not item:</code> | Умовна гілка: not item; відповідний block виконується тільки коли умова true. |
| 378 | <code>parse_frontmatter</code> | <code>                            raise ValueError("invalid metadata mapping entry")</code> | Відхиляє unsupported/failed input або передає error вище: ValueError('invalid metadata mapping entry') |
| 379 | <code>parse_frontmatter</code> | <code>                        member = _yaml_key(item.group(1))</code> | Обчислює та зберігає member ← _yaml_key(item.group(1)) |
| 380 | <code>parse_frontmatter</code> | <code>                        if member in members:</code> | Умовна гілка: member in members; відповідний block виконується тільки коли умова true. |
| 381 | <code>parse_frontmatter</code> | <code>                            raise ValueError("duplicate metadata key")</code> | Відхиляє unsupported/failed input або передає error вище: ValueError('duplicate metadata key') |
| 382 | <code>parse_frontmatter</code> | <code>                        members[member] = _yaml_scalar(item.group(2))</code> | Обчислює та зберігає members[member] ← _yaml_scalar(item.group(2)) |
| 383 | <code>parse_frontmatter</code> | <code>                    fm[key] = _FrontmatterValue(" ".join(members), "mapping", members)</code> | Обчислює та зберігає fm[key] ← _FrontmatterValue(' '.join(members), 'mapping', members) |
| 384 | <code>parse_frontmatter</code> | <code>                else:</code> | Alternative branch для попередньої умови або завершення циклу без break. |
| 385 | <code>parse_frontmatter</code> | <code>                    raise ValueError("only shallow metadata maps are supported")</code> | Відхиляє unsupported/failed input або передає error вище: ValueError('only shallow metadata maps are supported') |
| 386 | <code>parse_frontmatter</code> | <code>            elif value[:1] in ("'", '"'):</code> | Наступна умовна гілка, коли попередній if/elif не виконався. |
| 387 | <code>parse_frontmatter</code> | <code>                fm[key] = _yaml_scalar("\n".join([value] + children))</code> | Обчислює та зберігає fm[key] ← _yaml_scalar('\n'.join([value] + children)) |
| 388 | <code>parse_frontmatter</code> | <code>            else:</code> | Alternative branch для попередньої умови або завершення циклу без break. |
| 389 | <code>parse_frontmatter</code> | <code>                first = _yaml_scalar(value)</code> | Обчислює та зберігає first ← _yaml_scalar(value) |
| 390 | <code>parse_frontmatter</code> | <code>                if first.kind == "sequence" and meaningful:</code> | Умовна гілка: first.kind == 'sequence' and meaningful; відповідний block виконується тільки коли умова true. |
| 391 | <code>parse_frontmatter</code> | <code>                    raise ValueError("a flow sequence cannot have scalar continuation lines")</code> | Відхиляє unsupported/failed input або передає error вище: ValueError('a flow sequence cannot have scalar continuation lines') |
| 392 | <code>parse_frontmatter</code> | <code>                rendered = str(first)</code> | Обчислює та зберігає rendered ← str(first) |
| 393 | <code>parse_frontmatter</code> | <code>                blank_lines = 0</code> | Обчислює та зберігає blank_lines ← 0 |
| 394 | <code>parse_frontmatter</code> | <code>                for line in children:</code> | Ітерує children і зв’язує кожен елемент із line |
| 395 | <code>parse_frontmatter</code> | <code>                    if line.lstrip().startswith("#"):</code> | Умовна гілка: line.lstrip().startswith('#'); відповідний block виконується тільки коли умова true. |
| 396 | <code>parse_frontmatter</code> | <code>                        continue</code> | Пропускає решту цієї ітерації; переходить до наступного елемента. |
| 397 | <code>parse_frontmatter</code> | <code>                    if not line.strip():</code> | Умовна гілка: not line.strip(); відповідний block виконується тільки коли умова true. |
| 398 | <code>parse_frontmatter</code> | <code>                        blank_lines += 1</code> | Оновлює накопичене значення: blank_lines += 1 |
| 399 | <code>parse_frontmatter</code> | <code>                        continue</code> | Пропускає решту цієї ітерації; переходить до наступного елемента. |
| 400 | <code>parse_frontmatter</code> | <code>                    # Continuation text belongs to the existing plain scalar:</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 401 | <code>parse_frontmatter</code> | <code>                    # quotes, numbers and YAML-looking words stay literal text.</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 402 | <code>parse_frontmatter</code> | <code>                    part = re.split(r"\s+#", line.strip(), maxsplit=1)[0].rstrip()</code> | Обчислює та зберігає part ← re.split('\\s+#', line.strip(), maxsplit=1)[0].rstrip() |
| 403 | <code>parse_frontmatter</code> | <code>                    if re.search(r":(?:\s&#124;$)", part):</code> | Умовна гілка: re.search(':(?:\\s&#124;$)', part); відповідний block виконується тільки коли умова true. |
| 404 | <code>parse_frontmatter</code> | <code>                        raise ValueError("a plain scalar containing ': ' must be quoted")</code> | Відхиляє unsupported/failed input або передає error вище: ValueError("a plain scalar containing ': ' must be quoted") |
| 405 | <code>parse_frontmatter</code> | <code>                    rendered += ("\n" * blank_lines if blank_lines else " ") + part</code> | Оновлює накопичене значення: rendered += ('\n' * blank_lines if blank_lines else ' ') + part |
| 406 | <code>parse_frontmatter</code> | <code>                    blank_lines = 0</code> | Обчислює та зберігає blank_lines ← 0 |
| 407 | <code>parse_frontmatter</code> | <code>                fm[key] = _FrontmatterValue(rendered) if meaningful else first</code> | Обчислює та зберігає fm[key] ← _FrontmatterValue(rendered) if meaningful else first |
| 408 | <code>parse_frontmatter</code> | <code>        except ValueError as exc:</code> | Handler для зазначеного типу винятку; operational finding/fallback залежить від body нижче. |
| 409 | <code>parse_frontmatter</code> | <code>            problems.append("invalid-frontmatter: line {}: {}".format(start + 1, exc))</code> | Виконує виклик problems.append: problems.append('invalid-frontmatter: line {}: {}'.format(start + 1, exc)) |
| 410 | <code>parse_frontmatter</code> | <code>            return {}, body, problems</code> | Завершує поточну функцію та повертає ({}, body, problems) |
| 411 | <code>parse_frontmatter</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 412 | <code>parse_frontmatter</code> | <code>    return fm, body, problems</code> | Завершує поточну функцію та повертає (fm, body, problems) |
| 413 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 414 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 415 | <code>&lt;module&gt;</code> | <code># --- Discovery ------------------------------------------------------------</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 416 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 417 | <code>Skill</code> | <code>@dataclass</code> | Decorator змінює створення class/function (dataclass або property). |
| 418 | <code>Skill</code> | <code>class Skill:</code> | Оголошення класу `Skill` та базових класів; модель даних/поведінка розібрана вище. |
| 419 | <code>Skill</code> | <code>    path: Path</code> | Типізує path як Path |
| 420 | <code>Skill</code> | <code>    root: Path</code> | Типізує root як Path |
| 421 | <code>Skill</code> | <code>    origin: str                      # personal &#124; project &#124; plugin &#124; scanned</code> | Типізує origin як str |
| 422 | <code>Skill</code> | <code>    command: str                     # what you type to invoke it</code> | Типізує command як str |
| 423 | <code>Skill</code> | <code>    frontmatter: Dict[str, str]</code> | Типізує frontmatter як Dict[str, str] |
| 424 | <code>Skill</code> | <code>    body: str</code> | Типізує body як str |
| 425 | <code>Skill</code> | <code>    problems: List[str] = field(default_factory=list)</code> | Типізує problems як List[str]; initial value field(default_factory=list) |
| 426 | <code>Skill</code> | <code>    plugin: Optional[str] = None</code> | Типізує plugin як Optional[str]; initial value None |
| 427 | <code>Skill</code> | <code>    bundle_bytes: int = 0</code> | Типізує bundle_bytes як int; initial value 0 |
| 428 | <code>Skill</code> | <code>    kind: str = "skill"              # skill &#124; command (a commands/*.md file)</code> | Типізує kind як str; initial value 'skill' |
| 429 | <code>Skill</code> | <code>    override: Optional[str] = None   # skillOverrides state from settings, if any</code> | Типізує override як Optional[str]; initial value None |
| 430 | <code>Skill</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 431 | <code>Skill.description</code> | <code>    @property</code> | Decorator змінює створення class/function (dataclass або property). |
| 432 | <code>Skill.description</code> | <code>    def description(self) -&gt; str:</code> | Оголошення функції `description` та її аргументів; детальний контракт розібраний вище. |
| 433 | <code>Skill.description</code> | <code>        return self.frontmatter.get("description", "").strip()</code> | Завершує поточну функцію та повертає self.frontmatter.get('description', '').strip() |
| 434 | <code>Skill</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 435 | <code>Skill.when_to_use</code> | <code>    @property</code> | Decorator змінює створення class/function (dataclass або property). |
| 436 | <code>Skill.when_to_use</code> | <code>    def when_to_use(self) -&gt; str:</code> | Оголошення функції `when_to_use` та її аргументів; детальний контракт розібраний вище. |
| 437 | <code>Skill.when_to_use</code> | <code>        return self.frontmatter.get("when_to_use", "").strip()</code> | Завершує поточну функцію та повертає self.frontmatter.get('when_to_use', '').strip() |
| 438 | <code>Skill</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 439 | <code>Skill.routing_text</code> | <code>    @property</code> | Decorator змінює створення class/function (dataclass або property). |
| 440 | <code>Skill.routing_text</code> | <code>    def routing_text(self) -&gt; str:</code> | Оголошення функції `routing_text` та її аргументів; детальний контракт розібраний вище. |
| 441 | <code>Skill.routing_text</code> | <code>        """What the listing shows after the name: description + when_to_use, or,</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 442 | <code>Skill.routing_text</code> | <code>        with no description, the first non-empty line of the body (as documented)."""</code> | Продовження інструкції 441: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 443 | <code>Skill.routing_text</code> | <code>        description = self.description</code> | Обчислює та зберігає description ← self.description |
| 444 | <code>Skill.routing_text</code> | <code>        if not description:</code> | Умовна гілка: not description; відповідний block виконується тільки коли умова true. |
| 445 | <code>Skill.routing_text</code> | <code>            for line in self.body.splitlines():</code> | Ітерує self.body.splitlines() і зв’язує кожен елемент із line |
| 446 | <code>Skill.routing_text</code> | <code>                if line.strip():</code> | Умовна гілка: line.strip(); відповідний block виконується тільки коли умова true. |
| 447 | <code>Skill.routing_text</code> | <code>                    description = line.strip().lstrip("#").strip()</code> | Обчислює та зберігає description ← line.strip().lstrip('#').strip() |
| 448 | <code>Skill.routing_text</code> | <code>                    break</code> | Припиняє найближчий цикл; наступні елементи цього циклу не обробляються. |
| 449 | <code>Skill.routing_text</code> | <code>        return " ".join(p for p in (description, self.when_to_use) if p)</code> | Завершує поточну функцію та повертає ' '.join((p for p in (description, self.when_to_use) if p)) |
| 450 | <code>Skill</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 451 | <code>Skill.in_listing</code> | <code>    @property</code> | Decorator змінює створення class/function (dataclass або property). |
| 452 | <code>Skill.in_listing</code> | <code>    def in_listing(self) -&gt; bool:</code> | Оголошення функції `in_listing` та її аргументів; детальний контракт розібраний вище. |
| 453 | <code>Skill.in_listing</code> | <code>        """Whether the skill is advertised to the model at all.</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 454 | <code>Skill.in_listing</code> | <code>        `disable-model-invocation: true` and the skillOverrides states "off" and</code> | Продовження інструкції 453: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 455 | <code>Skill.in_listing</code> | <code>        "user-invocable-only" keep it out of context entirely."""</code> | Продовження інструкції 453: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 456 | <code>Skill.in_listing</code> | <code>        if self.override in ("off", "user-invocable-only"):</code> | Умовна гілка: self.override in ('off', 'user-invocable-only'); відповідний block виконується тільки коли умова true. |
| 457 | <code>Skill.in_listing</code> | <code>            return False</code> | Завершує поточну функцію та повертає False |
| 458 | <code>Skill.in_listing</code> | <code>        return _truthy(self.frontmatter.get("disable-model-invocation", "false")) is not True</code> | Завершує поточну функцію та повертає _truthy(self.frontmatter.get('disable-model-invocation', 'false')) is not True |
| 459 | <code>Skill</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 460 | <code>Skill.listing_text</code> | <code>    @property</code> | Decorator змінює створення class/function (dataclass або property). |
| 461 | <code>Skill.listing_text</code> | <code>    def listing_text(self) -&gt; str:</code> | Оголошення функції `listing_text` та її аргументів; детальний контракт розібраний вище. |
| 462 | <code>Skill.listing_text</code> | <code>        """The text the harness puts in the always-on skill listing."""</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 463 | <code>Skill.listing_text</code> | <code>        return ": ".join(p for p in (self.command, self.routing_text) if p)</code> | Завершує поточну функцію та повертає ': '.join((p for p in (self.command, self.routing_text) if p)) |
| 464 | <code>Skill</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 465 | <code>Skill.body_lines</code> | <code>    @property</code> | Decorator змінює створення class/function (dataclass або property). |
| 466 | <code>Skill.body_lines</code> | <code>    def body_lines(self) -&gt; int:</code> | Оголошення функції `body_lines` та її аргументів; детальний контракт розібраний вище. |
| 467 | <code>Skill.body_lines</code> | <code>        return len([ln for ln in self.body.splitlines() if ln.strip()])</code> | Завершує поточну функцію та повертає len([ln for ln in self.body.splitlines() if ln.strip()]) |
| 468 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 469 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 470 | <code>_is_version_dir</code> | <code>def _is_version_dir(name: str) -&gt; bool:</code> | Оголошення функції `_is_version_dir` та її аргументів; детальний контракт розібраний вище. |
| 471 | <code>_is_version_dir</code> | <code>    return bool(re.fullmatch(r"v?\d+(\.\d+)*[A-Za-z0-9.+-]*", name))</code> | Завершує поточну функцію та повертає bool(re.fullmatch('v?\\d+(\\.\\d+)*[A-Za-z0-9.+-]*', name)) |
| 472 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 473 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 474 | <code>_plugin_name_for</code> | <code>def _plugin_name_for(skill_dir: Path) -&gt; Optional[str]:</code> | Оголошення функції `_plugin_name_for` та її аргументів; детальний контракт розібраний вище. |
| 475 | <code>_plugin_name_for</code> | <code>    """Walk up from a skill directory to name the plugin that ships it."""</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 476 | <code>_plugin_name_for</code> | <code>    for parent in [skill_dir] + list(skill_dir.parents):</code> | Ітерує [skill_dir] + list(skill_dir.parents) і зв’язує кожен елемент із parent |
| 477 | <code>_plugin_name_for</code> | <code>        manifest = parent / ".claude-plugin" / "plugin.json"</code> | Обчислює та зберігає manifest ← parent / '.claude-plugin' / 'plugin.json' |
| 478 | <code>_plugin_name_for</code> | <code>        if manifest.is_file():</code> | Умовна гілка: manifest.is_file(); відповідний block виконується тільки коли умова true. |
| 479 | <code>_plugin_name_for</code> | <code>            data = _read_json(manifest)</code> | Обчислює та зберігає data ← _read_json(manifest) |
| 480 | <code>_plugin_name_for</code> | <code>            if data is not None:</code> | Умовна гілка: data is not None; відповідний block виконується тільки коли умова true. |
| 481 | <code>_plugin_name_for</code> | <code>                _validate_plugin_manifest(data, str(manifest))</code> | Виконує виклик _validate_plugin_manifest: _validate_plugin_manifest(data, str(manifest)) |
| 482 | <code>_plugin_name_for</code> | <code>                if "name" not in data:</code> | Умовна гілка: 'name' not in data; відповідний block виконується тільки коли умова true. |
| 483 | <code>_plugin_name_for</code> | <code>                    raise AuditError("{}: name is required".format(manifest))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{}: name is required'.format(manifest)) |
| 484 | <code>_plugin_name_for</code> | <code>                return data["name"]</code> | Завершує поточну функцію та повертає data['name'] |
| 485 | <code>_plugin_name_for</code> | <code>        if parent.name == "skills":</code> | Умовна гілка: parent.name == 'skills'; відповідний block виконується тільки коли умова true. |
| 486 | <code>_plugin_name_for</code> | <code>            root = parent.parent</code> | Обчислює та зберігає root ← parent.parent |
| 487 | <code>_plugin_name_for</code> | <code>            # Versioned install caches are the only manifest-free ownership</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 488 | <code>_plugin_name_for</code> | <code>            # evidence. A generic directory named skills is not a plugin.</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 489 | <code>_plugin_name_for</code> | <code>            if _is_version_dir(root.name) and any(p.name == "plugins" for p in root.parents):</code> | Умовна гілка: _is_version_dir(root.name) and any((p.name == 'plugins' for p in root.parents)); відповідний block виконується тільки коли умова true. |
| 490 | <code>_plugin_name_for</code> | <code>                return root.parent.name</code> | Завершує поточну функцію та повертає root.parent.name |
| 491 | <code>_plugin_name_for</code> | <code>    return None</code> | Завершує поточну функцію та повертає None |
| 492 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 493 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 494 | <code>_classify</code> | <code>def _classify(path: Path) -&gt; Tuple[str, Optional[str]]:</code> | Оголошення функції `_classify` та її аргументів; детальний контракт розібраний вище. |
| 495 | <code>_classify</code> | <code>    normalized = str(path).lower().replace("\\", "/")</code> | Обчислює та зберігає normalized ← str(path).lower().replace('\\', '/') |
| 496 | <code>_classify</code> | <code>    home = str(Path.home()).lower().replace("\\", "/")</code> | Обчислює та зберігає home ← str(Path.home()).lower().replace('\\', '/') |
| 497 | <code>_classify</code> | <code>    plugin = _plugin_name_for(path.parent)</code> | Обчислює та зберігає plugin ← _plugin_name_for(path.parent) |
| 498 | <code>_classify</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 499 | <code>_classify</code> | <code>    if "/plugins/" in normalized or "/marketplace" in normalized:</code> | Умовна гілка: '/plugins/' in normalized or '/marketplace' in normalized; відповідний block виконується тільки коли умова true. |
| 500 | <code>_classify</code> | <code>        if plugin:</code> | Умовна гілка: plugin; відповідний block виконується тільки коли умова true. |
| 501 | <code>_classify</code> | <code>            return "plugin", plugin</code> | Завершує поточну функцію та повертає ('plugin', plugin) |
| 502 | <code>_classify</code> | <code>    if normalized.startswith(home + "/.claude/skills"):</code> | Умовна гілка: normalized.startswith(home + '/.claude/skills'); відповідний block виконується тільки коли умова true. |
| 503 | <code>_classify</code> | <code>        return "personal", None</code> | Завершує поточну функцію та повертає ('personal', None) |
| 504 | <code>_classify</code> | <code>    if "/.claude/skills/" in normalized:</code> | Умовна гілка: '/.claude/skills/' in normalized; відповідний block виконується тільки коли умова true. |
| 505 | <code>_classify</code> | <code>        return "project", None</code> | Завершує поточну функцію та повертає ('project', None) |
| 506 | <code>_classify</code> | <code>    if plugin:</code> | Умовна гілка: plugin; відповідний block виконується тільки коли умова true. |
| 507 | <code>_classify</code> | <code>        return "plugin", plugin</code> | Завершує поточну функцію та повертає ('plugin', plugin) |
| 508 | <code>_classify</code> | <code>    return "scanned", None</code> | Завершує поточну функцію та повертає ('scanned', None) |
| 509 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 510 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 511 | <code>&lt;module&gt;</code> | <code>_PRUNE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}</code> | Обчислює та зберігає _PRUNE_DIRS ← {'.git', 'node_modules', '__pycache__', '.venv', 'venv'} |
| 512 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 513 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 514 | <code>_bundle_bytes</code> | <code>def _bundle_bytes(skill_dir: Path) -&gt; int:</code> | Оголошення функції `_bundle_bytes` та її аргументів; детальний контракт розібраний вище. |
| 515 | <code>_bundle_bytes</code> | <code>    """Bytes of the skill's own files.</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 516 | <code>_bundle_bytes</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 517 | <code>_bundle_bytes</code> | <code>    Prunes VCS/vendor noise and never descends into a nested skill (a</code> | Продовження інструкції 515: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 518 | <code>_bundle_bytes</code> | <code>    subdirectory carrying its own SKILL.md), so a plugin root or a whole</code> | Продовження інструкції 515: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 519 | <code>_bundle_bytes</code> | <code>    repository dropped in as one skill reports its own footprint rather than</code> | Продовження інструкції 515: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 520 | <code>_bundle_bytes</code> | <code>    the entire tree. Without this, a repo-root SKILL.md billed gigabytes and</code> | Продовження інструкції 515: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 521 | <code>_bundle_bytes</code> | <code>    the walk dominated runtime.</code> | Продовження інструкції 515: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 522 | <code>_bundle_bytes</code> | <code>    """</code> | Продовження інструкції 515: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 523 | <code>_bundle_bytes</code> | <code>    total = 0</code> | Обчислює та зберігає total ← 0 |
| 524 | <code>_bundle_bytes</code> | <code>    root = str(skill_dir)</code> | Обчислює та зберігає root ← str(skill_dir) |
| 525 | <code>_bundle_bytes</code> | <code>    for current, dirs, files in os.walk(root):</code> | Ітерує os.walk(root) і зв’язує кожен елемент із (current, dirs, files) |
| 526 | <code>_bundle_bytes</code> | <code>        if current != root and "SKILL.md" in files:</code> | Умовна гілка: current != root and 'SKILL.md' in files; відповідний block виконується тільки коли умова true. |
| 527 | <code>_bundle_bytes</code> | <code>            dirs[:] = []            # a separate skill owns everything below here</code> | Обчислює та зберігає dirs[:] ← [] |
| 528 | <code>_bundle_bytes</code> | <code>            continue</code> | Пропускає решту цієї ітерації; переходить до наступного елемента. |
| 529 | <code>_bundle_bytes</code> | <code>        descend: List[str] = []</code> | Типізує descend як List[str]; initial value [] |
| 530 | <code>_bundle_bytes</code> | <code>        for directory in dirs:</code> | Ітерує dirs і зв’язує кожен елемент із directory |
| 531 | <code>_bundle_bytes</code> | <code>            if directory in _PRUNE_DIRS:</code> | Умовна гілка: directory in _PRUNE_DIRS; відповідний block виконується тільки коли умова true. |
| 532 | <code>_bundle_bytes</code> | <code>                continue</code> | Пропускає решту цієї ітерації; переходить до наступного елемента. |
| 533 | <code>_bundle_bytes</code> | <code>            try:</code> | Межа обробки винятків: виконати block і застосувати specified handlers. |
| 534 | <code>_bundle_bytes</code> | <code>                info = os.lstat(os.path.join(current, directory))</code> | Обчислює та зберігає info ← os.lstat(os.path.join(current, directory)) |
| 535 | <code>_bundle_bytes</code> | <code>            except OSError:</code> | Handler для зазначеного типу винятку; operational finding/fallback залежить від body нижче. |
| 536 | <code>_bundle_bytes</code> | <code>                continue</code> | Пропускає решту цієї ітерації; переходить до наступного елемента. |
| 537 | <code>_bundle_bytes</code> | <code>            if (stat.S_ISLNK(info.st_mode) or</code> | Умовна гілка: stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) &amp; getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0); відповідний block виконується тільки коли умова true. |
| 538 | <code>_bundle_bytes</code> | <code>                    getattr(info, "st_file_attributes", 0) &amp; getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):</code> | Продовження інструкції 537: Умовна гілка: stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) &amp; getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0); відповідний block виконується тільки коли умова true. |
| 539 | <code>_bundle_bytes</code> | <code>                continue</code> | Пропускає решту цієї ітерації; переходить до наступного елемента. |
| 540 | <code>_bundle_bytes</code> | <code>            descend.append(directory)</code> | Виконує виклик descend.append: descend.append(directory) |
| 541 | <code>_bundle_bytes</code> | <code>        dirs[:] = descend</code> | Обчислює та зберігає dirs[:] ← descend |
| 542 | <code>_bundle_bytes</code> | <code>        for name in files:</code> | Ітерує files і зв’язує кожен елемент із name |
| 543 | <code>_bundle_bytes</code> | <code>            try:</code> | Межа обробки винятків: виконати block і застосувати specified handlers. |
| 544 | <code>_bundle_bytes</code> | <code>                total += os.stat(os.path.join(current, name)).st_size</code> | Оновлює накопичене значення: total += os.stat(os.path.join(current, name)).st_size |
| 545 | <code>_bundle_bytes</code> | <code>            except OSError:</code> | Handler для зазначеного типу винятку; operational finding/fallback залежить від body нижче. |
| 546 | <code>_bundle_bytes</code> | <code>                pass</code> | Свідомо порожня гілка; state/output на цьому кроці не змінюється. |
| 547 | <code>_bundle_bytes</code> | <code>    return total</code> | Завершує поточну функцію та повертає total |
| 548 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 549 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 550 | <code>_directory_name</code> | <code>def _directory_name(path: Path) -&gt; str:</code> | Оголошення функції `_directory_name` та її аргументів; детальний контракт розібраний вище. |
| 551 | <code>_directory_name</code> | <code>    """The skill's own directory name, resolved so `.` and `..` don't leak through."""</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 552 | <code>_directory_name</code> | <code>    name = path.parent.name</code> | Обчислює та зберігає name ← path.parent.name |
| 553 | <code>_directory_name</code> | <code>    if name in ("", ".", ".."):</code> | Умовна гілка: name in ('', '.', '..'); відповідний block виконується тільки коли умова true. |
| 554 | <code>_directory_name</code> | <code>        try:</code> | Межа обробки винятків: виконати block і застосувати specified handlers. |
| 555 | <code>_directory_name</code> | <code>            name = path.resolve().parent.name</code> | Обчислює та зберігає name ← path.resolve().parent.name |
| 556 | <code>_directory_name</code> | <code>        except OSError:</code> | Handler для зазначеного типу винятку; operational finding/fallback залежить від body нижче. |
| 557 | <code>_directory_name</code> | <code>            name = ""</code> | Обчислює та зберігає name ← '' |
| 558 | <code>_directory_name</code> | <code>    return name</code> | Завершує поточну функцію та повертає name |
| 559 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 560 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 561 | <code>&lt;module&gt;</code> | <code># One discovered file: (path, owning plugin or None, "skill" &#124; "command", command name or None)</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 562 | <code>&lt;module&gt;</code> | <code>Entry = Tuple[Path, Optional[str], str, Optional[str]]</code> | Обчислює та зберігає Entry ← Tuple[Path, Optional[str], str, Optional[str]] |
| 563 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 564 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 565 | <code>load_skill</code> | <code>def load_skill(</code> | Оголошення функції `load_skill` та її аргументів; детальний контракт розібраний вище. |
| 566 | <code>load_skill</code> | <code>    path: Path, plugin: Optional[str] = None, kind: str = "skill", command: Optional[str] = None</code> | Оголошення функції `load_skill` та її аргументів; детальний контракт розібраний вище. |
| 567 | <code>load_skill</code> | <code>) -&gt; Skill:</code> | Оголошення функції `load_skill` та її аргументів; детальний контракт розібраний вище. |
| 568 | <code>load_skill</code> | <code>    """Load one SKILL.md, or one commands/*.md file when kind == "command".</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 569 | <code>load_skill</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 570 | <code>load_skill</code> | <code>    `plugin` is the owning plugin when a manifest named it; otherwise it is</code> | Продовження інструкції 568: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 571 | <code>load_skill</code> | <code>    inferred from the path. `command` is a precomputed name (commands take theirs</code> | Продовження інструкції 568: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 572 | <code>load_skill</code> | <code>    from the file path, not from frontmatter)."""</code> | Продовження інструкції 568: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 573 | <code>load_skill</code> | <code>    try:</code> | Межа обробки винятків: виконати block і застосувати specified handlers. |
| 574 | <code>load_skill</code> | <code>        text = path.read_text(encoding="utf-8")</code> | Обчислює та зберігає text ← path.read_text(encoding='utf-8') |
| 575 | <code>load_skill</code> | <code>    except (OSError, UnicodeError) as exc:  # unreadable file is a finding, not a crash</code> | Handler для зазначеного типу винятку; operational finding/fallback залежить від body нижче. |
| 576 | <code>load_skill</code> | <code>        return Skill(</code> | Завершує поточну функцію та повертає Skill(path=path, root=path.parent, origin='scanned', command=command or path.parent.name, frontmatter={}, body='', problems=['unreadable: {}'.format(exc)], kind=kind) |
| 577 | <code>load_skill</code> | <code>            path=path, root=path.parent, origin="scanned", command=command or path.parent.name,</code> | Продовження інструкції 576: Завершує поточну функцію та повертає Skill(path=path, root=path.parent, origin='scanned', command=command or path.parent.name, frontmatter={}, body='', problems=['unreadable: {}'.format(exc)], kind=kind) |
| 578 | <code>load_skill</code> | <code>            frontmatter={}, body="", problems=["unreadable: {}".format(exc)], kind=kind,</code> | Продовження інструкції 576: Завершує поточну функцію та повертає Skill(path=path, root=path.parent, origin='scanned', command=command or path.parent.name, frontmatter={}, body='', problems=['unreadable: {}'.format(exc)], kind=kind) |
| 579 | <code>load_skill</code> | <code>        )</code> | Продовження інструкції 576: Завершує поточну функцію та повертає Skill(path=path, root=path.parent, origin='scanned', command=command or path.parent.name, frontmatter={}, body='', problems=['unreadable: {}'.format(exc)], kind=kind) |
| 580 | <code>load_skill</code> | <code>    fm, body, problems = parse_frontmatter(text)</code> | Обчислює та зберігає (fm, body, problems) ← parse_frontmatter(text) |
| 581 | <code>load_skill</code> | <code>    if kind == "command":</code> | Умовна гілка: kind == 'command'; відповідний block виконується тільки коли умова true. |
| 582 | <code>load_skill</code> | <code>        # Command files support the same frontmatter except `name`: the file path</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 583 | <code>load_skill</code> | <code>        # is the name. A missing frontmatter block is normal for them.</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 584 | <code>load_skill</code> | <code>        problems = [p for p in problems if p != "no-frontmatter"]</code> | Обчислює та зберігає problems ← [p for p in problems if p != 'no-frontmatter'] |
| 585 | <code>load_skill</code> | <code>        origin = "plugin" if plugin else "command"</code> | Обчислює та зберігає origin ← 'plugin' if plugin else 'command' |
| 586 | <code>load_skill</code> | <code>        try:</code> | Межа обробки винятків: виконати block і застосувати specified handlers. |
| 587 | <code>load_skill</code> | <code>            size = path.stat().st_size</code> | Обчислює та зберігає size ← path.stat().st_size |
| 588 | <code>load_skill</code> | <code>        except OSError:</code> | Handler для зазначеного типу винятку; operational finding/fallback залежить від body нижче. |
| 589 | <code>load_skill</code> | <code>            size = 0</code> | Обчислює та зберігає size ← 0 |
| 590 | <code>load_skill</code> | <code>        return Skill(</code> | Завершує поточну функцію та повертає Skill(path=path, root=path.parent, origin=origin, command=command or path.stem, frontmatter=fm, body=body, problems=problems, plugin=plugin, bundle_bytes=size, kind='command') |
| 591 | <code>load_skill</code> | <code>            path=path, root=path.parent, origin=origin, command=command or path.stem,</code> | Продовження інструкції 590: Завершує поточну функцію та повертає Skill(path=path, root=path.parent, origin=origin, command=command or path.stem, frontmatter=fm, body=body, problems=problems, plugin=plugin, bundle_bytes=size, kind='command') |
| 592 | <code>load_skill</code> | <code>            frontmatter=fm, body=body, problems=problems, plugin=plugin,</code> | Продовження інструкції 590: Завершує поточну функцію та повертає Skill(path=path, root=path.parent, origin=origin, command=command or path.stem, frontmatter=fm, body=body, problems=problems, plugin=plugin, bundle_bytes=size, kind='command') |
| 593 | <code>load_skill</code> | <code>            bundle_bytes=size, kind="command",</code> | Продовження інструкції 590: Завершує поточну функцію та повертає Skill(path=path, root=path.parent, origin=origin, command=command or path.stem, frontmatter=fm, body=body, problems=problems, plugin=plugin, bundle_bytes=size, kind='command') |
| 594 | <code>load_skill</code> | <code>        )</code> | Продовження інструкції 590: Завершує поточну функцію та повертає Skill(path=path, root=path.parent, origin=origin, command=command or path.stem, frontmatter=fm, body=body, problems=problems, plugin=plugin, bundle_bytes=size, kind='command') |
| 595 | <code>load_skill</code> | <code>    origin, inferred = ("plugin", plugin) if plugin else _classify(path)</code> | Обчислює та зберігає (origin, inferred) ← ('plugin', plugin) if plugin else _classify(path) |
| 596 | <code>load_skill</code> | <code>    plugin = inferred</code> | Обчислює та зберігає plugin ← inferred |
| 597 | <code>load_skill</code> | <code>    # Frontmatter `name` wins over the directory name, for plugin and local</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 598 | <code>load_skill</code> | <code>    # skills alike; a plugin keeps its prefix in front of it.</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 599 | <code>load_skill</code> | <code>    leaf = fm.get("name") or _directory_name(path) or path.stem</code> | Обчислює та зберігає leaf ← fm.get('name') or _directory_name(path) or path.stem |
| 600 | <code>load_skill</code> | <code>    if plugin:</code> | Умовна гілка: plugin; відповідний block виконується тільки коли умова true. |
| 601 | <code>load_skill</code> | <code>        command = leaf if leaf.startswith(plugin + ":") else "{}:{}".format(plugin, leaf)</code> | Обчислює та зберігає command ← leaf if leaf.startswith(plugin + ':') else '{}:{}'.format(plugin, leaf) |
| 602 | <code>load_skill</code> | <code>    else:</code> | Alternative branch для попередньої умови або завершення циклу без break. |
| 603 | <code>load_skill</code> | <code>        command = leaf</code> | Обчислює та зберігає command ← leaf |
| 604 | <code>load_skill</code> | <code>    return Skill(</code> | Завершує поточну функцію та повертає Skill(path=path, root=path.parent, origin=origin, command=command, frontmatter=fm, body=body, problems=problems, plugin=plugin, bundle_bytes=_bundle_bytes(path.parent)) |
| 605 | <code>load_skill</code> | <code>        path=path, root=path.parent, origin=origin, command=command,</code> | Продовження інструкції 604: Завершує поточну функцію та повертає Skill(path=path, root=path.parent, origin=origin, command=command, frontmatter=fm, body=body, problems=problems, plugin=plugin, bundle_bytes=_bundle_bytes(path.parent)) |
| 606 | <code>load_skill</code> | <code>        frontmatter=fm, body=body, problems=problems, plugin=plugin,</code> | Продовження інструкції 604: Завершує поточну функцію та повертає Skill(path=path, root=path.parent, origin=origin, command=command, frontmatter=fm, body=body, problems=problems, plugin=plugin, bundle_bytes=_bundle_bytes(path.parent)) |
| 607 | <code>load_skill</code> | <code>        bundle_bytes=_bundle_bytes(path.parent),</code> | Продовження інструкції 604: Завершує поточну функцію та повертає Skill(path=path, root=path.parent, origin=origin, command=command, frontmatter=fm, body=body, problems=problems, plugin=plugin, bundle_bytes=_bundle_bytes(path.parent)) |
| 608 | <code>load_skill</code> | <code>    )</code> | Продовження інструкції 604: Завершує поточну функцію та повертає Skill(path=path, root=path.parent, origin=origin, command=command, frontmatter=fm, body=body, problems=problems, plugin=plugin, bundle_bytes=_bundle_bytes(path.parent)) |
| 609 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 610 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 611 | <code>_project_dirs</code> | <code>def _project_dirs(cwd: Path) -&gt; List[Path]:</code> | Оголошення функції `_project_dirs` та її аргументів; детальний контракт розібраний вище. |
| 612 | <code>_project_dirs</code> | <code>    """The start directory and its parents up to the repository root: Claude Code</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 613 | <code>_project_dirs</code> | <code>    loads project skills from .claude/ in each. Outside a repo, just the start."""</code> | Продовження інструкції 612: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 614 | <code>_project_dirs</code> | <code>    dirs: List[Path] = []</code> | Типізує dirs як List[Path]; initial value [] |
| 615 | <code>_project_dirs</code> | <code>    for folder in [cwd] + list(cwd.parents):</code> | Ітерує [cwd] + list(cwd.parents) і зв’язує кожен елемент із folder |
| 616 | <code>_project_dirs</code> | <code>        dirs.append(folder)</code> | Виконує виклик dirs.append: dirs.append(folder) |
| 617 | <code>_project_dirs</code> | <code>        if (folder / ".git").exists():</code> | Умовна гілка: (folder / '.git').exists(); відповідний block виконується тільки коли умова true. |
| 618 | <code>_project_dirs</code> | <code>            return dirs</code> | Завершує поточну функцію та повертає dirs |
| 619 | <code>_project_dirs</code> | <code>    return [cwd]</code> | Завершує поточну функцію та повертає [cwd] |
| 620 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 621 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 622 | <code>default_roots</code> | <code>def default_roots(cwd: Optional[Path] = None) -&gt; List[Path]:</code> | Оголошення функції `default_roots` та її аргументів; детальний контракт розібраний вище. |
| 623 | <code>default_roots</code> | <code>    """Install directories for the Claude Code profile this tool models."""</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 624 | <code>default_roots</code> | <code>    home = Path.home()</code> | Обчислює та зберігає home ← Path.home() |
| 625 | <code>default_roots</code> | <code>    candidates = [</code> | Обчислює та зберігає candidates ← [home / '.claude' / 'skills', home / '.claude' / 'plugins'] + [d / '.claude' / 'skills' for d in _project_dirs(cwd or Path.cwd())] |
| 626 | <code>default_roots</code> | <code>        home / ".claude" / "skills",</code> | Продовження інструкції 625: Обчислює та зберігає candidates ← [home / '.claude' / 'skills', home / '.claude' / 'plugins'] + [d / '.claude' / 'skills' for d in _project_dirs(cwd or Path.cwd())] |
| 627 | <code>default_roots</code> | <code>        home / ".claude" / "plugins",</code> | Продовження інструкції 625: Обчислює та зберігає candidates ← [home / '.claude' / 'skills', home / '.claude' / 'plugins'] + [d / '.claude' / 'skills' for d in _project_dirs(cwd or Path.cwd())] |
| 628 | <code>default_roots</code> | <code>    ] + [d / ".claude" / "skills" for d in _project_dirs(cwd or Path.cwd())]</code> | Продовження інструкції 625: Обчислює та зберігає candidates ← [home / '.claude' / 'skills', home / '.claude' / 'plugins'] + [d / '.claude' / 'skills' for d in _project_dirs(cwd or Path.cwd())] |
| 629 | <code>default_roots</code> | <code>    return [c for c in candidates if c.is_dir()]</code> | Завершує поточну функцію та повертає [c for c in candidates if c.is_dir()] |
| 630 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 631 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 632 | <code>command_entries</code> | <code>def command_entries(root: Path) -&gt; List[Entry]:</code> | Оголошення функції `command_entries` та її аргументів; детальний контракт розібраний вище. |
| 633 | <code>command_entries</code> | <code>    """Legacy command files: commands/deploy.md is /deploy and</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 634 | <code>command_entries</code> | <code>    commands/frontend/component.md is /frontend:component."""</code> | Продовження інструкції 633: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 635 | <code>command_entries</code> | <code>    entries: List[Entry] = []</code> | Типізує entries як List[Entry]; initial value [] |
| 636 | <code>command_entries</code> | <code>    for path in _inventory_files(root, "*.md", missing_ok=True):</code> | Ітерує _inventory_files(root, '*.md', missing_ok=True) і зв’язує кожен елемент із path |
| 637 | <code>command_entries</code> | <code>        rel = path.relative_to(root).with_suffix("")</code> | Обчислює та зберігає rel ← path.relative_to(root).with_suffix('') |
| 638 | <code>command_entries</code> | <code>        entries.append((path, None, "command", ":".join(rel.parts)))</code> | Виконує виклик entries.append: entries.append((path, None, 'command', ':'.join(rel.parts))) |
| 639 | <code>command_entries</code> | <code>    return entries</code> | Завершує поточну функцію та повертає entries |
| 640 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 641 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 642 | <code>AuditError</code> | <code>class AuditError(ValueError):</code> | Оголошення класу `AuditError` та базових класів; модель даних/поведінка розібрана вище. |
| 643 | <code>AuditError</code> | <code>    """An operational input failure: an incomplete audit must not look clean."""</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 644 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 645 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 646 | <code>_inventory_files</code> | <code>def _inventory_files(</code> | Оголошення функції `_inventory_files` та її аргументів; детальний контракт розібраний вище. |
| 647 | <code>_inventory_files</code> | <code>    root: Path, pattern: str, shallow: bool = False, missing_ok: bool = False,</code> | Оголошення функції `_inventory_files` та її аргументів; детальний контракт розібраний вище. |
| 648 | <code>_inventory_files</code> | <code>) -&gt; List[Path]:</code> | Оголошення функції `_inventory_files` та її аргументів; детальний контракт розібраний вище. |
| 649 | <code>_inventory_files</code> | <code>    """Enumerate inventory without silently suppressing directory read errors.</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 650 | <code>_inventory_files</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 651 | <code>_inventory_files</code> | <code>    Recursive scans do not descend into child symlink/reparse directories;</code> | Продовження інструкції 649: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 652 | <code>_inventory_files</code> | <code>    explicit roots are followed. Shallow installed roots inspect one level of</code> | Продовження інструкції 649: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 653 | <code>_inventory_files</code> | <code>    skill directories, including linked installations, but never recurse deeper.</code> | Продовження інструкції 649: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 654 | <code>_inventory_files</code> | <code>    Missing optional component roots are normal; inaccessible roots are errors.</code> | Продовження інструкції 649: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 655 | <code>_inventory_files</code> | <code>    """</code> | Продовження інструкції 649: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 656 | <code>_inventory_files</code> | <code>    found: List[Path] = []</code> | Типізує found як List[Path]; initial value [] |
| 657 | <code>_inventory_files</code> | <code>    pending: List[Tuple[Path, int]] = [(root, 0)]</code> | Типізує pending як List[Tuple[Path, int]]; initial value [(root, 0)] |
| 658 | <code>_inventory_files</code> | <code>    while pending:</code> | Продовжує цикл поки pending |
| 659 | <code>_inventory_files</code> | <code>        folder, depth = pending.pop()</code> | Обчислює та зберігає (folder, depth) ← pending.pop() |
| 660 | <code>_inventory_files</code> | <code>        try:</code> | Межа обробки винятків: виконати block і застосувати specified handlers. |
| 661 | <code>_inventory_files</code> | <code>            with os.scandir(folder) as entries:</code> | Керує lifetime/закриттям context resources: os.scandir(folder) |
| 662 | <code>_inventory_files</code> | <code>                for entry in entries:</code> | Ітерує entries і зв’язує кожен елемент із entry |
| 663 | <code>_inventory_files</code> | <code>                    path = Path(entry.path)</code> | Обчислює та зберігає path ← Path(entry.path) |
| 664 | <code>_inventory_files</code> | <code>                    if (not shallow or depth == 1) and fnmatch.fnmatch(entry.name, pattern):</code> | Умовна гілка: (not shallow or depth == 1) and fnmatch.fnmatch(entry.name, pattern); відповідний block виконується тільки коли умова true. |
| 665 | <code>_inventory_files</code> | <code>                        found.append(path)</code> | Виконує виклик found.append: found.append(path) |
| 666 | <code>_inventory_files</code> | <code>                    if shallow:</code> | Умовна гілка: shallow; відповідний block виконується тільки коли умова true. |
| 667 | <code>_inventory_files</code> | <code>                        if depth == 0 and entry.is_dir():</code> | Умовна гілка: depth == 0 and entry.is_dir(); відповідний block виконується тільки коли умова true. |
| 668 | <code>_inventory_files</code> | <code>                            pending.append((path, 1))</code> | Виконує виклик pending.append: pending.append((path, 1)) |
| 669 | <code>_inventory_files</code> | <code>                    elif entry.is_dir(follow_symlinks=False):</code> | Наступна умовна гілка, коли попередній if/elif не виконався. |
| 670 | <code>_inventory_files</code> | <code>                        # Older Windows Pythons consider junctions directories</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 671 | <code>_inventory_files</code> | <code>                        # even with follow_symlinks=False. Prune reparse children</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 672 | <code>_inventory_files</code> | <code>                        # before scanning so junction cycles and escapes stop.</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 673 | <code>_inventory_files</code> | <code>                        attributes = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)</code> | Обчислює та зберігає attributes ← getattr(entry.stat(follow_symlinks=False), 'st_file_attributes', 0) |
| 674 | <code>_inventory_files</code> | <code>                        if not attributes &amp; getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):</code> | Умовна гілка: not attributes &amp; getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0); відповідний block виконується тільки коли умова true. |
| 675 | <code>_inventory_files</code> | <code>                            pending.append((path, depth + 1))</code> | Виконує виклик pending.append: pending.append((path, depth + 1)) |
| 676 | <code>_inventory_files</code> | <code>        except OSError as exc:</code> | Handler для зазначеного типу винятку; operational finding/fallback залежить від body нижче. |
| 677 | <code>_inventory_files</code> | <code>            if missing_ok and depth == 0 and isinstance(exc, (FileNotFoundError, NotADirectoryError)):</code> | Умовна гілка: missing_ok and depth == 0 and isinstance(exc, (FileNotFoundError, NotADirectoryError)); відповідний block виконується тільки коли умова true. |
| 678 | <code>_inventory_files</code> | <code>                continue</code> | Пропускає решту цієї ітерації; переходить до наступного елемента. |
| 679 | <code>_inventory_files</code> | <code>            raise AuditError("could not scan inventory {}: {}".format(folder, exc)) from None</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('could not scan inventory {}: {}'.format(folder, exc)) |
| 680 | <code>_inventory_files</code> | <code>    return sorted(found)</code> | Завершує поточну функцію та повертає sorted(found) |
| 681 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 682 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 683 | <code>_read_json</code> | <code>def _read_json(path: Path) -&gt; Optional[dict]:</code> | Оголошення функції `_read_json` та її аргументів; детальний контракт розібраний вище. |
| 684 | <code>_read_json</code> | <code>    """Read an optional JSON object; present but invalid input is an error."""</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 685 | <code>_read_json.reject_constant</code> | <code>    def reject_constant(value):</code> | Оголошення функції `reject_constant` та її аргументів; детальний контракт розібраний вище. |
| 686 | <code>_read_json.reject_constant</code> | <code>        raise ValueError("non-finite JSON number {}".format(value))</code> | Відхиляє unsupported/failed input або передає error вище: ValueError('non-finite JSON number {}'.format(value)) |
| 687 | <code>_read_json</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 688 | <code>_read_json</code> | <code>    try:</code> | Межа обробки винятків: виконати block і застосувати specified handlers. |
| 689 | <code>_read_json</code> | <code>        data = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)</code> | Обчислює та зберігає data ← json.loads(path.read_text(encoding='utf-8'), parse_constant=reject_constant) |
| 690 | <code>_read_json</code> | <code>    except FileNotFoundError:</code> | Handler для зазначеного типу винятку; operational finding/fallback залежить від body нижче. |
| 691 | <code>_read_json</code> | <code>        return None</code> | Завершує поточну функцію та повертає None |
| 692 | <code>_read_json</code> | <code>    except (ValueError, OSError, UnicodeError, RecursionError) as exc:</code> | Handler для зазначеного типу винятку; operational finding/fallback залежить від body нижче. |
| 693 | <code>_read_json</code> | <code>        raise AuditError("could not read JSON {}: {}".format(path, exc)) from None</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('could not read JSON {}: {}'.format(path, exc)) |
| 694 | <code>_read_json</code> | <code>    if not isinstance(data, dict):</code> | Умовна гілка: not isinstance(data, dict); відповідний block виконується тільки коли умова true. |
| 695 | <code>_read_json</code> | <code>        raise AuditError("{}: expected a JSON object".format(path))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{}: expected a JSON object'.format(path)) |
| 696 | <code>_read_json</code> | <code>    return data</code> | Завершує поточну функцію та повертає data |
| 697 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 698 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 699 | <code>_as_paths</code> | <code>def _as_paths(value, label: str = "manifest path") -&gt; List[str]:</code> | Оголошення функції `_as_paths` та її аргументів; детальний контракт розібраний вище. |
| 700 | <code>_as_paths</code> | <code>    if isinstance(value, str):</code> | Умовна гілка: isinstance(value, str); відповідний block виконується тільки коли умова true. |
| 701 | <code>_as_paths</code> | <code>        values = [value]</code> | Обчислює та зберігає values ← [value] |
| 702 | <code>_as_paths</code> | <code>    elif isinstance(value, list) and all(isinstance(p, str) for p in value):</code> | Наступна умовна гілка, коли попередній if/elif не виконався. |
| 703 | <code>_as_paths</code> | <code>        values = value</code> | Обчислює та зберігає values ← value |
| 704 | <code>_as_paths</code> | <code>    else:</code> | Alternative branch для попередньої умови або завершення циклу без break. |
| 705 | <code>_as_paths</code> | <code>        raise AuditError("{}: expected a path string or an array of path strings".format(label))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{}: expected a path string or an array of path strings'.format(label)) |
| 706 | <code>_as_paths</code> | <code>    if any(not p.strip() for p in values):</code> | Умовна гілка: any((not p.strip() for p in values)); відповідний block виконується тільки коли умова true. |
| 707 | <code>_as_paths</code> | <code>        raise AuditError("{}: paths must not be empty".format(label))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{}: paths must not be empty'.format(label)) |
| 708 | <code>_as_paths</code> | <code>    return values</code> | Завершує поточну функцію та повертає values |
| 709 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 710 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 711 | <code>_within_root</code> | <code>def _within_root(path: Path, root: Path, label: str) -&gt; Path:</code> | Оголошення функції `_within_root` та її аргументів; детальний контракт розібраний вище. |
| 712 | <code>_within_root</code> | <code>    try:</code> | Межа обробки винятків: виконати block і застосувати specified handlers. |
| 713 | <code>_within_root</code> | <code>        path.resolve().relative_to(root.resolve())</code> | Виконує виклик path.resolve().relative_to: path.resolve().relative_to(root.resolve()) |
| 714 | <code>_within_root</code> | <code>    except (ValueError, OSError, RuntimeError):</code> | Handler для зазначеного типу винятку; operational finding/fallback залежить від body нижче. |
| 715 | <code>_within_root</code> | <code>        raise AuditError("{}: path escapes its root: {}".format(label, path)) from None</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{}: path escapes its root: {}'.format(label, path)) |
| 716 | <code>_within_root</code> | <code>    return path</code> | Завершує поточну функцію та повертає path |
| 717 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 718 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 719 | <code>_manifest_path</code> | <code>def _manifest_path(root: Path, value: str, label: str) -&gt; Path:</code> | Оголошення функції `_manifest_path` та її аргументів; детальний контракт розібраний вище. |
| 720 | <code>_manifest_path</code> | <code>    # Check Windows syntax on every host, before resolving a UNC path could</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 721 | <code>_manifest_path</code> | <code>    # cause network filesystem access. Parent traversal is never a local source.</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 722 | <code>_manifest_path</code> | <code>    normalized = value.replace("\\", "/")</code> | Обчислює та зберігає normalized ← value.replace('\\', '/') |
| 723 | <code>_manifest_path</code> | <code>    windows = PureWindowsPath(value)</code> | Обчислює та зберігає windows ← PureWindowsPath(value) |
| 724 | <code>_manifest_path</code> | <code>    if not value.strip() or Path(normalized).is_absolute() or windows.drive or ".." in normalized.split("/"):</code> | Умовна гілка: not value.strip() or Path(normalized).is_absolute() or windows.drive or ('..' in normalized.split('/')); відповідний block виконується тільки коли умова true. |
| 725 | <code>_manifest_path</code> | <code>        raise AuditError("{}: expected a relative path within {}: {}".format(label, root, value))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{}: expected a relative path within {}: {}'.format(label, root, value)) |
| 726 | <code>_manifest_path</code> | <code>    return _within_root(root / normalized, root, label)</code> | Завершує поточну функцію та повертає _within_root(root / normalized, root, label) |
| 727 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 728 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 729 | <code>_validate_plugin_manifest</code> | <code>def _validate_plugin_manifest(manifest: dict, label: str) -&gt; None:</code> | Оголошення функції `_validate_plugin_manifest` та її аргументів; детальний контракт розібраний вище. |
| 730 | <code>_validate_plugin_manifest</code> | <code>    if "name" in manifest and (not isinstance(manifest["name"], str) or not manifest["name"].strip()):</code> | Умовна гілка: 'name' in manifest and (not isinstance(manifest['name'], str) or not manifest['name'].strip()); відповідний block виконується тільки коли умова true. |
| 731 | <code>_validate_plugin_manifest</code> | <code>        raise AuditError("{}: name must be a non-empty string".format(label))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{}: name must be a non-empty string'.format(label)) |
| 732 | <code>_validate_plugin_manifest</code> | <code>    for key in ("skills", "commands"):</code> | Ітерує ('skills', 'commands') і зв’язує кожен елемент із key |
| 733 | <code>_validate_plugin_manifest</code> | <code>        if key in manifest:</code> | Умовна гілка: key in manifest; відповідний block виконується тільки коли умова true. |
| 734 | <code>_validate_plugin_manifest</code> | <code>            _as_paths(manifest[key], "{} {}".format(label, key))</code> | Виконує виклик _as_paths: _as_paths(manifest[key], '{} {}'.format(label, key)) |
| 735 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 736 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 737 | <code>_marketplace_entries</code> | <code>def _marketplace_entries(market: dict, label: str) -&gt; List[dict]:</code> | Оголошення функції `_marketplace_entries` та її аргументів; детальний контракт розібраний вище. |
| 738 | <code>_marketplace_entries</code> | <code>    if "plugins" not in market:</code> | Умовна гілка: 'plugins' not in market; відповідний block виконується тільки коли умова true. |
| 739 | <code>_marketplace_entries</code> | <code>        raise AuditError("{}: plugins is required".format(label))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{}: plugins is required'.format(label)) |
| 740 | <code>_marketplace_entries</code> | <code>    entries = market["plugins"]</code> | Обчислює та зберігає entries ← market['plugins'] |
| 741 | <code>_marketplace_entries</code> | <code>    if not isinstance(entries, list) or any(not isinstance(p, dict) for p in entries):</code> | Умовна гілка: not isinstance(entries, list) or any((not isinstance(p, dict) for p in entries)); відповідний block виконується тільки коли умова true. |
| 742 | <code>_marketplace_entries</code> | <code>        raise AuditError("{}: plugins must be an array of objects".format(label))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{}: plugins must be an array of objects'.format(label)) |
| 743 | <code>_marketplace_entries</code> | <code>    for entry in entries:</code> | Ітерує entries і зв’язує кожен елемент із entry |
| 744 | <code>_marketplace_entries</code> | <code>        for required in ("name", "source"):</code> | Ітерує ('name', 'source') і зв’язує кожен елемент із required |
| 745 | <code>_marketplace_entries</code> | <code>            if required not in entry:</code> | Умовна гілка: required not in entry; відповідний block виконується тільки коли умова true. |
| 746 | <code>_marketplace_entries</code> | <code>                raise AuditError("{}: plugin {} is required".format(label, required))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{}: plugin {} is required'.format(label, required)) |
| 747 | <code>_marketplace_entries</code> | <code>        _validate_plugin_manifest(entry, label)</code> | Виконує виклик _validate_plugin_manifest: _validate_plugin_manifest(entry, label) |
| 748 | <code>_marketplace_entries</code> | <code>        if "strict" in entry and not isinstance(entry["strict"], bool):</code> | Умовна гілка: 'strict' in entry and (not isinstance(entry['strict'], bool)); відповідний block виконується тільки коли умова true. |
| 749 | <code>_marketplace_entries</code> | <code>            raise AuditError("{}: plugin strict must be a boolean".format(label))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{}: plugin strict must be a boolean'.format(label)) |
| 750 | <code>_marketplace_entries</code> | <code>        source = entry["source"]</code> | Обчислює та зберігає source ← entry['source'] |
| 751 | <code>_marketplace_entries</code> | <code>        if not isinstance(source, (str, dict)):</code> | Умовна гілка: not isinstance(source, (str, dict)); відповідний block виконується тільки коли умова true. |
| 752 | <code>_marketplace_entries</code> | <code>            raise AuditError("{}: plugin source must be a relative path or a source object".format(label))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{}: plugin source must be a relative path or a source object'.format(label)) |
| 753 | <code>_marketplace_entries</code> | <code>        if isinstance(source, dict) and (not isinstance(source.get("source"), str)</code> | Умовна гілка: isinstance(source, dict) and (not isinstance(source.get('source'), str) or not source['source'].strip()); відповідний block виконується тільки коли умова true. |
| 754 | <code>_marketplace_entries</code> | <code>                                        or not source["source"].strip()):</code> | Продовження інструкції 753: Умовна гілка: isinstance(source, dict) and (not isinstance(source.get('source'), str) or not source['source'].strip()); відповідний block виконується тільки коли умова true. |
| 755 | <code>_marketplace_entries</code> | <code>            raise AuditError("{}: remote source must identify its source type".format(label))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{}: remote source must identify its source type'.format(label)) |
| 756 | <code>_marketplace_entries</code> | <code>    return entries</code> | Завершує поточну функцію та повертає entries |
| 757 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 758 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 759 | <code>_plugin_entries</code> | <code>def _plugin_entries(</code> | Оголошення функції `_plugin_entries` та її аргументів; детальний контракт розібраний вище. |
| 760 | <code>_plugin_entries</code> | <code>    plugin_root: Path, entry: Optional[dict] = None, name: Optional[str] = None</code> | Оголошення функції `_plugin_entries` та її аргументів; детальний контракт розібраний вище. |
| 761 | <code>_plugin_entries</code> | <code>) -&gt; List[Entry]:</code> | Оголошення функції `_plugin_entries` та її аргументів; детальний контракт розібраний вище. |
| 762 | <code>_plugin_entries</code> | <code>    """Everything one plugin adds to the listing: skills and commands.</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 763 | <code>_plugin_entries</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 764 | <code>_plugin_entries</code> | <code>    Skills: default `skills/&lt;name&gt;/SKILL.md`, plus any manifest `skills` paths</code> | Продовження інструкції 762: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 765 | <code>_plugin_entries</code> | <code>    (a folder of skill folders, or one folder holding SKILL.md); a plugin with</code> | Продовження інструкції 762: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 766 | <code>_plugin_entries</code> | <code>    only a root SKILL.md loads as a single skill. Commands: `commands/*.md`,</code> | Продовження інструкції 762: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 767 | <code>_plugin_entries</code> | <code>    unless the manifest `commands` key replaces that default. With no</code> | Продовження інструкції 762: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 768 | <code>_plugin_entries</code> | <code>    plugin.json, the marketplace entry is the manifest.</code> | Продовження інструкції 762: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 769 | <code>_plugin_entries</code> | <code>    Unsupported manifest shapes are diagnosed rather than silently skipped.</code> | Продовження інструкції 762: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 770 | <code>_plugin_entries</code> | <code>    """</code> | Продовження інструкції 762: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 771 | <code>_plugin_entries</code> | <code>    manifest_path = plugin_root / ".claude-plugin" / "plugin.json"</code> | Обчислює та зберігає manifest_path ← plugin_root / '.claude-plugin' / 'plugin.json' |
| 772 | <code>_plugin_entries</code> | <code>    loaded = _read_json(manifest_path)</code> | Обчислює та зберігає loaded ← _read_json(manifest_path) |
| 773 | <code>_plugin_entries</code> | <code>    if loaded is not None and entry:</code> | Умовна гілка: loaded is not None and entry; відповідний block виконується тільки коли умова true. |
| 774 | <code>_plugin_entries</code> | <code>        components = [key for key in ("skills", "commands", "agents", "hooks", "mcpServers",</code> | Обчислює та зберігає components ← [key for key in ('skills', 'commands', 'agents', 'hooks', 'mcpServers', 'lspServers', 'outputStyles') if key in entry] |
| 775 | <code>_plugin_entries</code> | <code>                                     "lspServers", "outputStyles") if key in entry]</code> | Продовження інструкції 774: Обчислює та зберігає components ← [key for key in ('skills', 'commands', 'agents', 'hooks', 'mcpServers', 'lspServers', 'outputStyles') if key in entry] |
| 776 | <code>_plugin_entries</code> | <code>        if components and entry.get("strict", True) is False:</code> | Умовна гілка: components and entry.get('strict', True) is False; відповідний block виконується тільки коли умова true. |
| 777 | <code>_plugin_entries</code> | <code>            raise AuditError("{}: strict:false conflicts with marketplace component fields: {}".format(</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{}: strict:false conflicts with marketplace component fields: {}'.format(manifest_path, ', '.join(components))) |
| 778 | <code>_plugin_entries</code> | <code>                manifest_path, ", ".join(components)))</code> | Продовження інструкції 777: Відхиляє unsupported/failed input або передає error вище: AuditError('{}: strict:false conflicts with marketplace component fields: {}'.format(manifest_path, ', '.join(components))) |
| 779 | <code>_plugin_entries</code> | <code>        listing_components = [key for key in components if key in ("skills", "commands")]</code> | Обчислює та зберігає listing_components ← [key for key in components if key in ('skills', 'commands')] |
| 780 | <code>_plugin_entries</code> | <code>        if listing_components:</code> | Умовна гілка: listing_components; відповідний block виконується тільки коли умова true. |
| 781 | <code>_plugin_entries</code> | <code>            raise AuditError("{}: unsupported marketplace component extensions alongside plugin.json: {}. "</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{}: unsupported marketplace component extensions alongside plugin.json: {}. Audit the component directories explicitly or use --all.'.format(manifest_path, ', '.join(listing_components))) |
| 782 | <code>_plugin_entries</code> | <code>                             "Audit the component directories explicitly or use --all.".format(</code> | Продовження інструкції 781: Відхиляє unsupported/failed input або передає error вище: AuditError('{}: unsupported marketplace component extensions alongside plugin.json: {}. Audit the component directories explicitly or use --all.'.format(manifest_path, ', '.join(listing_components))) |
| 783 | <code>_plugin_entries</code> | <code>                                 manifest_path, ", ".join(listing_components)))</code> | Продовження інструкції 781: Відхиляє unsupported/failed input або передає error вище: AuditError('{}: unsupported marketplace component extensions alongside plugin.json: {}. Audit the component directories explicitly or use --all.'.format(manifest_path, ', '.join(listing_components))) |
| 784 | <code>_plugin_entries</code> | <code>    manifest = loaded if loaded is not None else entry or {}</code> | Обчислює та зберігає manifest ← loaded if loaded is not None else entry or {} |
| 785 | <code>_plugin_entries</code> | <code>    label = str(manifest_path)</code> | Обчислює та зберігає label ← str(manifest_path) |
| 786 | <code>_plugin_entries</code> | <code>    if loaded is not None and "name" not in loaded:</code> | Умовна гілка: loaded is not None and 'name' not in loaded; відповідний block виконується тільки коли умова true. |
| 787 | <code>_plugin_entries</code> | <code>        raise AuditError("{}: name is required".format(label))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{}: name is required'.format(label)) |
| 788 | <code>_plugin_entries</code> | <code>    _validate_plugin_manifest(manifest, label)</code> | Виконує виклик _validate_plugin_manifest: _validate_plugin_manifest(manifest, label) |
| 789 | <code>_plugin_entries</code> | <code>    plugin = str(manifest.get("name") or name or (entry or {}).get("name")</code> | Обчислює та зберігає plugin ← str(manifest.get('name') or name or (entry or {}).get('name') or plugin_root.resolve().name) |
| 790 | <code>_plugin_entries</code> | <code>                 or plugin_root.resolve().name)</code> | Продовження інструкції 789: Обчислює та зберігає plugin ← str(manifest.get('name') or name or (entry or {}).get('name') or plugin_root.resolve().name) |
| 791 | <code>_plugin_entries</code> | <code>    extra = _as_paths(manifest["skills"], label + " skills") if "skills" in manifest else []</code> | Обчислює та зберігає extra ← _as_paths(manifest['skills'], label + ' skills') if 'skills' in manifest else [] |
| 792 | <code>_plugin_entries</code> | <code>    skills: List[Path] = []</code> | Типізує skills як List[Path]; initial value [] |
| 793 | <code>_plugin_entries</code> | <code>    folders = [("skills", False)] + [(p, True) for p in extra]</code> | Обчислює та зберігає folders ← [('skills', False)] + [(p, True) for p in extra] |
| 794 | <code>_plugin_entries</code> | <code>    for rel, explicit in folders:</code> | Ітерує folders і зв’язує кожен елемент із (rel, explicit) |
| 795 | <code>_plugin_entries</code> | <code>        folder = _manifest_path(plugin_root, rel, label + " skills")</code> | Обчислює та зберігає folder ← _manifest_path(plugin_root, rel, label + ' skills') |
| 796 | <code>_plugin_entries</code> | <code>        if explicit and not folder.is_dir():</code> | Умовна гілка: explicit and (not folder.is_dir()); відповідний block виконується тільки коли умова true. |
| 797 | <code>_plugin_entries</code> | <code>            raise AuditError("{} skills: component directory is missing or invalid: {}".format(label, folder))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{} skills: component directory is missing or invalid: {}'.format(label, folder)) |
| 798 | <code>_plugin_entries</code> | <code>        if (folder / "SKILL.md").is_file():</code> | Умовна гілка: (folder / 'SKILL.md').is_file(); відповідний block виконується тільки коли умова true. |
| 799 | <code>_plugin_entries</code> | <code>            skills.append(_within_root(folder / "SKILL.md", plugin_root, label + " skills"))</code> | Виконує виклик skills.append: skills.append(_within_root(folder / 'SKILL.md', plugin_root, label + ' skills')) |
| 800 | <code>_plugin_entries</code> | <code>        else:</code> | Alternative branch для попередньої умови або завершення циклу без break. |
| 801 | <code>_plugin_entries</code> | <code>            skills.extend(_within_root(p, plugin_root, label + " skills")</code> | Виконує виклик skills.extend: skills.extend((_within_root(p, plugin_root, label + ' skills') for p in _inventory_files(folder, 'SKILL.md', shallow=True, missing_ok=not explicit))) |
| 802 | <code>_plugin_entries</code> | <code>                          for p in _inventory_files(folder, "SKILL.md", shallow=True,</code> | Продовження інструкції 801: Виконує виклик skills.extend: skills.extend((_within_root(p, plugin_root, label + ' skills') for p in _inventory_files(folder, 'SKILL.md', shallow=True, missing_ok=not explicit))) |
| 803 | <code>_plugin_entries</code> | <code>                                                    missing_ok=not explicit))</code> | Продовження інструкції 801: Виконує виклик skills.extend: skills.extend((_within_root(p, plugin_root, label + ' skills') for p in _inventory_files(folder, 'SKILL.md', shallow=True, missing_ok=not explicit))) |
| 804 | <code>_plugin_entries</code> | <code>    if (not skills and "skills" not in manifest and not (plugin_root / "skills").is_dir()</code> | Умовна гілка: not skills and 'skills' not in manifest and (not (plugin_root / 'skills').is_dir()) and (plugin_root / 'SKILL.md').is_file(); відповідний block виконується тільки коли умова true. |
| 805 | <code>_plugin_entries</code> | <code>            and (plugin_root / "SKILL.md").is_file()):</code> | Продовження інструкції 804: Умовна гілка: not skills and 'skills' not in manifest and (not (plugin_root / 'skills').is_dir()) and (plugin_root / 'SKILL.md').is_file(); відповідний block виконується тільки коли умова true. |
| 806 | <code>_plugin_entries</code> | <code>        skills.append(_within_root(plugin_root / "SKILL.md", plugin_root, label + " skills"))</code> | Виконує виклик skills.append: skills.append(_within_root(plugin_root / 'SKILL.md', plugin_root, label + ' skills')) |
| 807 | <code>_plugin_entries</code> | <code>    found: List[Entry] = [(p, plugin, "skill", None) for p in skills]</code> | Типізує found як List[Entry]; initial value [(p, plugin, 'skill', None) for p in skills] |
| 808 | <code>_plugin_entries</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 809 | <code>_plugin_entries</code> | <code>    command_paths = (_as_paths(manifest["commands"], label + " commands") if "commands" in manifest</code> | Обчислює та зберігає command_paths ← _as_paths(manifest['commands'], label + ' commands') if 'commands' in manifest else ['commands'] |
| 810 | <code>_plugin_entries</code> | <code>                     else ["commands"])</code> | Продовження інструкції 809: Обчислює та зберігає command_paths ← _as_paths(manifest['commands'], label + ' commands') if 'commands' in manifest else ['commands'] |
| 811 | <code>_plugin_entries</code> | <code>    for rel in command_paths:</code> | Ітерує command_paths і зв’язує кожен елемент із rel |
| 812 | <code>_plugin_entries</code> | <code>        target = _manifest_path(plugin_root, rel, label + " commands")</code> | Обчислює та зберігає target ← _manifest_path(plugin_root, rel, label + ' commands') |
| 813 | <code>_plugin_entries</code> | <code>        if "commands" in manifest and not target.exists():</code> | Умовна гілка: 'commands' in manifest and (not target.exists()); відповідний block виконується тільки коли умова true. |
| 814 | <code>_plugin_entries</code> | <code>            raise AuditError("{} commands: component path is missing: {}".format(label, target))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{} commands: component path is missing: {}'.format(label, target)) |
| 815 | <code>_plugin_entries</code> | <code>        target_is_file = target.is_file()</code> | Обчислює та зберігає target_is_file ← target.is_file() |
| 816 | <code>_plugin_entries</code> | <code>        if target_is_file:</code> | Умовна гілка: target_is_file; відповідний block виконується тільки коли умова true. |
| 817 | <code>_plugin_entries</code> | <code>            files = [target]</code> | Обчислює та зберігає files ← [target] |
| 818 | <code>_plugin_entries</code> | <code>        else:</code> | Alternative branch для попередньої умови або завершення циклу без break. |
| 819 | <code>_plugin_entries</code> | <code>            files = _inventory_files(target, "*.md", missing_ok="commands" not in manifest)</code> | Обчислює та зберігає files ← _inventory_files(target, '*.md', missing_ok='commands' not in manifest) |
| 820 | <code>_plugin_entries</code> | <code>        for path in files:</code> | Ітерує files і зв’язує кожен елемент із path |
| 821 | <code>_plugin_entries</code> | <code>            if path.suffix != ".md":</code> | Умовна гілка: path.suffix != '.md'; відповідний block виконується тільки коли умова true. |
| 822 | <code>_plugin_entries</code> | <code>                continue</code> | Пропускає решту цієї ітерації; переходить до наступного елемента. |
| 823 | <code>_plugin_entries</code> | <code>            _within_root(path, plugin_root, label + " commands")</code> | Виконує виклик _within_root: _within_root(path, plugin_root, label + ' commands') |
| 824 | <code>_plugin_entries</code> | <code>            leaf = (":".join(path.relative_to(target).with_suffix("").parts)</code> | Обчислює та зберігає leaf ← ':'.join(path.relative_to(target).with_suffix('').parts) if not target_is_file else path.stem |
| 825 | <code>_plugin_entries</code> | <code>                    if not target_is_file else path.stem)</code> | Продовження інструкції 824: Обчислює та зберігає leaf ← ':'.join(path.relative_to(target).with_suffix('').parts) if not target_is_file else path.stem |
| 826 | <code>_plugin_entries</code> | <code>            found.append((path, plugin, "command", "{}:{}".format(plugin, leaf)))</code> | Виконує виклик found.append: found.append((path, plugin, 'command', '{}:{}'.format(plugin, leaf))) |
| 827 | <code>_plugin_entries</code> | <code>    return found</code> | Завершує поточну функцію та повертає found |
| 828 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 829 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 830 | <code>manifest_skill_files</code> | <code>def manifest_skill_files(root: Path) -&gt; Optional[List[Entry]]:</code> | Оголошення функції `manifest_skill_files` та її аргументів; детальний контракт розібраний вище. |
| 831 | <code>manifest_skill_files</code> | <code>    """Skills and commands a marketplace or plugin checkout would install.</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 832 | <code>manifest_skill_files</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 833 | <code>manifest_skill_files</code> | <code>    Returns None when `root` is neither, so the caller falls back to a plain</code> | Продовження інструкції 831: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 834 | <code>manifest_skill_files</code> | <code>    recursive scan. Without this, a repo's translated docs and mirrors for</code> | Продовження інструкції 831: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 835 | <code>manifest_skill_files</code> | <code>    other harnesses (docs/ja-JP/skills, .gemini/skills, ...) were counted as</code> | Продовження інструкції 831: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 836 | <code>manifest_skill_files</code> | <code>    installed skills and inflated the bill several times over.</code> | Продовження інструкції 831: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 837 | <code>manifest_skill_files</code> | <code>    ponytail: only local (string) plugin sources resolve; github/url sources</code> | Продовження інструкції 831: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 838 | <code>manifest_skill_files</code> | <code>    are not in this checkout, so they are skipped rather than fetched.</code> | Продовження інструкції 831: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 839 | <code>manifest_skill_files</code> | <code>    """</code> | Продовження інструкції 831: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 840 | <code>manifest_skill_files</code> | <code>    found: List[Entry] = []</code> | Типізує found як List[Entry]; initial value [] |
| 841 | <code>manifest_skill_files</code> | <code>    recognized = False</code> | Обчислює та зберігає recognized ← False |
| 842 | <code>manifest_skill_files</code> | <code>    # The checkout itself can be a plugin even when its marketplace entry points</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 843 | <code>manifest_skill_files</code> | <code>    # at a remote copy of the same repo (source: github), so check both.</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 844 | <code>manifest_skill_files</code> | <code>    if (root / ".claude-plugin" / "plugin.json").is_file():</code> | Умовна гілка: (root / '.claude-plugin' / 'plugin.json').is_file(); відповідний block виконується тільки коли умова true. |
| 845 | <code>manifest_skill_files</code> | <code>        recognized = True</code> | Обчислює та зберігає recognized ← True |
| 846 | <code>manifest_skill_files</code> | <code>        found.extend(_plugin_entries(root))</code> | Виконує виклик found.extend: found.extend(_plugin_entries(root)) |
| 847 | <code>manifest_skill_files</code> | <code>    market_path = root / ".claude-plugin" / "marketplace.json"</code> | Обчислює та зберігає market_path ← root / '.claude-plugin' / 'marketplace.json' |
| 848 | <code>manifest_skill_files</code> | <code>    market = _read_json(market_path)</code> | Обчислює та зберігає market ← _read_json(market_path) |
| 849 | <code>manifest_skill_files</code> | <code>    if market is not None:</code> | Умовна гілка: market is not None; відповідний block виконується тільки коли умова true. |
| 850 | <code>manifest_skill_files</code> | <code>        recognized = True</code> | Обчислює та зберігає recognized ← True |
| 851 | <code>manifest_skill_files</code> | <code>        for entry in _marketplace_entries(market, str(market_path)):</code> | Ітерує _marketplace_entries(market, str(market_path)) і зв’язує кожен елемент із entry |
| 852 | <code>manifest_skill_files</code> | <code>            source = entry.get("source")</code> | Обчислює та зберігає source ← entry.get('source') |
| 853 | <code>manifest_skill_files</code> | <code>            if isinstance(source, str):</code> | Умовна гілка: isinstance(source, str); відповідний block виконується тільки коли умова true. |
| 854 | <code>manifest_skill_files</code> | <code>                plugin_root = _manifest_path(root, source, str(market_path) + " source")</code> | Обчислює та зберігає plugin_root ← _manifest_path(root, source, str(market_path) + ' source') |
| 855 | <code>manifest_skill_files</code> | <code>                if not plugin_root.is_dir():</code> | Умовна гілка: not plugin_root.is_dir(); відповідний block виконується тільки коли умова true. |
| 856 | <code>manifest_skill_files</code> | <code>                    raise AuditError("{} source: plugin directory is missing or invalid: {}".format(market_path, plugin_root))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{} source: plugin directory is missing or invalid: {}'.format(market_path, plugin_root)) |
| 857 | <code>manifest_skill_files</code> | <code>                found.extend(_plugin_entries(plugin_root, entry))</code> | Виконує виклик found.extend: found.extend(_plugin_entries(plugin_root, entry)) |
| 858 | <code>manifest_skill_files</code> | <code>    return found if recognized else None</code> | Завершує поточну функцію та повертає found if recognized else None |
| 859 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 860 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 861 | <code>_validate_settings</code> | <code>def _validate_settings(data: dict, label: str) -&gt; None:</code> | Оголошення функції `_validate_settings` та її аргументів; детальний контракт розібраний вище. |
| 862 | <code>_validate_settings</code> | <code>    states = {"on", "off", "name-only", "user-invocable-only"}</code> | Обчислює та зберігає states ← {'on', 'off', 'name-only', 'user-invocable-only'} |
| 863 | <code>_validate_settings</code> | <code>    for key in ("enabledPlugins", "skillOverrides", "env"):</code> | Ітерує ('enabledPlugins', 'skillOverrides', 'env') і зв’язує кожен елемент із key |
| 864 | <code>_validate_settings</code> | <code>        if key in data and not isinstance(data[key], dict):</code> | Умовна гілка: key in data and (not isinstance(data[key], dict)); відповідний block виконується тільки коли умова true. |
| 865 | <code>_validate_settings</code> | <code>            raise AuditError("{}: {} must be an object".format(label, key))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{}: {} must be an object'.format(label, key)) |
| 866 | <code>_validate_settings</code> | <code>    for key, value in data.get("enabledPlugins", {}).items():</code> | Ітерує data.get('enabledPlugins', {}).items() і зв’язує кожен елемент із (key, value) |
| 867 | <code>_validate_settings</code> | <code>        if not isinstance(key, str) or not isinstance(value, bool):</code> | Умовна гілка: not isinstance(key, str) or not isinstance(value, bool); відповідний block виконується тільки коли умова true. |
| 868 | <code>_validate_settings</code> | <code>            raise AuditError("{}: enabledPlugins entries must be booleans".format(label))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{}: enabledPlugins entries must be booleans'.format(label)) |
| 869 | <code>_validate_settings</code> | <code>    for key, value in data.get("skillOverrides", {}).items():</code> | Ітерує data.get('skillOverrides', {}).items() і зв’язує кожен елемент із (key, value) |
| 870 | <code>_validate_settings</code> | <code>        if not isinstance(key, str) or not isinstance(value, str) or value not in states:</code> | Умовна гілка: not isinstance(key, str) or not isinstance(value, str) or value not in states; відповідний block виконується тільки коли умова true. |
| 871 | <code>_validate_settings</code> | <code>            raise AuditError("{}: skillOverrides entries must be on, off, name-only or user-invocable-only".format(label))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{}: skillOverrides entries must be on, off, name-only or user-invocable-only'.format(label)) |
| 872 | <code>_validate_settings</code> | <code>    if any(not isinstance(value, str) for value in data.get("env", {}).values()):</code> | Умовна гілка: any((not isinstance(value, str) for value in data.get('env', {}).values())); відповідний block виконується тільки коли умова true. |
| 873 | <code>_validate_settings</code> | <code>        raise AuditError("{}: env values must be strings".format(label))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{}: env values must be strings'.format(label)) |
| 874 | <code>_validate_settings</code> | <code>    if "skillListingBudgetFraction" in data:</code> | Умовна гілка: 'skillListingBudgetFraction' in data; відповідний block виконується тільки коли умова true. |
| 875 | <code>_validate_settings</code> | <code>        value = data["skillListingBudgetFraction"]</code> | Обчислює та зберігає value ← data['skillListingBudgetFraction'] |
| 876 | <code>_validate_settings</code> | <code>        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 &lt; value &lt;= 1 or not math.isfinite(value):</code> | Умовна гілка: isinstance(value, bool) or not isinstance(value, (int, float)) or (not 0 &lt; value &lt;= 1) or (not math.isfinite(value)); відповідний block виконується тільки коли умова true. |
| 877 | <code>_validate_settings</code> | <code>            raise AuditError("{}: skillListingBudgetFraction must be finite and in (0, 1]".format(label))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{}: skillListingBudgetFraction must be finite and in (0, 1]'.format(label)) |
| 878 | <code>_validate_settings</code> | <code>    if "skillListingMaxDescChars" in data and (type(data["skillListingMaxDescChars"]) is not int</code> | Умовна гілка: 'skillListingMaxDescChars' in data and (type(data['skillListingMaxDescChars']) is not int or data['skillListingMaxDescChars'] != LISTING_CHAR_CAP); відповідний block виконується тільки коли умова true. |
| 879 | <code>_validate_settings</code> | <code>                                               or data["skillListingMaxDescChars"] != LISTING_CHAR_CAP):</code> | Продовження інструкції 878: Умовна гілка: 'skillListingMaxDescChars' in data and (type(data['skillListingMaxDescChars']) is not int or data['skillListingMaxDescChars'] != LISTING_CHAR_CAP); відповідний block виконується тільки коли умова true. |
| 880 | <code>_validate_settings</code> | <code>        raise AuditError("{}: this profile models skillListingMaxDescChars={} only".format(label, LISTING_CHAR_CAP))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{}: this profile models skillListingMaxDescChars={} only'.format(label, LISTING_CHAR_CAP)) |
| 881 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 882 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 883 | <code>load_settings</code> | <code>def load_settings(home: Path, cwd: Path) -&gt; dict:</code> | Оголошення функції `load_settings` та її аргументів; детальний контракт розібраний вище. |
| 884 | <code>load_settings</code> | <code>    """Merge Claude Code settings: user, then project, then local (later wins;</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 885 | <code>load_settings</code> | <code>    enabledPlugins, skillOverrides and env merge key by key)."""</code> | Продовження інструкції 884: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 886 | <code>load_settings</code> | <code>    merged: dict = {}</code> | Типізує merged як dict; initial value {} |
| 887 | <code>load_settings</code> | <code>    files = [home / ".claude" / "settings.json"]</code> | Обчислює та зберігає files ← [home / '.claude' / 'settings.json'] |
| 888 | <code>load_settings</code> | <code>    for folder in reversed(_project_dirs(cwd)):</code> | Ітерує reversed(_project_dirs(cwd)) і зв’язує кожен елемент із folder |
| 889 | <code>load_settings</code> | <code>        files += [folder / ".claude" / "settings.json", folder / ".claude" / "settings.local.json"]</code> | Оновлює накопичене значення: files += [folder / '.claude' / 'settings.json', folder / '.claude' / 'settings.local.json'] |
| 890 | <code>load_settings</code> | <code>    for path in files:</code> | Ітерує files і зв’язує кожен елемент із path |
| 891 | <code>load_settings</code> | <code>        data = _read_json(path) or {}</code> | Обчислює та зберігає data ← _read_json(path) or {} |
| 892 | <code>load_settings</code> | <code>        _validate_settings(data, str(path))</code> | Виконує виклик _validate_settings: _validate_settings(data, str(path)) |
| 893 | <code>load_settings</code> | <code>        for key, value in data.items():</code> | Ітерує data.items() і зв’язує кожен елемент із (key, value) |
| 894 | <code>load_settings</code> | <code>            if isinstance(value, dict) and isinstance(merged.get(key), dict):</code> | Умовна гілка: isinstance(value, dict) and isinstance(merged.get(key), dict); відповідний block виконується тільки коли умова true. |
| 895 | <code>load_settings</code> | <code>                merged[key] = dict(merged[key], **value)</code> | Обчислює та зберігає merged[key] ← dict(merged[key], **value) |
| 896 | <code>load_settings</code> | <code>            else:</code> | Alternative branch для попередньої умови або завершення циклу без break. |
| 897 | <code>load_settings</code> | <code>                merged[key] = value</code> | Обчислює та зберігає merged[key] ← value |
| 898 | <code>load_settings</code> | <code>    return merged</code> | Завершує поточну функцію та повертає merged |
| 899 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 900 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 901 | <code>installed_plugin_entries</code> | <code>def installed_plugin_entries(home: Path, settings: dict) -&gt; Optional[List[Entry]]:</code> | Оголошення функції `installed_plugin_entries` та її аргументів; детальний контракт розібраний вище. |
| 902 | <code>installed_plugin_entries</code> | <code>    """Skills and commands of the plugins enabled in settings.</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 903 | <code>installed_plugin_entries</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 904 | <code>installed_plugin_entries</code> | <code>    Resolves each `name@marketplace` through installed_plugins.json (the install</code> | Продовження інструкції 902: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 905 | <code>installed_plugin_entries</code> | <code>    cache) and, for directory marketplaces loaded in place, through</code> | Продовження інструкції 902: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 906 | <code>installed_plugin_entries</code> | <code>    known_marketplaces.json. An absent enabledPlugins setting means no enabled</code> | Продовження інструкції 902: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 907 | <code>installed_plugin_entries</code> | <code>    plugins; blindly scanning the cache would count disabled installations.</code> | Продовження інструкції 902: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 908 | <code>installed_plugin_entries</code> | <code>    """</code> | Продовження інструкції 902: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 909 | <code>installed_plugin_entries</code> | <code>    _validate_settings(settings, "settings")</code> | Виконує виклик _validate_settings: _validate_settings(settings, 'settings') |
| 910 | <code>installed_plugin_entries</code> | <code>    enabled = settings.get("enabledPlugins", {})</code> | Обчислює та зберігає enabled ← settings.get('enabledPlugins', {}) |
| 911 | <code>installed_plugin_entries</code> | <code>    if not enabled:</code> | Умовна гілка: not enabled; відповідний block виконується тільки коли умова true. |
| 912 | <code>installed_plugin_entries</code> | <code>        return []</code> | Завершує поточну функцію та повертає [] |
| 913 | <code>installed_plugin_entries</code> | <code>    plugins_dir = home / ".claude" / "plugins"</code> | Обчислює та зберігає plugins_dir ← home / '.claude' / 'plugins' |
| 914 | <code>installed_plugin_entries</code> | <code>    installed_path = plugins_dir / "installed_plugins.json"</code> | Обчислює та зберігає installed_path ← plugins_dir / 'installed_plugins.json' |
| 915 | <code>installed_plugin_entries</code> | <code>    installed = (_read_json(installed_path) or {}).get("plugins", {})</code> | Обчислює та зберігає installed ← (_read_json(installed_path) or {}).get('plugins', {}) |
| 916 | <code>installed_plugin_entries</code> | <code>    if not isinstance(installed, dict):</code> | Умовна гілка: not isinstance(installed, dict); відповідний block виконується тільки коли умова true. |
| 917 | <code>installed_plugin_entries</code> | <code>        raise AuditError("{}: plugins must be an object".format(installed_path))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{}: plugins must be an object'.format(installed_path)) |
| 918 | <code>installed_plugin_entries</code> | <code>    for installs in installed.values():</code> | Ітерує installed.values() і зв’язує кожен елемент із installs |
| 919 | <code>installed_plugin_entries</code> | <code>        if not isinstance(installs, list) or any(not isinstance(i, dict) for i in installs):</code> | Умовна гілка: not isinstance(installs, list) or any((not isinstance(i, dict) for i in installs)); відповідний block виконується тільки коли умова true. |
| 920 | <code>installed_plugin_entries</code> | <code>            raise AuditError("{}: plugin installations must be arrays of objects".format(installed_path))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{}: plugin installations must be arrays of objects'.format(installed_path)) |
| 921 | <code>installed_plugin_entries</code> | <code>        for install in installs:</code> | Ітерує installs і зв’язує кожен елемент із install |
| 922 | <code>installed_plugin_entries</code> | <code>            if "installPath" in install and not isinstance(install["installPath"], str):</code> | Умовна гілка: 'installPath' in install and (not isinstance(install['installPath'], str)); відповідний block виконується тільки коли умова true. |
| 923 | <code>installed_plugin_entries</code> | <code>                raise AuditError("{}: installPath must be a string".format(installed_path))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{}: installPath must be a string'.format(installed_path)) |
| 924 | <code>installed_plugin_entries</code> | <code>    markets_path = plugins_dir / "known_marketplaces.json"</code> | Обчислює та зберігає markets_path ← plugins_dir / 'known_marketplaces.json' |
| 925 | <code>installed_plugin_entries</code> | <code>    markets = _read_json(markets_path) or {}</code> | Обчислює та зберігає markets ← _read_json(markets_path) or {} |
| 926 | <code>installed_plugin_entries</code> | <code>    for info in markets.values():</code> | Ітерує markets.values() і зв’язує кожен елемент із info |
| 927 | <code>installed_plugin_entries</code> | <code>        if not isinstance(info, dict) or ("source" in info and not isinstance(info["source"], dict)):</code> | Умовна гілка: not isinstance(info, dict) or ('source' in info and (not isinstance(info['source'], dict))); відповідний block виконується тільки коли умова true. |
| 928 | <code>installed_plugin_entries</code> | <code>            raise AuditError("{}: marketplace entries and sources must be objects".format(markets_path))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{}: marketplace entries and sources must be objects'.format(markets_path)) |
| 929 | <code>installed_plugin_entries</code> | <code>        for location in (info.get("installLocation"), info.get("source", {}).get("path")):</code> | Ітерує (info.get('installLocation'), info.get('source', {}).get('path')) і зв’язує кожен елемент із location |
| 930 | <code>installed_plugin_entries</code> | <code>            if location is not None and not isinstance(location, str):</code> | Умовна гілка: location is not None and (not isinstance(location, str)); відповідний block виконується тільки коли умова true. |
| 931 | <code>installed_plugin_entries</code> | <code>                raise AuditError("{}: marketplace locations must be strings".format(markets_path))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{}: marketplace locations must be strings'.format(markets_path)) |
| 932 | <code>installed_plugin_entries</code> | <code>    found: List[Entry] = []</code> | Типізує found як List[Entry]; initial value [] |
| 933 | <code>installed_plugin_entries</code> | <code>    for key, on in sorted(enabled.items()):</code> | Ітерує sorted(enabled.items()) і зв’язує кожен елемент із (key, on) |
| 934 | <code>installed_plugin_entries</code> | <code>        if on is not True:</code> | Умовна гілка: on is not True; відповідний block виконується тільки коли умова true. |
| 935 | <code>installed_plugin_entries</code> | <code>            continue</code> | Пропускає решту цієї ітерації; переходить до наступного елемента. |
| 936 | <code>installed_plugin_entries</code> | <code>        name, _, market = key.partition("@")</code> | Обчислює та зберігає (name, _, market) ← key.partition('@') |
| 937 | <code>installed_plugin_entries</code> | <code>        root: Optional[Path] = None</code> | Типізує root як Optional[Path]; initial value None |
| 938 | <code>installed_plugin_entries</code> | <code>        entry: Optional[dict] = None</code> | Типізує entry як Optional[dict]; initial value None |
| 939 | <code>installed_plugin_entries</code> | <code>        installed_roots: Dict[Path, Path] = {}</code> | Типізує installed_roots як Dict[Path, Path]; initial value {} |
| 940 | <code>installed_plugin_entries</code> | <code>        for install in installed.get(key) or []:</code> | Ітерує installed.get(key) or [] і зв’язує кожен елемент із install |
| 941 | <code>installed_plugin_entries</code> | <code>            path = Path(str((install or {}).get("installPath", "")))</code> | Обчислює та зберігає path ← Path(str((install or {}).get('installPath', ''))) |
| 942 | <code>installed_plugin_entries</code> | <code>            if str(path) not in ("", ".") and path.is_dir():</code> | Умовна гілка: str(path) not in ('', '.') and path.is_dir(); відповідний block виконується тільки коли умова true. |
| 943 | <code>installed_plugin_entries</code> | <code>                installed_roots.setdefault(path.resolve(), path)</code> | Виконує виклик installed_roots.setdefault: installed_roots.setdefault(path.resolve(), path) |
| 944 | <code>installed_plugin_entries</code> | <code>        if len(installed_roots) &gt; 1:</code> | Умовна гілка: len(installed_roots) &gt; 1; відповідний block виконується тільки коли умова true. |
| 945 | <code>installed_plugin_entries</code> | <code>            raise AuditError("{}: enabled plugin {} has multiple installation roots; "</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{}: enabled plugin {} has multiple installation roots; scoped registry selection is outside this profile. Pass an explicit plugin path to audit.'.format(installed_path, key)) |
| 946 | <code>installed_plugin_entries</code> | <code>                             "scoped registry selection is outside this profile. "</code> | Продовження інструкції 945: Відхиляє unsupported/failed input або передає error вище: AuditError('{}: enabled plugin {} has multiple installation roots; scoped registry selection is outside this profile. Pass an explicit plugin path to audit.'.format(installed_path, key)) |
| 947 | <code>installed_plugin_entries</code> | <code>                             "Pass an explicit plugin path to audit.".format(installed_path, key))</code> | Продовження інструкції 945: Відхиляє unsupported/failed input або передає error вище: AuditError('{}: enabled plugin {} has multiple installation roots; scoped registry selection is outside this profile. Pass an explicit plugin path to audit.'.format(installed_path, key)) |
| 948 | <code>installed_plugin_entries</code> | <code>        if installed_roots:</code> | Умовна гілка: installed_roots; відповідний block виконується тільки коли умова true. |
| 949 | <code>installed_plugin_entries</code> | <code>            root = next(iter(installed_roots.values()))</code> | Обчислює та зберігає root ← next(iter(installed_roots.values())) |
| 950 | <code>installed_plugin_entries</code> | <code>        info = markets.get(market)</code> | Обчислює та зберігає info ← markets.get(market) |
| 951 | <code>installed_plugin_entries</code> | <code>        if not isinstance(info, dict):</code> | Умовна гілка: not isinstance(info, dict); відповідний block виконується тільки коли умова true. |
| 952 | <code>installed_plugin_entries</code> | <code>            info = {}</code> | Обчислює та зберігає info ← {} |
| 953 | <code>installed_plugin_entries</code> | <code>        location = info.get("installLocation") or info.get("source", {}).get("path")</code> | Обчислює та зберігає location ← info.get('installLocation') or info.get('source', {}).get('path') |
| 954 | <code>installed_plugin_entries</code> | <code>        if location:</code> | Умовна гілка: location; відповідний block виконується тільки коли умова true. |
| 955 | <code>installed_plugin_entries</code> | <code>            catalog_path = Path(location) / ".claude-plugin" / "marketplace.json"</code> | Обчислює та зберігає catalog_path ← Path(location) / '.claude-plugin' / 'marketplace.json' |
| 956 | <code>installed_plugin_entries</code> | <code>            catalog = _read_json(catalog_path) or {}</code> | Обчислює та зберігає catalog ← _read_json(catalog_path) or {} |
| 957 | <code>installed_plugin_entries</code> | <code>            entry = next((p for p in _marketplace_entries(catalog, str(catalog_path))</code> | Обчислює та зберігає entry ← next((p for p in _marketplace_entries(catalog, str(catalog_path)) if p.get('name') == name), None) |
| 958 | <code>installed_plugin_entries</code> | <code>                          if p.get("name") == name), None)</code> | Продовження інструкції 957: Обчислює та зберігає entry ← next((p for p in _marketplace_entries(catalog, str(catalog_path)) if p.get('name') == name), None) |
| 959 | <code>installed_plugin_entries</code> | <code>            if root is None and entry and isinstance(entry.get("source"), str):</code> | Умовна гілка: root is None and entry and isinstance(entry.get('source'), str); відповідний block виконується тільки коли умова true. |
| 960 | <code>installed_plugin_entries</code> | <code>                candidate = _manifest_path(Path(location), entry["source"], str(catalog_path) + " source")</code> | Обчислює та зберігає candidate ← _manifest_path(Path(location), entry['source'], str(catalog_path) + ' source') |
| 961 | <code>installed_plugin_entries</code> | <code>                if not candidate.is_dir():</code> | Умовна гілка: not candidate.is_dir(); відповідний block виконується тільки коли умова true. |
| 962 | <code>installed_plugin_entries</code> | <code>                    raise AuditError("{} source: plugin directory is missing or invalid: {}".format(catalog_path, candidate))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{} source: plugin directory is missing or invalid: {}'.format(catalog_path, candidate)) |
| 963 | <code>installed_plugin_entries</code> | <code>                root = candidate</code> | Обчислює та зберігає root ← candidate |
| 964 | <code>installed_plugin_entries</code> | <code>        if root is not None:</code> | Умовна гілка: root is not None; відповідний block виконується тільки коли умова true. |
| 965 | <code>installed_plugin_entries</code> | <code>            found.extend(_plugin_entries(root, entry, name))</code> | Виконує виклик found.extend: found.extend(_plugin_entries(root, entry, name)) |
| 966 | <code>installed_plugin_entries</code> | <code>        else:</code> | Alternative branch для попередньої умови або завершення циклу без break. |
| 967 | <code>installed_plugin_entries</code> | <code>            raise AuditError("enabled plugin {} could not be resolved to a local installation".format(key))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('enabled plugin {} could not be resolved to a local installation'.format(key)) |
| 968 | <code>installed_plugin_entries</code> | <code>    return found</code> | Завершує поточну функцію та повертає found |
| 969 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 970 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 971 | <code>discover</code> | <code>def discover(</code> | Оголошення функції `discover` та її аргументів; детальний контракт розібраний вище. |
| 972 | <code>discover</code> | <code>    roots: Sequence[Path],</code> | Оголошення функції `discover` та її аргументів; детальний контракт розібраний вище. |
| 973 | <code>discover</code> | <code>    shallow_roots: Sequence[Path] = (),</code> | Оголошення функції `discover` та її аргументів; детальний контракт розібраний вище. |
| 974 | <code>discover</code> | <code>    scan_all: bool = False,</code> | Оголошення функції `discover` та її аргументів; детальний контракт розібраний вище. |
| 975 | <code>discover</code> | <code>    extra: Sequence[Entry] = (),</code> | Оголошення функції `discover` та її аргументів; детальний контракт розібраний вище. |
| 976 | <code>discover</code> | <code>) -&gt; List[Skill]:</code> | Оголошення функції `discover` та її аргументів; детальний контракт розібраний вище. |
| 977 | <code>discover</code> | <code>    """Find and load every unique skill under the roots, plus `extra` entries.</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 978 | <code>discover</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 979 | <code>discover</code> | <code>    A root in `shallow_roots` is scanned one level deep (`*/SKILL.md`), the way</code> | Продовження інструкції 977: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 980 | <code>discover</code> | <code>    Claude Code loads an install directory: a whole repo dropped into</code> | Продовження інструкції 977: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 981 | <code>discover</code> | <code>    `~/.claude/skills/foo/` is one skill at `foo/SKILL.md`, not every nested</code> | Продовження інструкції 977: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 982 | <code>discover</code> | <code>    SKILL.md it happens to contain. A marketplace or plugin checkout is read</code> | Продовження інструкції 977: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 983 | <code>discover</code> | <code>    through its manifest, so only what Claude Code would install is counted.</code> | Продовження інструкції 977: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 984 | <code>discover</code> | <code>    Any other root is scanned recursively; `scan_all` forces that everywhere.</code> | Продовження інструкції 977: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 985 | <code>discover</code> | <code>    """</code> | Продовження інструкції 977: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 986 | <code>discover</code> | <code>    shallow = {Path(r) for r in shallow_roots}</code> | Обчислює та зберігає shallow ← {Path(r) for r in shallow_roots} |
| 987 | <code>discover</code> | <code>    entries: List[Entry] = []</code> | Типізує entries як List[Entry]; initial value [] |
| 988 | <code>discover</code> | <code>    for root in roots:</code> | Ітерує roots і зв’язує кожен елемент із root |
| 989 | <code>discover</code> | <code>        manifest = None if (scan_all or root.is_file()) else manifest_skill_files(root)</code> | Обчислює та зберігає manifest ← None if scan_all or root.is_file() else manifest_skill_files(root) |
| 990 | <code>discover</code> | <code>        if root.is_file():</code> | Умовна гілка: root.is_file(); відповідний block виконується тільки коли умова true. |
| 991 | <code>discover</code> | <code>            found: Iterable[Entry] = [(root, None, "skill", None)]</code> | Типізує found як Iterable[Entry]; initial value [(root, None, 'skill', None)] |
| 992 | <code>discover</code> | <code>        elif root in shallow and not scan_all:</code> | Наступна умовна гілка, коли попередній if/elif не виконався. |
| 993 | <code>discover</code> | <code>            found = [(p, None, "skill", None)</code> | Обчислює та зберігає found ← [(p, None, 'skill', None) for p in _inventory_files(root, 'SKILL.md', shallow=True)] |
| 994 | <code>discover</code> | <code>                     for p in _inventory_files(root, "SKILL.md", shallow=True)]</code> | Продовження інструкції 993: Обчислює та зберігає found ← [(p, None, 'skill', None) for p in _inventory_files(root, 'SKILL.md', shallow=True)] |
| 995 | <code>discover</code> | <code>        elif manifest is not None:</code> | Наступна умовна гілка, коли попередній if/elif не виконався. |
| 996 | <code>discover</code> | <code>            found = manifest</code> | Обчислює та зберігає found ← manifest |
| 997 | <code>discover</code> | <code>        else:</code> | Alternative branch для попередньої умови або завершення циклу без break. |
| 998 | <code>discover</code> | <code>            found = [(p, None, "skill", None) for p in _inventory_files(root, "SKILL.md")]</code> | Обчислює та зберігає found ← [(p, None, 'skill', None) for p in _inventory_files(root, 'SKILL.md')] |
| 999 | <code>discover</code> | <code>        entries.extend(found)</code> | Виконує виклик entries.extend: entries.extend(found) |
| 1000 | <code>discover</code> | <code>    seen: Set[Path] = set()</code> | Типізує seen як Set[Path]; initial value set() |
| 1001 | <code>discover</code> | <code>    unique: List[Entry] = []</code> | Типізує unique як List[Entry]; initial value [] |
| 1002 | <code>discover</code> | <code>    for item in list(entries) + list(extra):</code> | Ітерує list(entries) + list(extra) і зв’язує кожен елемент із item |
| 1003 | <code>discover</code> | <code>        try:</code> | Межа обробки винятків: виконати block і застосувати specified handlers. |
| 1004 | <code>discover</code> | <code>            resolved = item[0].resolve()</code> | Обчислює та зберігає resolved ← item[0].resolve() |
| 1005 | <code>discover</code> | <code>        except RuntimeError as exc:</code> | Handler для зазначеного типу винятку; operational finding/fallback залежить від body нижче. |
| 1006 | <code>discover</code> | <code>            raise AuditError("could not resolve discovered path {}: {}".format(item[0], exc)) from None</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('could not resolve discovered path {}: {}'.format(item[0], exc)) |
| 1007 | <code>discover</code> | <code>        except OSError:</code> | Handler для зазначеного типу винятку; operational finding/fallback залежить від body нижче. |
| 1008 | <code>discover</code> | <code>            resolved = item[0]</code> | Обчислює та зберігає resolved ← item[0] |
| 1009 | <code>discover</code> | <code>        if resolved in seen:</code> | Умовна гілка: resolved in seen; відповідний block виконується тільки коли умова true. |
| 1010 | <code>discover</code> | <code>            continue</code> | Пропускає решту цієї ітерації; переходить до наступного елемента. |
| 1011 | <code>discover</code> | <code>        seen.add(resolved)</code> | Виконує виклик seen.add: seen.add(resolved) |
| 1012 | <code>discover</code> | <code>        unique.append(item)</code> | Виконує виклик unique.append: unique.append(item) |
| 1013 | <code>discover</code> | <code>    if not unique:</code> | Умовна гілка: not unique; відповідний block виконується тільки коли умова true. |
| 1014 | <code>discover</code> | <code>        return []</code> | Завершує поточну функцію та повертає [] |
| 1015 | <code>discover</code> | <code>    # Reads are I/O bound (often on an external disk); load in parallel but</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 1016 | <code>discover</code> | <code>    # keep discovery order so output is deterministic.</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 1017 | <code>discover</code> | <code>    workers = min(32, (os.cpu_count() or 4) * 4, len(unique))</code> | Обчислює та зберігає workers ← min(32, (os.cpu_count() or 4) * 4, len(unique)) |
| 1018 | <code>discover</code> | <code>    with ThreadPoolExecutor(max_workers=workers) as pool:</code> | Керує lifetime/закриттям context resources: ThreadPoolExecutor(max_workers=workers) |
| 1019 | <code>discover</code> | <code>        return list(pool.map(lambda item: load_skill(*item), unique))</code> | Завершує поточну функцію та повертає list(pool.map(lambda item: load_skill(*item), unique)) |
| 1020 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1021 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1022 | <code>&lt;module&gt;</code> | <code># --- Usage evidence -------------------------------------------------------</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 1023 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1024 | <code>&lt;module&gt;</code> | <code># A skill or command the user typed as /name is logged in their own message.</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 1025 | <code>&lt;module&gt;</code> | <code>_TYPED_COMMAND_RE = re.compile(r"&lt;command-name&gt;/?([^&lt;\s]+)&lt;/command-name&gt;")</code> | Обчислює та зберігає _TYPED_COMMAND_RE ← re.compile('&lt;command-name&gt;/?([^&lt;\\s]+)&lt;/command-name&gt;') |
| 1026 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1027 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1028 | <code>usage_counts</code> | <code>def usage_counts(transcript_root: Optional[Path] = None) -&gt; Dict[str, int]:</code> | Оголошення функції `usage_counts` та її аргументів; детальний контракт розібраний вище. |
| 1029 | <code>usage_counts</code> | <code>    """Count real invocations in local Claude Code transcripts: Skill tool calls</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1030 | <code>usage_counts</code> | <code>    made by the model, plus /commands the user typed."""</code> | Продовження інструкції 1029: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1031 | <code>usage_counts</code> | <code>    root = transcript_root or (Path.home() / ".claude" / "projects")</code> | Обчислює та зберігає root ← transcript_root or Path.home() / '.claude' / 'projects' |
| 1032 | <code>usage_counts</code> | <code>    counts: Dict[str, int] = {}</code> | Типізує counts як Dict[str, int]; initial value {} |
| 1033 | <code>usage_counts</code> | <code>    if not root.is_dir():</code> | Умовна гілка: not root.is_dir(); відповідний block виконується тільки коли умова true. |
| 1034 | <code>usage_counts</code> | <code>        return counts</code> | Завершує поточну функцію та повертає counts |
| 1035 | <code>usage_counts</code> | <code>    for jsonl in root.rglob("*.jsonl"):</code> | Ітерує root.rglob('*.jsonl') і зв’язує кожен елемент із jsonl |
| 1036 | <code>usage_counts</code> | <code>        try:</code> | Межа обробки винятків: виконати block і застосувати specified handlers. |
| 1037 | <code>usage_counts</code> | <code>            with jsonl.open("r", encoding="utf-8", errors="replace") as handle:</code> | Керує lifetime/закриттям context resources: jsonl.open('r', encoding='utf-8', errors='replace') |
| 1038 | <code>usage_counts</code> | <code>                for line in handle:</code> | Ітерує handle і зв’язує кожен елемент із line |
| 1039 | <code>usage_counts</code> | <code>                    try:</code> | Межа обробки винятків: виконати block і застосувати specified handlers. |
| 1040 | <code>usage_counts</code> | <code>                        record = json.loads(line)</code> | Обчислює та зберігає record ← json.loads(line) |
| 1041 | <code>usage_counts</code> | <code>                    except (ValueError, RecursionError):</code> | Handler для зазначеного типу винятку; operational finding/fallback залежить від body нижче. |
| 1042 | <code>usage_counts</code> | <code>                        continue</code> | Пропускає решту цієї ітерації; переходить до наступного елемента. |
| 1043 | <code>usage_counts</code> | <code>                    if not isinstance(record, dict):</code> | Умовна гілка: not isinstance(record, dict); відповідний block виконується тільки коли умова true. |
| 1044 | <code>usage_counts</code> | <code>                        continue</code> | Пропускає решту цієї ітерації; переходить до наступного елемента. |
| 1045 | <code>usage_counts</code> | <code>                    kind = record.get("type")</code> | Обчислює та зберігає kind ← record.get('type') |
| 1046 | <code>usage_counts</code> | <code>                    message = record.get("message")</code> | Обчислює та зберігає message ← record.get('message') |
| 1047 | <code>usage_counts</code> | <code>                    content = message.get("content") if isinstance(message, dict) else None</code> | Обчислює та зберігає content ← message.get('content') if isinstance(message, dict) else None |
| 1048 | <code>usage_counts</code> | <code>                    names: List[str] = []</code> | Типізує names як List[str]; initial value [] |
| 1049 | <code>usage_counts</code> | <code>                    blocks = ([record] if kind == "tool_use" else</code> | Обчислює та зберігає blocks ← [record] if kind == 'tool_use' else content if kind == 'assistant' and isinstance(content, list) else [] |
| 1050 | <code>usage_counts</code> | <code>                              content if kind == "assistant" and isinstance(content, list) else [])</code> | Продовження інструкції 1049: Обчислює та зберігає blocks ← [record] if kind == 'tool_use' else content if kind == 'assistant' and isinstance(content, list) else [] |
| 1051 | <code>usage_counts</code> | <code>                    for block in blocks:</code> | Ітерує blocks і зв’язує кожен елемент із block |
| 1052 | <code>usage_counts</code> | <code>                        if not isinstance(block, dict) or block.get("type") != "tool_use":</code> | Умовна гілка: not isinstance(block, dict) or block.get('type') != 'tool_use'; відповідний block виконується тільки коли умова true. |
| 1053 | <code>usage_counts</code> | <code>                            continue</code> | Пропускає решту цієї ітерації; переходить до наступного елемента. |
| 1054 | <code>usage_counts</code> | <code>                        data = block.get("input")</code> | Обчислює та зберігає data ← block.get('input') |
| 1055 | <code>usage_counts</code> | <code>                        if block.get("name") == "Skill" and isinstance(data, dict):</code> | Умовна гілка: block.get('name') == 'Skill' and isinstance(data, dict); відповідний block виконується тільки коли умова true. |
| 1056 | <code>usage_counts</code> | <code>                            name = data.get("skill")</code> | Обчислює та зберігає name ← data.get('skill') |
| 1057 | <code>usage_counts</code> | <code>                            if isinstance(name, str) and name.strip():</code> | Умовна гілка: isinstance(name, str) and name.strip(); відповідний block виконується тільки коли умова true. |
| 1058 | <code>usage_counts</code> | <code>                                names.append(name)</code> | Виконує виклик names.append: names.append(name) |
| 1059 | <code>usage_counts</code> | <code>                    if kind == "user":</code> | Умовна гілка: kind == 'user'; відповідний block виконується тільки коли умова true. |
| 1060 | <code>usage_counts</code> | <code>                        text_parts = ([content] if isinstance(content, str) else</code> | Обчислює та зберігає text_parts ← [content] if isinstance(content, str) else [b.get('text', '') for b in content if isinstance(b, dict) and b.get('type') == 'text'] if isinstance(content, list) else [] |
| 1061 | <code>usage_counts</code> | <code>                                      [b.get("text", "") for b in content</code> | Продовження інструкції 1060: Обчислює та зберігає text_parts ← [content] if isinstance(content, str) else [b.get('text', '') for b in content if isinstance(b, dict) and b.get('type') == 'text'] if isinstance(content, list) else [] |
| 1062 | <code>usage_counts</code> | <code>                                       if isinstance(b, dict) and b.get("type") == "text"]</code> | Продовження інструкції 1060: Обчислює та зберігає text_parts ← [content] if isinstance(content, str) else [b.get('text', '') for b in content if isinstance(b, dict) and b.get('type') == 'text'] if isinstance(content, list) else [] |
| 1063 | <code>usage_counts</code> | <code>                                      if isinstance(content, list) else [])</code> | Продовження інструкції 1060: Обчислює та зберігає text_parts ← [content] if isinstance(content, str) else [b.get('text', '') for b in content if isinstance(b, dict) and b.get('type') == 'text'] if isinstance(content, list) else [] |
| 1064 | <code>usage_counts</code> | <code>                        for part in text_parts:</code> | Ітерує text_parts і зв’язує кожен елемент із part |
| 1065 | <code>usage_counts</code> | <code>                            if isinstance(part, str):</code> | Умовна гілка: isinstance(part, str); відповідний block виконується тільки коли умова true. |
| 1066 | <code>usage_counts</code> | <code>                                names.extend(_TYPED_COMMAND_RE.findall(part))</code> | Виконує виклик names.extend: names.extend(_TYPED_COMMAND_RE.findall(part)) |
| 1067 | <code>usage_counts</code> | <code>                    for name in names:</code> | Ітерує names і зв’язує кожен елемент із name |
| 1068 | <code>usage_counts</code> | <code>                        counts[name] = counts.get(name, 0) + 1</code> | Обчислює та зберігає counts[name] ← counts.get(name, 0) + 1 |
| 1069 | <code>usage_counts</code> | <code>        except OSError:</code> | Handler для зазначеного типу винятку; operational finding/fallback залежить від body нижче. |
| 1070 | <code>usage_counts</code> | <code>            continue</code> | Пропускає решту цієї ітерації; переходить до наступного елемента. |
| 1071 | <code>usage_counts</code> | <code>    return counts</code> | Завершує поточну функцію та повертає counts |
| 1072 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1073 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1074 | <code>resolve_usage</code> | <code>def resolve_usage(</code> | Оголошення функції `resolve_usage` та її аргументів; детальний контракт розібраний вище. |
| 1075 | <code>resolve_usage</code> | <code>    skill: Skill, counts: Dict[str, int], skills: Optional[Sequence[Skill]] = None,</code> | Оголошення функції `resolve_usage` та її аргументів; детальний контракт розібраний вище. |
| 1076 | <code>resolve_usage</code> | <code>) -&gt; int:</code> | Оголошення функції `resolve_usage` та її аргументів; детальний контракт розібраний вище. |
| 1077 | <code>resolve_usage</code> | <code>    if skill.command in counts:</code> | Умовна гілка: skill.command in counts; відповідний block виконується тільки коли умова true. |
| 1078 | <code>resolve_usage</code> | <code>        return counts[skill.command]</code> | Завершує поточну функцію та повертає counts[skill.command] |
| 1079 | <code>resolve_usage</code> | <code>    leaf = skill.command.rsplit(":", 1)[-1]</code> | Обчислює та зберігає leaf ← skill.command.rsplit(':', 1)[-1] |
| 1080 | <code>resolve_usage</code> | <code>    if leaf not in counts:</code> | Умовна гілка: leaf not in counts; відповідний block виконується тільки коли умова true. |
| 1081 | <code>resolve_usage</code> | <code>        return 0</code> | Завершує поточну функцію та повертає 0 |
| 1082 | <code>resolve_usage</code> | <code>    if skills is not None:</code> | Умовна гілка: skills is not None; відповідний block виконується тільки коли умова true. |
| 1083 | <code>resolve_usage</code> | <code>        owners = {s.command for s in skills if s.command.rsplit(":", 1)[-1] == leaf}</code> | Обчислює та зберігає owners ← {s.command for s in skills if s.command.rsplit(':', 1)[-1] == leaf} |
| 1084 | <code>resolve_usage</code> | <code>        if owners != {skill.command}:</code> | Умовна гілка: owners != {skill.command}; відповідний block виконується тільки коли умова true. |
| 1085 | <code>resolve_usage</code> | <code>            # A local or legacy bare name does not identify one of several</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 1086 | <code>resolve_usage</code> | <code>            # namespaced entries. Preserve exact evidence instead of guessing.</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 1087 | <code>resolve_usage</code> | <code>            return 0</code> | Завершує поточну функцію та повертає 0 |
| 1088 | <code>resolve_usage</code> | <code>    return counts.get(leaf, 0)</code> | Завершує поточну функцію та повертає counts.get(leaf, 0) |
| 1089 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1090 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1091 | <code>&lt;module&gt;</code> | <code># --- Findings -------------------------------------------------------------</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 1092 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1093 | <code>&lt;module&gt;</code> | <code>SEVERITIES = {"error": 0, "warn": 1, "info": 2}</code> | Обчислює та зберігає SEVERITIES ← {'error': 0, 'warn': 1, 'info': 2} |
| 1094 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1095 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1096 | <code>Finding</code> | <code>@dataclass</code> | Decorator змінює створення class/function (dataclass або property). |
| 1097 | <code>Finding</code> | <code>class Finding:</code> | Оголошення класу `Finding` та базових класів; модель даних/поведінка розібрана вище. |
| 1098 | <code>Finding</code> | <code>    rule: str</code> | Типізує rule як str |
| 1099 | <code>Finding</code> | <code>    severity: str</code> | Типізує severity як str |
| 1100 | <code>Finding</code> | <code>    command: str</code> | Типізує command як str |
| 1101 | <code>Finding</code> | <code>    path: str</code> | Типізує path як str |
| 1102 | <code>Finding</code> | <code>    message: str</code> | Типізує message як str |
| 1103 | <code>Finding</code> | <code>    fix: str</code> | Типізує fix як str |
| 1104 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1105 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1106 | <code>estimate_tokens</code> | <code>def estimate_tokens(text: str, chars_per_token: float = DEFAULT_CHARS_PER_TOKEN) -&gt; int:</code> | Оголошення функції `estimate_tokens` та її аргументів; детальний контракт розібраний вище. |
| 1107 | <code>estimate_tokens</code> | <code>    """Character-ratio token estimate.</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1108 | <code>estimate_tokens</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1109 | <code>estimate_tokens</code> | <code>    No tokenizer dependency. Useful for ranking listings, not</code> | Продовження інструкції 1107: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1110 | <code>estimate_tokens</code> | <code>    exact. Pass --chars-per-token to recalibrate, or feed --json into a real</code> | Продовження інструкції 1107: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1111 | <code>estimate_tokens</code> | <code>    tokenizer when you need precise numbers.</code> | Продовження інструкції 1107: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1112 | <code>estimate_tokens</code> | <code>    """</code> | Продовження інструкції 1107: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1113 | <code>estimate_tokens</code> | <code>    if not text:</code> | Умовна гілка: not text; відповідний block виконується тільки коли умова true. |
| 1114 | <code>estimate_tokens</code> | <code>        return 0</code> | Завершує поточну функцію та повертає 0 |
| 1115 | <code>estimate_tokens</code> | <code>    return max(1, int(round(len(text) / chars_per_token)))</code> | Завершує поточну функцію та повертає max(1, int(round(len(text) / chars_per_token))) |
| 1116 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1117 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1118 | <code>_content_words</code> | <code>def _content_words(text: str) -&gt; Set[str]:</code> | Оголошення функції `_content_words` та її аргументів; детальний контракт розібраний вище. |
| 1119 | <code>_content_words</code> | <code>    words = re.findall(r"[^\W_]+", text.casefold())</code> | Обчислює та зберігає words ← re.findall('[^\\W_]+', text.casefold()) |
| 1120 | <code>_content_words</code> | <code>    return {w for w in words if len(w) &gt; 2 and w not in STOPWORDS}</code> | Завершує поточну функцію та повертає {w for w in words if len(w) &gt; 2 and w not in STOPWORDS} |
| 1121 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1122 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1123 | <code>_jaccard</code> | <code>def _jaccard(left: Set[str], right: Set[str]) -&gt; float:</code> | Оголошення функції `_jaccard` та її аргументів; детальний контракт розібраний вище. |
| 1124 | <code>_jaccard</code> | <code>    if not left or not right:</code> | Умовна гілка: not left or not right; відповідний block виконується тільки коли умова true. |
| 1125 | <code>_jaccard</code> | <code>        return 0.0</code> | Завершує поточну функцію та повертає 0.0 |
| 1126 | <code>_jaccard</code> | <code>    union = len(left &#124; right)</code> | Обчислює та зберігає union ← len(left &#124; right) |
| 1127 | <code>_jaccard</code> | <code>    return len(left &amp; right) / union if union else 0.0</code> | Завершує поточну функцію та повертає len(left &amp; right) / union if union else 0.0 |
| 1128 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1129 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1130 | <code>&lt;module&gt;</code> | <code>_SYMLINK_STUB_RE = re.compile(r"^[.\w/\\-]{1,300}\.(md&#124;markdown)$")</code> | Обчислює та зберігає _SYMLINK_STUB_RE ← re.compile('^[.\\w/\\\\-]{1,300}\\.(md&#124;markdown)$') |
| 1131 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1132 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1133 | <code>_looks_like_symlink_stub</code> | <code>def _looks_like_symlink_stub(body: str) -&gt; bool:</code> | Оголошення функції `_looks_like_symlink_stub` та її аргументів; детальний контракт розібраний вище. |
| 1134 | <code>_looks_like_symlink_stub</code> | <code>    """A git symlink checked out as a plain file: one line holding a path."""</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1135 | <code>_looks_like_symlink_stub</code> | <code>    stripped = body.strip()</code> | Обчислює та зберігає stripped ← body.strip() |
| 1136 | <code>_looks_like_symlink_stub</code> | <code>    return bool(stripped) and "\n" not in stripped and bool(_SYMLINK_STUB_RE.match(stripped))</code> | Завершує поточну функцію та повертає bool(stripped) and '\n' not in stripped and bool(_SYMLINK_STUB_RE.match(stripped)) |
| 1137 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1138 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1139 | <code>cluster_by_description</code> | <code>def cluster_by_description(</code> | Оголошення функції `cluster_by_description` та її аргументів; детальний контракт розібраний вище. |
| 1140 | <code>cluster_by_description</code> | <code>    skills: Sequence[Skill], similarity: float = DEFAULT_SIMILARITY</code> | Оголошення функції `cluster_by_description` та її аргументів; детальний контракт розібраний вище. |
| 1141 | <code>cluster_by_description</code> | <code>) -&gt; List[List[Skill]]:</code> | Оголошення функції `cluster_by_description` та її аргументів; детальний контракт розібраний вище. |
| 1142 | <code>cluster_by_description</code> | <code>    """Group skills whose descriptions overlap past `similarity`.</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1143 | <code>cluster_by_description</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1144 | <code>cluster_by_description</code> | <code>    Exact word bags are grouped first, including large duplicate collections.</code> | Продовження інструкції 1142: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1145 | <code>cluster_by_description</code> | <code>    Approximate pairs use an index of discriminative words to bound the work;</code> | Продовження інструкції 1142: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1146 | <code>cluster_by_description</code> | <code>    descriptions made entirely of collection-wide common words can still hide</code> | Продовження інструкції 1142: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1147 | <code>cluster_by_description</code> | <code>    approximate matches. This is a word-overlap heuristic, not a routing eval.</code> | Продовження інструкції 1142: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1148 | <code>cluster_by_description</code> | <code>    """</code> | Продовження інструкції 1142: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1149 | <code>cluster_by_description</code> | <code>    words = [_content_words(s.description) for s in skills]</code> | Обчислює та зберігає words ← [_content_words(s.description) for s in skills] |
| 1150 | <code>cluster_by_description</code> | <code>    total = len(skills)</code> | Обчислює та зберігає total ← len(skills) |
| 1151 | <code>cluster_by_description</code> | <code>    if total &lt; 2:</code> | Умовна гілка: total &lt; 2; відповідний block виконується тільки коли умова true. |
| 1152 | <code>cluster_by_description</code> | <code>        return []</code> | Завершує поточну функцію та повертає [] |
| 1153 | <code>cluster_by_description</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1154 | <code>cluster_by_description</code> | <code>    index: Dict[str, List[int]] = {}</code> | Типізує index як Dict[str, List[int]]; initial value {} |
| 1155 | <code>cluster_by_description</code> | <code>    for i, bag in enumerate(words):</code> | Ітерує enumerate(words) і зв’язує кожен елемент із (i, bag) |
| 1156 | <code>cluster_by_description</code> | <code>        for word in bag:</code> | Ітерує bag і зв’язує кожен елемент із word |
| 1157 | <code>cluster_by_description</code> | <code>            index.setdefault(word, []).append(i)</code> | Виконує виклик index.setdefault(word, []).append: index.setdefault(word, []).append(i) |
| 1158 | <code>cluster_by_description</code> | <code>    # Skip words so common they carry no signal, but never below a floor:</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 1159 | <code>cluster_by_description</code> | <code>    # in a small library every word is "common" and the filter would hide</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 1160 | <code>cluster_by_description</code> | <code>    # the very duplicates it exists to find.</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 1161 | <code>cluster_by_description</code> | <code>    max_doc_freq = max(50, int(total * 0.05))</code> | Обчислює та зберігає max_doc_freq ← max(50, int(total * 0.05)) |
| 1162 | <code>cluster_by_description</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1163 | <code>cluster_by_description</code> | <code>    parent = list(range(total))</code> | Обчислює та зберігає parent ← list(range(total)) |
| 1164 | <code>cluster_by_description</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1165 | <code>cluster_by_description.find</code> | <code>    def find(i: int) -&gt; int:</code> | Оголошення функції `find` та її аргументів; детальний контракт розібраний вище. |
| 1166 | <code>cluster_by_description.find</code> | <code>        while parent[i] != i:</code> | Продовжує цикл поки parent[i] != i |
| 1167 | <code>cluster_by_description.find</code> | <code>            parent[i] = parent[parent[i]]</code> | Обчислює та зберігає parent[i] ← parent[parent[i]] |
| 1168 | <code>cluster_by_description.find</code> | <code>            i = parent[i]</code> | Обчислює та зберігає i ← parent[i] |
| 1169 | <code>cluster_by_description.find</code> | <code>        return i</code> | Завершує поточну функцію та повертає i |
| 1170 | <code>cluster_by_description</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1171 | <code>cluster_by_description.union</code> | <code>    def union(i: int, j: int) -&gt; None:</code> | Оголошення функції `union` та її аргументів; детальний контракт розібраний вище. |
| 1172 | <code>cluster_by_description.union</code> | <code>        root_i, root_j = find(i), find(j)</code> | Обчислює та зберігає (root_i, root_j) ← (find(i), find(j)) |
| 1173 | <code>cluster_by_description.union</code> | <code>        if root_i != root_j:</code> | Умовна гілка: root_i != root_j; відповідний block виконується тільки коли умова true. |
| 1174 | <code>cluster_by_description.union</code> | <code>            parent[max(root_i, root_j)] = min(root_i, root_j)</code> | Обчислює та зберігає parent[max(root_i, root_j)] ← min(root_i, root_j) |
| 1175 | <code>cluster_by_description</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1176 | <code>cluster_by_description</code> | <code>    exact: Dict[frozenset, int] = {}</code> | Типізує exact як Dict[frozenset, int]; initial value {} |
| 1177 | <code>cluster_by_description</code> | <code>    for i, bag in enumerate(words):</code> | Ітерує enumerate(words) і зв’язує кожен елемент із (i, bag) |
| 1178 | <code>cluster_by_description</code> | <code>        if not bag:</code> | Умовна гілка: not bag; відповідний block виконується тільки коли умова true. |
| 1179 | <code>cluster_by_description</code> | <code>            continue</code> | Пропускає решту цієї ітерації; переходить до наступного елемента. |
| 1180 | <code>cluster_by_description</code> | <code>        key = frozenset(bag)</code> | Обчислює та зберігає key ← frozenset(bag) |
| 1181 | <code>cluster_by_description</code> | <code>        if key in exact:</code> | Умовна гілка: key in exact; відповідний block виконується тільки коли умова true. |
| 1182 | <code>cluster_by_description</code> | <code>            union(exact[key], i)</code> | Виконує виклик union: union(exact[key], i) |
| 1183 | <code>cluster_by_description</code> | <code>        else:</code> | Alternative branch для попередньої умови або завершення циклу без break. |
| 1184 | <code>cluster_by_description</code> | <code>            exact[key] = i</code> | Обчислює та зберігає exact[key] ← i |
| 1185 | <code>cluster_by_description</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1186 | <code>cluster_by_description</code> | <code>    for i, bag in enumerate(words):</code> | Ітерує enumerate(words) і зв’язує кожен елемент із (i, bag) |
| 1187 | <code>cluster_by_description</code> | <code>        candidates: Set[int] = set()</code> | Типізує candidates як Set[int]; initial value set() |
| 1188 | <code>cluster_by_description</code> | <code>        for word in bag:</code> | Ітерує bag і зв’язує кожен елемент із word |
| 1189 | <code>cluster_by_description</code> | <code>            bucket = index.get(word, ())</code> | Обчислює та зберігає bucket ← index.get(word, ()) |
| 1190 | <code>cluster_by_description</code> | <code>            if len(bucket) &gt; max_doc_freq:</code> | Умовна гілка: len(bucket) &gt; max_doc_freq; відповідний block виконується тільки коли умова true. |
| 1191 | <code>cluster_by_description</code> | <code>                continue</code> | Пропускає решту цієї ітерації; переходить до наступного елемента. |
| 1192 | <code>cluster_by_description</code> | <code>            candidates.update(j for j in bucket if j &gt; i)</code> | Виконує виклик candidates.update: candidates.update((j for j in bucket if j &gt; i)) |
| 1193 | <code>cluster_by_description</code> | <code>        for j in candidates:</code> | Ітерує candidates і зв’язує кожен елемент із j |
| 1194 | <code>cluster_by_description</code> | <code>            if find(i) != find(j) and _jaccard(bag, words[j]) &gt;= similarity:</code> | Умовна гілка: find(i) != find(j) and _jaccard(bag, words[j]) &gt;= similarity; відповідний block виконується тільки коли умова true. |
| 1195 | <code>cluster_by_description</code> | <code>                union(i, j)</code> | Виконує виклик union: union(i, j) |
| 1196 | <code>cluster_by_description</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1197 | <code>cluster_by_description</code> | <code>    groups: Dict[int, List[Skill]] = {}</code> | Типізує groups як Dict[int, List[Skill]]; initial value {} |
| 1198 | <code>cluster_by_description</code> | <code>    for i, skill in enumerate(skills):</code> | Ітерує enumerate(skills) і зв’язує кожен елемент із (i, skill) |
| 1199 | <code>cluster_by_description</code> | <code>        groups.setdefault(find(i), []).append(skill)</code> | Виконує виклик groups.setdefault(find(i), []).append: groups.setdefault(find(i), []).append(skill) |
| 1200 | <code>cluster_by_description</code> | <code>    return [sorted(g, key=lambda s: s.command) for g in groups.values() if len(g) &gt; 1]</code> | Завершує поточну функцію та повертає [sorted(g, key=lambda s: s.command) for g in groups.values() if len(g) &gt; 1] |
| 1201 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1202 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1203 | <code>_truthy</code> | <code>def _truthy(value: str) -&gt; Optional[bool]:</code> | Оголошення функції `_truthy` та її аргументів; детальний контракт розібраний вище. |
| 1204 | <code>_truthy</code> | <code>    if getattr(value, "kind", "string") in ("sequence", "mapping"):</code> | Умовна гілка: getattr(value, 'kind', 'string') in ('sequence', 'mapping'); відповідний block виконується тільки коли умова true. |
| 1205 | <code>_truthy</code> | <code>        return None</code> | Завершує поточну функцію та повертає None |
| 1206 | <code>_truthy</code> | <code>    token = value.strip().strip("\"'").lower()</code> | Обчислює та зберігає token ← value.strip().strip('"\'').lower() |
| 1207 | <code>_truthy</code> | <code>    if token in TRUE_WORDS:</code> | Умовна гілка: token in TRUE_WORDS; відповідний block виконується тільки коли умова true. |
| 1208 | <code>_truthy</code> | <code>        return True</code> | Завершує поточну функцію та повертає True |
| 1209 | <code>_truthy</code> | <code>    if token in FALSE_WORDS:</code> | Умовна гілка: token in FALSE_WORDS; відповідний block виконується тільки коли умова true. |
| 1210 | <code>_truthy</code> | <code>        return False</code> | Завершує поточну функцію та повертає False |
| 1211 | <code>_truthy</code> | <code>    return None</code> | Завершує поточну функцію та повертає None |
| 1212 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1213 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1214 | <code>analyze</code> | <code>def analyze(</code> | Оголошення функції `analyze` та її аргументів; детальний контракт розібраний вище. |
| 1215 | <code>analyze</code> | <code>    skills: Sequence[Skill],</code> | Оголошення функції `analyze` та її аргументів; детальний контракт розібраний вище. |
| 1216 | <code>analyze</code> | <code>    usage: Optional[Dict[str, int]] = None,</code> | Оголошення функції `analyze` та її аргументів; детальний контракт розібраний вище. |
| 1217 | <code>analyze</code> | <code>    portable: bool = False,</code> | Оголошення функції `analyze` та її аргументів; детальний контракт розібраний вище. |
| 1218 | <code>analyze</code> | <code>    body_line_budget: int = DEFAULT_BODY_LINE_BUDGET,</code> | Оголошення функції `analyze` та її аргументів; детальний контракт розібраний вище. |
| 1219 | <code>analyze</code> | <code>    similarity: float = DEFAULT_SIMILARITY,</code> | Оголошення функції `analyze` та її аргументів; детальний контракт розібраний вище. |
| 1220 | <code>analyze</code> | <code>    listing_budget: Optional[int] = None,</code> | Оголошення функції `analyze` та її аргументів; детальний контракт розібраний вище. |
| 1221 | <code>analyze</code> | <code>    chars_per_token: float = DEFAULT_CHARS_PER_TOKEN,</code> | Оголошення функції `analyze` та її аргументів; детальний контракт розібраний вище. |
| 1222 | <code>analyze</code> | <code>) -&gt; List[Finding]:</code> | Оголошення функції `analyze` та її аргументів; детальний контракт розібраний вище. |
| 1223 | <code>analyze</code> | <code>    findings: List[Finding] = []</code> | Типізує findings як List[Finding]; initial value [] |
| 1224 | <code>analyze</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1225 | <code>analyze.add</code> | <code>    def add(rule: str, severity: str, skill: Skill, message: str, fix: str) -&gt; None:</code> | Оголошення функції `add` та її аргументів; детальний контракт розібраний вище. |
| 1226 | <code>analyze.add</code> | <code>        findings.append(Finding(rule, severity, skill.command, str(skill.path), message, fix))</code> | Виконує виклик findings.append: findings.append(Finding(rule, severity, skill.command, str(skill.path), message, fix)) |
| 1227 | <code>analyze</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1228 | <code>analyze</code> | <code>    for skill in skills:</code> | Ітерує skills і зв’язує кожен елемент із skill |
| 1229 | <code>analyze</code> | <code>        fm = skill.frontmatter</code> | Обчислює та зберігає fm ← skill.frontmatter |
| 1230 | <code>analyze</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1231 | <code>analyze</code> | <code>        if any(p.startswith("unreadable") for p in skill.problems):</code> | Умовна гілка: any((p.startswith('unreadable') for p in skill.problems)); відповідний block виконується тільки коли умова true. |
| 1232 | <code>analyze</code> | <code>            add("SR007", "error", skill, "; ".join(skill.problems),</code> | Додає source-linked Finding правила 'SR007': add('SR007', 'error', skill, '; '.join(skill.problems), 'Check file permissions and encoding.') |
| 1233 | <code>analyze</code> | <code>                "Check file permissions and encoding.")</code> | Продовження інструкції 1232: Додає source-linked Finding правила 'SR007': add('SR007', 'error', skill, '; '.join(skill.problems), 'Check file permissions and encoding.') |
| 1234 | <code>analyze</code> | <code>            continue</code> | Пропускає решту цієї ітерації; переходить до наступного елемента. |
| 1235 | <code>analyze</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1236 | <code>analyze</code> | <code>        if "frontmatter-not-first-line" in skill.problems:</code> | Умовна гілка: 'frontmatter-not-first-line' in skill.problems; відповідний block виконується тільки коли умова true. |
| 1237 | <code>analyze</code> | <code>            add("SR001", "error", skill,</code> | Додає source-linked Finding правила 'SR001': add('SR001', 'error', skill, 'Frontmatter does not start on line 1, so the whole file is read as body and these metadata fields do not apply.', 'Move the opening `---` to the very first line, with no… |
| 1238 | <code>analyze</code> | <code>                "Frontmatter does not start on line 1, so the whole file is read as body "</code> | Продовження інструкції 1237: Додає source-linked Finding правила 'SR001': add('SR001', 'error', skill, 'Frontmatter does not start on line 1, so the whole file is read as body and these metadata fields do not apply.', 'Move the opening `---` to the very first line, with no… |
| 1239 | <code>analyze</code> | <code>                "and these metadata fields do not apply.",</code> | Продовження інструкції 1237: Додає source-linked Finding правила 'SR001': add('SR001', 'error', skill, 'Frontmatter does not start on line 1, so the whole file is read as body and these metadata fields do not apply.', 'Move the opening `---` to the very first line, with no… |
| 1240 | <code>analyze</code> | <code>                "Move the opening `---` to the very first line, with nothing above it.")</code> | Продовження інструкції 1237: Додає source-linked Finding правила 'SR001': add('SR001', 'error', skill, 'Frontmatter does not start on line 1, so the whole file is read as body and these metadata fields do not apply.', 'Move the opening `---` to the very first line, with no… |
| 1241 | <code>analyze</code> | <code>        elif "no-frontmatter" in skill.problems:</code> | Наступна умовна гілка, коли попередній if/elif не виконався. |
| 1242 | <code>analyze</code> | <code>            if _looks_like_symlink_stub(skill.body):</code> | Умовна гілка: _looks_like_symlink_stub(skill.body); відповідний block виконується тільки коли умова true. |
| 1243 | <code>analyze</code> | <code>                add("SR008", "error", skill,</code> | Додає source-linked Finding правила 'SR008': add('SR008', 'error', skill, 'File contains a bare path, not a skill: a git symlink that was checked out as a plain file (usual on Windows without symlink support).', 'Re-clone with symlinks enabled,… |
| 1244 | <code>analyze</code> | <code>                    "File contains a bare path, not a skill: a git symlink that was "</code> | Продовження інструкції 1243: Додає source-linked Finding правила 'SR008': add('SR008', 'error', skill, 'File contains a bare path, not a skill: a git symlink that was checked out as a plain file (usual on Windows without symlink support).', 'Re-clone with symlinks enabled,… |
| 1245 | <code>analyze</code> | <code>                    "checked out as a plain file (usual on Windows without symlink support).",</code> | Продовження інструкції 1243: Додає source-linked Finding правила 'SR008': add('SR008', 'error', skill, 'File contains a bare path, not a skill: a git symlink that was checked out as a plain file (usual on Windows without symlink support).', 'Re-clone with symlinks enabled,… |
| 1246 | <code>analyze</code> | <code>                    "Re-clone with symlinks enabled, or replace the stub with the real file.")</code> | Продовження інструкції 1243: Додає source-linked Finding правила 'SR008': add('SR008', 'error', skill, 'File contains a bare path, not a skill: a git symlink that was checked out as a plain file (usual on Windows without symlink support).', 'Re-clone with symlinks enabled,… |
| 1247 | <code>analyze</code> | <code>            else:</code> | Alternative branch для попередньої умови або завершення циклу без break. |
| 1248 | <code>analyze</code> | <code>                add("SR001", "error", skill,</code> | Додає source-linked Finding правила 'SR001': add('SR001', 'error', skill, 'No YAML frontmatter block.', 'Add a `---` delimited block with at least `description`.') |
| 1249 | <code>analyze</code> | <code>                    "No YAML frontmatter block.",</code> | Продовження інструкції 1248: Додає source-linked Finding правила 'SR001': add('SR001', 'error', skill, 'No YAML frontmatter block.', 'Add a `---` delimited block with at least `description`.') |
| 1250 | <code>analyze</code> | <code>                    "Add a `---` delimited block with at least `description`.")</code> | Продовження інструкції 1248: Додає source-linked Finding правила 'SR001': add('SR001', 'error', skill, 'No YAML frontmatter block.', 'Add a `---` delimited block with at least `description`.') |
| 1251 | <code>analyze</code> | <code>        if "unterminated-frontmatter" in skill.problems:</code> | Умовна гілка: 'unterminated-frontmatter' in skill.problems; відповідний block виконується тільки коли умова true. |
| 1252 | <code>analyze</code> | <code>            add("SR006", "error", skill,</code> | Додає source-linked Finding правила 'SR006': add('SR006', 'error', skill, 'Frontmatter opens but never closes.', 'Add the closing `---` line.') |
| 1253 | <code>analyze</code> | <code>                "Frontmatter opens but never closes.",</code> | Продовження інструкції 1252: Додає source-linked Finding правила 'SR006': add('SR006', 'error', skill, 'Frontmatter opens but never closes.', 'Add the closing `---` line.') |
| 1254 | <code>analyze</code> | <code>                "Add the closing `---` line.")</code> | Продовження інструкції 1252: Додає source-linked Finding правила 'SR006': add('SR006', 'error', skill, 'Frontmatter opens but never closes.', 'Add the closing `---` line.') |
| 1255 | <code>analyze</code> | <code>        for problem in skill.problems:</code> | Ітерує skill.problems і зв’язує кожен елемент із problem |
| 1256 | <code>analyze</code> | <code>            if problem.startswith("invalid-frontmatter:"):</code> | Умовна гілка: problem.startswith('invalid-frontmatter:'); відповідний block виконується тільки коли умова true. |
| 1257 | <code>analyze</code> | <code>                add("SR009", "error", skill,</code> | Додає source-linked Finding правила 'SR009': add('SR009', 'error', skill, 'Cannot validate frontmatter with the supported YAML subset: ' + problem.split(':', 1)[1].strip(), 'Correct invalid YAML or use scalar fields, flat lists and a shallow me… |
| 1258 | <code>analyze</code> | <code>                    "Cannot validate frontmatter with the supported YAML subset: " + problem.split(":", 1)[1].strip(),</code> | Продовження інструкції 1257: Додає source-linked Finding правила 'SR009': add('SR009', 'error', skill, 'Cannot validate frontmatter with the supported YAML subset: ' + problem.split(':', 1)[1].strip(), 'Correct invalid YAML or use scalar fields, flat lists and a shallow me… |
| 1259 | <code>analyze</code> | <code>                    "Correct invalid YAML or use scalar fields, flat lists and a shallow metadata map; "</code> | Продовження інструкції 1257: Додає source-linked Finding правила 'SR009': add('SR009', 'error', skill, 'Cannot validate frontmatter with the supported YAML subset: ' + problem.split(':', 1)[1].strip(), 'Correct invalid YAML or use scalar fields, flat lists and a shallow me… |
| 1260 | <code>analyze</code> | <code>                    "validate more complex YAML with a full YAML validator.")</code> | Продовження інструкції 1257: Додає source-linked Finding правила 'SR009': add('SR009', 'error', skill, 'Cannot validate frontmatter with the supported YAML subset: ' + problem.split(':', 1)[1].strip(), 'Correct invalid YAML or use scalar fields, flat lists and a shallow me… |
| 1261 | <code>analyze</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1262 | <code>analyze</code> | <code>        description = skill.description</code> | Обчислює та зберігає description ← skill.description |
| 1263 | <code>analyze</code> | <code>        combined = " ".join(p for p in (description, skill.when_to_use) if p)</code> | Обчислює та зберігає combined ← ' '.join((p for p in (description, skill.when_to_use) if p)) |
| 1264 | <code>analyze</code> | <code>        # Command files are the older format: no description and no frontmatter</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 1265 | <code>analyze</code> | <code>        # are normal for them, and the Agent Skills spec does not cover them, so</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 1266 | <code>analyze</code> | <code>        # the skill-authoring rules below skip them.</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 1267 | <code>analyze</code> | <code>        authoring = skill.kind == "skill"</code> | Обчислює та зберігає authoring ← skill.kind == 'skill' |
| 1268 | <code>analyze</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1269 | <code>analyze</code> | <code>        if authoring and not description:</code> | Умовна гілка: authoring and (not description); відповідний block виконується тільки коли умова true. |
| 1270 | <code>analyze</code> | <code>            add("SR002", "error" if portable else "warn", skill,</code> | Додає source-linked Finding правила 'SR002': add('SR002', 'error' if portable else 'warn', skill, 'No non-empty `description`. ' + ('The Agent Skills spec requires it.' if portable else 'Claude Code falls back to the first non-empty line of the… |
| 1271 | <code>analyze</code> | <code>                "No non-empty `description`. " + (</code> | Продовження інструкції 1270: Додає source-linked Finding правила 'SR002': add('SR002', 'error' if portable else 'warn', skill, 'No non-empty `description`. ' + ('The Agent Skills spec requires it.' if portable else 'Claude Code falls back to the first non-empty line of the… |
| 1272 | <code>analyze</code> | <code>                    "The Agent Skills spec requires it." if portable else</code> | Продовження інструкції 1270: Додає source-linked Finding правила 'SR002': add('SR002', 'error' if portable else 'warn', skill, 'No non-empty `description`. ' + ('The Agent Skills spec requires it.' if portable else 'Claude Code falls back to the first non-empty line of the… |
| 1273 | <code>analyze</code> | <code>                    "Claude Code falls back to the first non-empty line of the body."),</code> | Продовження інструкції 1270: Додає source-linked Finding правила 'SR002': add('SR002', 'error' if portable else 'warn', skill, 'No non-empty `description`. ' + ('The Agent Skills spec requires it.' if portable else 'Claude Code falls back to the first non-empty line of the… |
| 1274 | <code>analyze</code> | <code>                "Add a description that says what the skill does and when to use it.")</code> | Продовження інструкції 1270: Додає source-linked Finding правила 'SR002': add('SR002', 'error' if portable else 'warn', skill, 'No non-empty `description`. ' + ('The Agent Skills spec requires it.' if portable else 'Claude Code falls back to the first non-empty line of the… |
| 1275 | <code>analyze</code> | <code>        elif authoring and description and len(description) &lt; 15:</code> | Наступна умовна гілка, коли попередній if/elif не виконався. |
| 1276 | <code>analyze</code> | <code>            add("SR025", "warn", skill,</code> | Додає source-linked Finding правила 'SR025': add('SR025', 'warn', skill, 'Description is {} characters. Too thin to route on.'.format(len(description)), 'Say what it does and name the trigger, in one sentence.') |
| 1277 | <code>analyze</code> | <code>                "Description is {} characters. Too thin to route on.".format(len(description)),</code> | Продовження інструкції 1276: Додає source-linked Finding правила 'SR025': add('SR025', 'warn', skill, 'Description is {} characters. Too thin to route on.'.format(len(description)), 'Say what it does and name the trigger, in one sentence.') |
| 1278 | <code>analyze</code> | <code>                "Say what it does and name the trigger, in one sentence.")</code> | Продовження інструкції 1276: Додає source-linked Finding правила 'SR025': add('SR025', 'warn', skill, 'Description is {} characters. Too thin to route on.'.format(len(description)), 'Say what it does and name the trigger, in one sentence.') |
| 1279 | <code>analyze</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1280 | <code>analyze</code> | <code>        if len(combined) &gt; LISTING_CHAR_CAP:</code> | Умовна гілка: len(combined) &gt; LISTING_CHAR_CAP; відповідний block виконується тільки коли умова true. |
| 1281 | <code>analyze</code> | <code>            add("SR003", "error", skill,</code> | Додає source-linked Finding правила 'SR003': add('SR003', 'error', skill, 'description + when_to_use is {} chars; the configured listing model caps it at {} characters.'.format(len(combined), LISTING_CHAR_CAP), 'Put the trigger first and move t… |
| 1282 | <code>analyze</code> | <code>                "description + when_to_use is {} chars; the configured listing model "</code> | Продовження інструкції 1281: Додає source-linked Finding правила 'SR003': add('SR003', 'error', skill, 'description + when_to_use is {} chars; the configured listing model caps it at {} characters.'.format(len(combined), LISTING_CHAR_CAP), 'Put the trigger first and move t… |
| 1283 | <code>analyze</code> | <code>                "caps it at {} characters.".format(</code> | Продовження інструкції 1281: Додає source-linked Finding правила 'SR003': add('SR003', 'error', skill, 'description + when_to_use is {} chars; the configured listing model caps it at {} characters.'.format(len(combined), LISTING_CHAR_CAP), 'Put the trigger first and move t… |
| 1284 | <code>analyze</code> | <code>                    len(combined), LISTING_CHAR_CAP),</code> | Продовження інструкції 1281: Додає source-linked Finding правила 'SR003': add('SR003', 'error', skill, 'description + when_to_use is {} chars; the configured listing model caps it at {} characters.'.format(len(combined), LISTING_CHAR_CAP), 'Put the trigger first and move t… |
| 1285 | <code>analyze</code> | <code>                "Put the trigger first and move the detail into the body.")</code> | Продовження інструкції 1281: Додає source-linked Finding правила 'SR003': add('SR003', 'error', skill, 'description + when_to_use is {} chars; the configured listing model caps it at {} characters.'.format(len(combined), LISTING_CHAR_CAP), 'Put the trigger first and move t… |
| 1286 | <code>analyze</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1287 | <code>analyze</code> | <code>        disabled_model = _truthy(fm.get("disable-model-invocation", "false"))</code> | Обчислює та зберігає disabled_model ← _truthy(fm.get('disable-model-invocation', 'false')) |
| 1288 | <code>analyze</code> | <code>        user_invocable = _truthy(fm.get("user-invocable", "true"))</code> | Обчислює та зберігає user_invocable ← _truthy(fm.get('user-invocable', 'true')) |
| 1289 | <code>analyze</code> | <code>        if disabled_model is True and user_invocable is False:</code> | Умовна гілка: disabled_model is True and user_invocable is False; відповідний block виконується тільки коли умова true. |
| 1290 | <code>analyze</code> | <code>            add("SR004", "error", skill,</code> | Додає source-linked Finding правила 'SR004': add('SR004', 'error', skill, '`disable-model-invocation: true` and `user-invocable: false`: direct /command invocation and automatic invocation are both disabled.', 'Enable the invocation route the s… |
| 1291 | <code>analyze</code> | <code>                "`disable-model-invocation: true` and `user-invocable: false`: direct "</code> | Продовження інструкції 1290: Додає source-linked Finding правила 'SR004': add('SR004', 'error', skill, '`disable-model-invocation: true` and `user-invocable: false`: direct /command invocation and automatic invocation are both disabled.', 'Enable the invocation route the s… |
| 1292 | <code>analyze</code> | <code>                "/command invocation and automatic invocation are both disabled.",</code> | Продовження інструкції 1290: Додає source-linked Finding правила 'SR004': add('SR004', 'error', skill, '`disable-model-invocation: true` and `user-invocable: false`: direct /command invocation and automatic invocation are both disabled.', 'Enable the invocation route the s… |
| 1293 | <code>analyze</code> | <code>                "Enable the invocation route the skill needs.")</code> | Продовження інструкції 1290: Додає source-linked Finding правила 'SR004': add('SR004', 'error', skill, '`disable-model-invocation: true` and `user-invocable: false`: direct /command invocation and automatic invocation are both disabled.', 'Enable the invocation route the s… |
| 1294 | <code>analyze</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1295 | <code>analyze</code> | <code>        for bool_field in BOOL_FIELDS:</code> | Ітерує BOOL_FIELDS і зв’язує кожен елемент із bool_field |
| 1296 | <code>analyze</code> | <code>            if bool_field in fm and _truthy(fm[bool_field]) is None:</code> | Умовна гілка: bool_field in fm and _truthy(fm[bool_field]) is None; відповідний block виконується тільки коли умова true. |
| 1297 | <code>analyze</code> | <code>                add("SR005", "warn", skill,</code> | Додає source-linked Finding правила 'SR005': add('SR005', 'warn', skill, '`{}: {}` is not a boolean.'.format(bool_field, fm[bool_field]), 'Use true/false (yes/no/on/off/1/0 also work).') |
| 1298 | <code>analyze</code> | <code>                    "`{}: {}` is not a boolean.".format(bool_field, fm[bool_field]),</code> | Продовження інструкції 1297: Додає source-linked Finding правила 'SR005': add('SR005', 'warn', skill, '`{}: {}` is not a boolean.'.format(bool_field, fm[bool_field]), 'Use true/false (yes/no/on/off/1/0 also work).') |
| 1299 | <code>analyze</code> | <code>                    "Use true/false (yes/no/on/off/1/0 also work).")</code> | Продовження інструкції 1297: Додає source-linked Finding правила 'SR005': add('SR005', 'warn', skill, '`{}: {}` is not a boolean.'.format(bool_field, fm[bool_field]), 'Use true/false (yes/no/on/off/1/0 also work).') |
| 1300 | <code>analyze</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1301 | <code>analyze</code> | <code>        if authoring and description and not any(cue in combined.lower() for cue in TRIGGER_CUES):</code> | Умовна гілка: authoring and description and (not any((cue in combined.lower() for cue in TRIGGER_CUES))); відповідний block виконується тільки коли умова true. |
| 1302 | <code>analyze</code> | <code>            add("SR022", "warn", skill,</code> | Додає source-linked Finding правила 'SR022': add('SR022', 'warn', skill, 'Description has no recognized trigger phrase (a heuristic, not proof of poor routing).', 'Review whether the description states when to use the skill.') |
| 1303 | <code>analyze</code> | <code>                "Description has no recognized trigger phrase (a heuristic, not proof of poor routing).",</code> | Продовження інструкції 1302: Додає source-linked Finding правила 'SR022': add('SR022', 'warn', skill, 'Description has no recognized trigger phrase (a heuristic, not proof of poor routing).', 'Review whether the description states when to use the skill.') |
| 1304 | <code>analyze</code> | <code>                "Review whether the description states when to use the skill.")</code> | Продовження інструкції 1302: Додає source-linked Finding правила 'SR022': add('SR022', 'warn', skill, 'Description has no recognized trigger phrase (a heuristic, not proof of poor routing).', 'Review whether the description states when to use the skill.') |
| 1305 | <code>analyze</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1306 | <code>analyze</code> | <code>        if skill.body_lines &gt; body_line_budget:</code> | Умовна гілка: skill.body_lines &gt; body_line_budget; відповідний block виконується тільки коли умова true. |
| 1307 | <code>analyze</code> | <code>            add("SR023", "warn", skill,</code> | Додає source-linked Finding правила 'SR023': add('SR023', 'warn', skill, 'Body is {} non-blank lines. Invoked content persists across turns; compaction can truncate or drop it.'.format(skill.body_lines), 'Split the reference material into files… |
| 1308 | <code>analyze</code> | <code>                "Body is {} non-blank lines. Invoked content persists across turns; "</code> | Продовження інструкції 1307: Додає source-linked Finding правила 'SR023': add('SR023', 'warn', skill, 'Body is {} non-blank lines. Invoked content persists across turns; compaction can truncate or drop it.'.format(skill.body_lines), 'Split the reference material into files… |
| 1309 | <code>analyze</code> | <code>                "compaction can truncate or drop it.".format(skill.body_lines),</code> | Продовження інструкції 1307: Додає source-linked Finding правила 'SR023': add('SR023', 'warn', skill, 'Body is {} non-blank lines. Invoked content persists across turns; compaction can truncate or drop it.'.format(skill.body_lines), 'Split the reference material into files… |
| 1310 | <code>analyze</code> | <code>                "Split the reference material into files the skill reads on demand.")</code> | Продовження інструкції 1307: Додає source-linked Finding правила 'SR023': add('SR023', 'warn', skill, 'Body is {} non-blank lines. Invoked content persists across turns; compaction can truncate or drop it.'.format(skill.body_lines), 'Split the reference material into files… |
| 1311 | <code>analyze</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1312 | <code>analyze</code> | <code>        if authoring:</code> | Умовна гілка: authoring; відповідний block виконується тільки коли умова true. |
| 1313 | <code>analyze</code> | <code>            scalar_fields: Tuple[str, ...] = ("name", "description", "when_to_use")</code> | Типізує scalar_fields як Tuple[str, ...]; initial value ('name', 'description', 'when_to_use') |
| 1314 | <code>analyze</code> | <code>            if portable:</code> | Умовна гілка: portable; відповідний block виконується тільки коли умова true. |
| 1315 | <code>analyze</code> | <code>                scalar_fields += ("license", "compatibility", "allowed-tools")</code> | Оновлює накопичене значення: scalar_fields += ('license', 'compatibility', 'allowed-tools') |
| 1316 | <code>analyze</code> | <code>            for key in scalar_fields:</code> | Ітерує scalar_fields і зв’язує кожен елемент із key |
| 1317 | <code>analyze</code> | <code>                if key in fm and getattr(fm[key], "kind", "string") != "string":</code> | Умовна гілка: key in fm and getattr(fm[key], 'kind', 'string') != 'string'; відповідний block виконується тільки коли умова true. |
| 1318 | <code>analyze</code> | <code>                    add("SR014", "error", skill,</code> | Додає source-linked Finding правила 'SR014': add('SR014', 'error', skill, '`{}` must be a string; found a YAML {}.'.format(key, getattr(fm[key], 'kind', 'string')), 'Use a quoted string or a block scalar.') |
| 1319 | <code>analyze</code> | <code>                        "`{}` must be a string; found a YAML {}.".format(key, getattr(fm[key], "kind", "string")),</code> | Продовження інструкції 1318: Додає source-linked Finding правила 'SR014': add('SR014', 'error', skill, '`{}` must be a string; found a YAML {}.'.format(key, getattr(fm[key], 'kind', 'string')), 'Use a quoted string or a block scalar.') |
| 1320 | <code>analyze</code> | <code>                        "Use a quoted string or a block scalar.")</code> | Продовження інструкції 1318: Додає source-linked Finding правила 'SR014': add('SR014', 'error', skill, '`{}` must be a string; found a YAML {}.'.format(key, getattr(fm[key], 'kind', 'string')), 'Use a quoted string or a block scalar.') |
| 1321 | <code>analyze</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1322 | <code>analyze</code> | <code>        if portable and authoring:</code> | Умовна гілка: portable and authoring; відповідний block виконується тільки коли умова true. |
| 1323 | <code>analyze</code> | <code>            for key in sorted(fm):</code> | Ітерує sorted(fm) і зв’язує кожен елемент із key |
| 1324 | <code>analyze</code> | <code>                if key not in PORTABLE_FIELDS:</code> | Умовна гілка: key not in PORTABLE_FIELDS; відповідний block виконується тільки коли умова true. |
| 1325 | <code>analyze</code> | <code>                    add("SR010", "error", skill,</code> | Додає source-linked Finding правила 'SR010': add('SR010', 'error', skill, '`{}` is not in the Agent Skills spec; claude.ai upload and package_skill.py reject it outright.'.format(key), 'Remove it, or keep the skill Claude Code-only.') |
| 1326 | <code>analyze</code> | <code>                        "`{}` is not in the Agent Skills spec; claude.ai upload and "</code> | Продовження інструкції 1325: Додає source-linked Finding правила 'SR010': add('SR010', 'error', skill, '`{}` is not in the Agent Skills spec; claude.ai upload and package_skill.py reject it outright.'.format(key), 'Remove it, or keep the skill Claude Code-only.') |
| 1327 | <code>analyze</code> | <code>                        "package_skill.py reject it outright.".format(key),</code> | Продовження інструкції 1325: Додає source-linked Finding правила 'SR010': add('SR010', 'error', skill, '`{}` is not in the Agent Skills spec; claude.ai upload and package_skill.py reject it outright.'.format(key), 'Remove it, or keep the skill Claude Code-only.') |
| 1328 | <code>analyze</code> | <code>                        "Remove it, or keep the skill Claude Code-only.")</code> | Продовження інструкції 1325: Додає source-linked Finding правила 'SR010': add('SR010', 'error', skill, '`{}` is not in the Agent Skills spec; claude.ai upload and package_skill.py reject it outright.'.format(key), 'Remove it, or keep the skill Claude Code-only.') |
| 1329 | <code>analyze</code> | <code>            name = fm.get("name", "")</code> | Обчислює та зберігає name ← fm.get('name', '') |
| 1330 | <code>analyze</code> | <code>            if (not name or len(name) &gt; 64 or name != name.lower()</code> | Умовна гілка: not name or len(name) &gt; 64 or name != name.lower() or (not all((char.isalnum() or char == '-' for char in name))) or name.startswith('-') or name.endswith('-') or ('--' in name) or (name != _director…; відповідний block виконується тільки коли умова true. |
| 1331 | <code>analyze</code> | <code>                    or not all(char.isalnum() or char == "-" for char in name)</code> | Продовження інструкції 1330: Умовна гілка: not name or len(name) &gt; 64 or name != name.lower() or (not all((char.isalnum() or char == '-' for char in name))) or name.startswith('-') or name.endswith('-') or ('--' in name) or (name != _director…; відповідний block виконується тільки коли умова true. |
| 1332 | <code>analyze</code> | <code>                    or name.startswith("-") or name.endswith("-") or "--" in name</code> | Продовження інструкції 1330: Умовна гілка: not name or len(name) &gt; 64 or name != name.lower() or (not all((char.isalnum() or char == '-' for char in name))) or name.startswith('-') or name.endswith('-') or ('--' in name) or (name != _director…; відповідний block виконується тільки коли умова true. |
| 1333 | <code>analyze</code> | <code>                    or name != _directory_name(skill.path)</code> | Продовження інструкції 1330: Умовна гілка: not name or len(name) &gt; 64 or name != name.lower() or (not all((char.isalnum() or char == '-' for char in name))) or name.startswith('-') or name.endswith('-') or ('--' in name) or (name != _director…; відповідний block виконується тільки коли умова true. |
| 1334 | <code>analyze</code> | <code>                    or getattr(name, "kind", "string") != "string"):</code> | Продовження інструкції 1330: Умовна гілка: not name or len(name) &gt; 64 or name != name.lower() or (not all((char.isalnum() or char == '-' for char in name))) or name.startswith('-') or name.endswith('-') or ('--' in name) or (name != _director…; відповідний block виконується тільки коли умова true. |
| 1335 | <code>analyze</code> | <code>                add("SR013", "error", skill,</code> | Додає source-linked Finding правила 'SR013': add('SR013', 'error', skill, 'Portable `name` must be a 1-64 character lowercase alphanumeric/hyphen string, with no edge or repeated hyphens, matching the parent directory.', 'Set `name` to the vali… |
| 1336 | <code>analyze</code> | <code>                    "Portable `name` must be a 1-64 character lowercase alphanumeric/hyphen "</code> | Продовження інструкції 1335: Додає source-linked Finding правила 'SR013': add('SR013', 'error', skill, 'Portable `name` must be a 1-64 character lowercase alphanumeric/hyphen string, with no edge or repeated hyphens, matching the parent directory.', 'Set `name` to the vali… |
| 1337 | <code>analyze</code> | <code>                    "string, with no edge or repeated hyphens, matching the parent directory.",</code> | Продовження інструкції 1335: Додає source-linked Finding правила 'SR013': add('SR013', 'error', skill, 'Portable `name` must be a 1-64 character lowercase alphanumeric/hyphen string, with no edge or repeated hyphens, matching the parent directory.', 'Set `name` to the vali… |
| 1338 | <code>analyze</code> | <code>                    "Set `name` to the valid skill directory name; rename the directory if necessary.")</code> | Продовження інструкції 1335: Додає source-linked Finding правила 'SR013': add('SR013', 'error', skill, 'Portable `name` must be a 1-64 character lowercase alphanumeric/hyphen string, with no edge or repeated hyphens, matching the parent directory.', 'Set `name` to the vali… |
| 1339 | <code>analyze</code> | <code>            if len(fm.get("description", "")) &gt; 1024:</code> | Умовна гілка: len(fm.get('description', '')) &gt; 1024; відповідний block виконується тільки коли умова true. |
| 1340 | <code>analyze</code> | <code>                add("SR014", "error", skill,</code> | Додає source-linked Finding правила 'SR014': add('SR014', 'error', skill, '`description` is {} chars; the Agent Skills spec allows 1024.'.format(len(fm['description'])), 'Keep the trigger and summary within 1024 characters.') |
| 1341 | <code>analyze</code> | <code>                    "`description` is {} chars; the Agent Skills spec allows 1024.".format(len(fm["description"])),</code> | Продовження інструкції 1340: Додає source-linked Finding правила 'SR014': add('SR014', 'error', skill, '`description` is {} chars; the Agent Skills spec allows 1024.'.format(len(fm['description'])), 'Keep the trigger and summary within 1024 characters.') |
| 1342 | <code>analyze</code> | <code>                    "Keep the trigger and summary within 1024 characters.")</code> | Продовження інструкції 1340: Додає source-linked Finding правила 'SR014': add('SR014', 'error', skill, '`description` is {} chars; the Agent Skills spec allows 1024.'.format(len(fm['description'])), 'Keep the trigger and summary within 1024 characters.') |
| 1343 | <code>analyze</code> | <code>            compat = fm.get("compatibility", "")</code> | Обчислює та зберігає compat ← fm.get('compatibility', '') |
| 1344 | <code>analyze</code> | <code>            if len(compat) &gt; COMPATIBILITY_CAP:</code> | Умовна гілка: len(compat) &gt; COMPATIBILITY_CAP; відповідний block виконується тільки коли умова true. |
| 1345 | <code>analyze</code> | <code>                add("SR011", "error", skill,</code> | Додає source-linked Finding правила 'SR011': add('SR011', 'error', skill, '`compatibility` is {} chars; the spec allows {}.'.format(len(compat), COMPATIBILITY_CAP), 'Trim it.') |
| 1346 | <code>analyze</code> | <code>                    "`compatibility` is {} chars; the spec allows {}.".format(</code> | Продовження інструкції 1345: Додає source-linked Finding правила 'SR011': add('SR011', 'error', skill, '`compatibility` is {} chars; the spec allows {}.'.format(len(compat), COMPATIBILITY_CAP), 'Trim it.') |
| 1347 | <code>analyze</code> | <code>                        len(compat), COMPATIBILITY_CAP),</code> | Продовження інструкції 1345: Додає source-linked Finding правила 'SR011': add('SR011', 'error', skill, '`compatibility` is {} chars; the spec allows {}.'.format(len(compat), COMPATIBILITY_CAP), 'Trim it.') |
| 1348 | <code>analyze</code> | <code>                    "Trim it.")</code> | Продовження інструкції 1345: Додає source-linked Finding правила 'SR011': add('SR011', 'error', skill, '`compatibility` is {} chars; the spec allows {}.'.format(len(compat), COMPATIBILITY_CAP), 'Trim it.') |
| 1349 | <code>analyze</code> | <code>            elif "compatibility" in fm and not compat:</code> | Наступна умовна гілка, коли попередній if/elif не виконався. |
| 1350 | <code>analyze</code> | <code>                add("SR014", "error", skill,</code> | Додає source-linked Finding правила 'SR014': add('SR014', 'error', skill, '`compatibility` must be non-empty when present.', 'Describe the environment requirements, or omit the field.') |
| 1351 | <code>analyze</code> | <code>                    "`compatibility` must be non-empty when present.",</code> | Продовження інструкції 1350: Додає source-linked Finding правила 'SR014': add('SR014', 'error', skill, '`compatibility` must be non-empty when present.', 'Describe the environment requirements, or omit the field.') |
| 1352 | <code>analyze</code> | <code>                    "Describe the environment requirements, or omit the field.")</code> | Продовження інструкції 1350: Додає source-linked Finding правила 'SR014': add('SR014', 'error', skill, '`compatibility` must be non-empty when present.', 'Describe the environment requirements, or omit the field.') |
| 1353 | <code>analyze</code> | <code>            if "metadata" in fm:</code> | Умовна гілка: 'metadata' in fm; відповідний block виконується тільки коли умова true. |
| 1354 | <code>analyze</code> | <code>                metadata = fm["metadata"]</code> | Обчислює та зберігає metadata ← fm['metadata'] |
| 1355 | <code>analyze</code> | <code>                members = getattr(metadata, "members", None)</code> | Обчислює та зберігає members ← getattr(metadata, 'members', None) |
| 1356 | <code>analyze</code> | <code>                if (getattr(metadata, "kind", "string") != "mapping" or not isinstance(members, dict)</code> | Умовна гілка: getattr(metadata, 'kind', 'string') != 'mapping' or not isinstance(members, dict) or any((getattr(value, 'kind', 'string') != 'string' for value in members.values())); відповідний block виконується тільки коли умова true. |
| 1357 | <code>analyze</code> | <code>                        or any(getattr(value, "kind", "string") != "string" for value in members.values())):</code> | Продовження інструкції 1356: Умовна гілка: getattr(metadata, 'kind', 'string') != 'mapping' or not isinstance(members, dict) or any((getattr(value, 'kind', 'string') != 'string' for value in members.values())); відповідний block виконується тільки коли умова true. |
| 1358 | <code>analyze</code> | <code>                    add("SR014", "error", skill,</code> | Додає source-linked Finding правила 'SR014': add('SR014', 'error', skill, '`metadata` must be a map from string keys to string values.', 'Use an indented map and quote numeric, boolean or null-looking values.') |
| 1359 | <code>analyze</code> | <code>                        "`metadata` must be a map from string keys to string values.",</code> | Продовження інструкції 1358: Додає source-linked Finding правила 'SR014': add('SR014', 'error', skill, '`metadata` must be a map from string keys to string values.', 'Use an indented map and quote numeric, boolean or null-looking values.') |
| 1360 | <code>analyze</code> | <code>                        "Use an indented map and quote numeric, boolean or null-looking values.")</code> | Продовження інструкції 1358: Додає source-linked Finding правила 'SR014': add('SR014', 'error', skill, '`metadata` must be a map from string keys to string values.', 'Use an indented map and quote numeric, boolean or null-looking values.') |
| 1361 | <code>analyze</code> | <code>        elif not portable:</code> | Наступна умовна гілка, коли попередній if/elif не виконався. |
| 1362 | <code>analyze</code> | <code>            for key in sorted(fm):</code> | Ітерує sorted(fm) і зв’язує кожен елемент із key |
| 1363 | <code>analyze</code> | <code>                if key not in KNOWN_FIELDS:</code> | Умовна гілка: key not in KNOWN_FIELDS; відповідний block виконується тільки коли умова true. |
| 1364 | <code>analyze</code> | <code>                    add("SR012", "info", skill,</code> | Додає source-linked Finding правила 'SR012': add('SR012', 'info', skill, 'Unrecognized frontmatter field `{}`.'.format(key), 'Check for a typo, or move it under `metadata:`.') |
| 1365 | <code>analyze</code> | <code>                        "Unrecognized frontmatter field `{}`.".format(key),</code> | Продовження інструкції 1364: Додає source-linked Finding правила 'SR012': add('SR012', 'info', skill, 'Unrecognized frontmatter field `{}`.'.format(key), 'Check for a typo, or move it under `metadata:`.') |
| 1366 | <code>analyze</code> | <code>                        "Check for a typo, or move it under `metadata:`.")</code> | Продовження інструкції 1364: Додає source-linked Finding правила 'SR012': add('SR012', 'info', skill, 'Unrecognized frontmatter field `{}`.'.format(key), 'Check for a typo, or move it under `metadata:`.') |
| 1367 | <code>analyze</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1368 | <code>analyze</code> | <code>    # --- Cross-skill rules ---</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 1369 | <code>analyze</code> | <code>    by_command: Dict[str, List[Skill]] = {}</code> | Типізує by_command як Dict[str, List[Skill]]; initial value {} |
| 1370 | <code>analyze</code> | <code>    for skill in skills:</code> | Ітерує skills і зв’язує кожен елемент із skill |
| 1371 | <code>analyze</code> | <code>        by_command.setdefault(skill.command.lower(), []).append(skill)</code> | Виконує виклик by_command.setdefault(skill.command.lower(), []).append: by_command.setdefault(skill.command.lower(), []).append(skill) |
| 1372 | <code>analyze</code> | <code>    for command, group in sorted(by_command.items()):</code> | Ітерує sorted(by_command.items()) і зв’язує кожен елемент із (command, group) |
| 1373 | <code>analyze</code> | <code>        if len(group) &gt; 1:</code> | Умовна гілка: len(group) &gt; 1; відповідний block виконується тільки коли умова true. |
| 1374 | <code>analyze</code> | <code>            others = ", ".join(str(s.path) for s in group[1:])</code> | Обчислює та зберігає others ← ', '.join((str(s.path) for s in group[1:])) |
| 1375 | <code>analyze</code> | <code>            findings.append(Finding(</code> | Виконує виклик findings.append: findings.append(Finding('SR020', 'warn', group[0].command, str(group[0].path), '{} skills answer to `/{}`; only one of them ever runs.'.format(len(group), command), 'Rename or remove the duplicates: … |
| 1376 | <code>analyze</code> | <code>                "SR020", "warn", group[0].command, str(group[0].path),</code> | Продовження інструкції 1375: Виконує виклик findings.append: findings.append(Finding('SR020', 'warn', group[0].command, str(group[0].path), '{} skills answer to `/{}`; only one of them ever runs.'.format(len(group), command), 'Rename or remove the duplicates: … |
| 1377 | <code>analyze</code> | <code>                "{} skills answer to `/{}`; only one of them ever runs.".format(</code> | Продовження інструкції 1375: Виконує виклик findings.append: findings.append(Finding('SR020', 'warn', group[0].command, str(group[0].path), '{} skills answer to `/{}`; only one of them ever runs.'.format(len(group), command), 'Rename or remove the duplicates: … |
| 1378 | <code>analyze</code> | <code>                    len(group), command),</code> | Продовження інструкції 1375: Виконує виклик findings.append: findings.append(Finding('SR020', 'warn', group[0].command, str(group[0].path), '{} skills answer to `/{}`; only one of them ever runs.'.format(len(group), command), 'Rename or remove the duplicates: … |
| 1379 | <code>analyze</code> | <code>                "Rename or remove the duplicates: {}".format(others),</code> | Продовження інструкції 1375: Виконує виклик findings.append: findings.append(Finding('SR020', 'warn', group[0].command, str(group[0].path), '{} skills answer to `/{}`; only one of them ever runs.'.format(len(group), command), 'Rename or remove the duplicates: … |
| 1380 | <code>analyze</code> | <code>            ))</code> | Продовження інструкції 1375: Виконує виклик findings.append: findings.append(Finding('SR020', 'warn', group[0].command, str(group[0].path), '{} skills answer to `/{}`; only one of them ever runs.'.format(len(group), command), 'Rename or remove the duplicates: … |
| 1381 | <code>analyze</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1382 | <code>analyze</code> | <code>    routable = [s for s in skills if s.description and s.in_listing]</code> | Обчислює та зберігає routable ← [s for s in skills if s.description and s.in_listing] |
| 1383 | <code>analyze</code> | <code>    for cluster in cluster_by_description(routable, similarity):</code> | Ітерує cluster_by_description(routable, similarity) і зв’язує кожен елемент із cluster |
| 1384 | <code>analyze</code> | <code>        head = cluster[0]</code> | Обчислює та зберігає head ← cluster[0] |
| 1385 | <code>analyze</code> | <code>        names = ", ".join("/" + s.command for s in cluster[:4])</code> | Обчислює та зберігає names ← ', '.join(('/' + s.command for s in cluster[:4])) |
| 1386 | <code>analyze</code> | <code>        if len(cluster) &gt; 4:</code> | Умовна гілка: len(cluster) &gt; 4; відповідний block виконується тільки коли умова true. |
| 1387 | <code>analyze</code> | <code>            names += " and {} more".format(len(cluster) - 4)</code> | Оновлює накопичене значення: names += ' and {} more'.format(len(cluster) - 4) |
| 1388 | <code>analyze</code> | <code>        findings.append(Finding(</code> | Виконує виклик findings.append: findings.append(Finding('SR021', 'warn', head.command, str(head.path), '{} skills form a description cluster linked by {:.0%}+ word-overlap pairs: {}. Not every pair in the cluster necessarily meets … |
| 1389 | <code>analyze</code> | <code>            "SR021", "warn", head.command, str(head.path),</code> | Продовження інструкції 1388: Виконує виклик findings.append: findings.append(Finding('SR021', 'warn', head.command, str(head.path), '{} skills form a description cluster linked by {:.0%}+ word-overlap pairs: {}. Not every pair in the cluster necessarily meets … |
| 1390 | <code>analyze</code> | <code>            "{} skills form a description cluster linked by {:.0%}+ word-overlap pairs: {}. "</code> | Продовження інструкції 1388: Виконує виклик findings.append: findings.append(Finding('SR021', 'warn', head.command, str(head.path), '{} skills form a description cluster linked by {:.0%}+ word-overlap pairs: {}. Not every pair in the cluster necessarily meets … |
| 1391 | <code>analyze</code> | <code>            "Not every pair in the cluster necessarily meets the threshold. "</code> | Продовження інструкції 1388: Виконує виклик findings.append: findings.append(Finding('SR021', 'warn', head.command, str(head.path), '{} skills form a description cluster linked by {:.0%}+ word-overlap pairs: {}. Not every pair in the cluster necessarily meets … |
| 1392 | <code>analyze</code> | <code>            "This overlap may make automatic selection ambiguous; it is a heuristic.".format(</code> | Продовження інструкції 1388: Виконує виклик findings.append: findings.append(Finding('SR021', 'warn', head.command, str(head.path), '{} skills form a description cluster linked by {:.0%}+ word-overlap pairs: {}. Not every pair in the cluster necessarily meets … |
| 1393 | <code>analyze</code> | <code>                len(cluster), similarity, names),</code> | Продовження інструкції 1388: Виконує виклик findings.append: findings.append(Finding('SR021', 'warn', head.command, str(head.path), '{} skills form a description cluster linked by {:.0%}+ word-overlap pairs: {}. Not every pair in the cluster necessarily meets … |
| 1394 | <code>analyze</code> | <code>            "Differentiate the triggers, or merge them into one skill.",</code> | Продовження інструкції 1388: Виконує виклик findings.append: findings.append(Finding('SR021', 'warn', head.command, str(head.path), '{} skills form a description cluster linked by {:.0%}+ word-overlap pairs: {}. Not every pair in the cluster necessarily meets … |
| 1395 | <code>analyze</code> | <code>        ))</code> | Продовження інструкції 1388: Виконує виклик findings.append: findings.append(Finding('SR021', 'warn', head.command, str(head.path), '{} skills form a description cluster linked by {:.0%}+ word-overlap pairs: {}. Not every pair in the cluster necessarily meets … |
| 1396 | <code>analyze</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1397 | <code>analyze</code> | <code>    if usage is not None:</code> | Умовна гілка: usage is not None; відповідний block виконується тільки коли умова true. |
| 1398 | <code>analyze</code> | <code>        for skill in skills:</code> | Ітерує skills і зв’язує кожен елемент із skill |
| 1399 | <code>analyze</code> | <code>            if resolve_usage(skill, usage, skills) == 0:</code> | Умовна гілка: resolve_usage(skill, usage, skills) == 0; відповідний block виконується тільки коли умова true. |
| 1400 | <code>analyze</code> | <code>                findings.append(Finding(</code> | Виконує виклик findings.append: findings.append(Finding('SR024', 'info', skill.command, str(skill.path), 'No invocation found in the local transcripts scanned.', 'Check history coverage and installation age before removing it.')) |
| 1401 | <code>analyze</code> | <code>                    "SR024", "info", skill.command, str(skill.path),</code> | Продовження інструкції 1400: Виконує виклик findings.append: findings.append(Finding('SR024', 'info', skill.command, str(skill.path), 'No invocation found in the local transcripts scanned.', 'Check history coverage and installation age before removing it.')) |
| 1402 | <code>analyze</code> | <code>                    "No invocation found in the local transcripts scanned.",</code> | Продовження інструкції 1400: Виконує виклик findings.append: findings.append(Finding('SR024', 'info', skill.command, str(skill.path), 'No invocation found in the local transcripts scanned.', 'Check history coverage and installation age before removing it.')) |
| 1403 | <code>analyze</code> | <code>                    "Check history coverage and installation age before removing it.",</code> | Продовження інструкції 1400: Виконує виклик findings.append: findings.append(Finding('SR024', 'info', skill.command, str(skill.path), 'No invocation found in the local transcripts scanned.', 'Check history coverage and installation age before removing it.')) |
| 1404 | <code>analyze</code> | <code>                ))</code> | Продовження інструкції 1400: Виконує виклик findings.append: findings.append(Finding('SR024', 'info', skill.command, str(skill.path), 'No invocation found in the local transcripts scanned.', 'Check history coverage and installation age before removing it.')) |
| 1405 | <code>analyze</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1406 | <code>analyze</code> | <code>    if listing_budget is not None:</code> | Умовна гілка: listing_budget is not None; відповідний block виконується тільки коли умова true. |
| 1407 | <code>analyze</code> | <code>        for skill in name_only_skills(skills, usage or {}, listing_budget, chars_per_token):</code> | Ітерує name_only_skills(skills, usage or {}, listing_budget, chars_per_token) і зв’язує кожен елемент із skill |
| 1408 | <code>analyze</code> | <code>            findings.append(Finding(</code> | Виконує виклик findings.append: findings.append(Finding('SR030', 'info', skill.command, str(skill.path), 'The estimated listing model drops this description at the configured budget. Its name remains available; actual session order… |
| 1409 | <code>analyze</code> | <code>                "SR030", "info", skill.command, str(skill.path),</code> | Продовження інструкції 1408: Виконує виклик findings.append: findings.append(Finding('SR030', 'info', skill.command, str(skill.path), 'The estimated listing model drops this description at the configured budget. Its name remains available; actual session order… |
| 1410 | <code>analyze</code> | <code>                "The estimated listing model drops this description at the configured "</code> | Продовження інструкції 1408: Виконує виклик findings.append: findings.append(Finding('SR030', 'info', skill.command, str(skill.path), 'The estimated listing model drops this description at the configured budget. Its name remains available; actual session order… |
| 1411 | <code>analyze</code> | <code>                "budget. Its name remains available; actual session ordering can differ.",</code> | Продовження інструкції 1408: Виконує виклик findings.append: findings.append(Finding('SR030', 'info', skill.command, str(skill.path), 'The estimated listing model drops this description at the configured budget. Its name remains available; actual session order… |
| 1412 | <code>analyze</code> | <code>                "Disable unused plugins or local skills, shorten descriptions, or raise the listing "</code> | Продовження інструкції 1408: Виконує виклик findings.append: findings.append(Finding('SR030', 'info', skill.command, str(skill.path), 'The estimated listing model drops this description at the configured budget. Its name remains available; actual session order… |
| 1413 | <code>analyze</code> | <code>                "budget with skillListingBudgetFraction / SLASH_COMMAND_TOOL_CHAR_BUDGET.",</code> | Продовження інструкції 1408: Виконує виклик findings.append: findings.append(Finding('SR030', 'info', skill.command, str(skill.path), 'The estimated listing model drops this description at the configured budget. Its name remains available; actual session order… |
| 1414 | <code>analyze</code> | <code>            ))</code> | Продовження інструкції 1408: Виконує виклик findings.append: findings.append(Finding('SR030', 'info', skill.command, str(skill.path), 'The estimated listing model drops this description at the configured budget. Its name remains available; actual session order… |
| 1415 | <code>analyze</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1416 | <code>analyze</code> | <code>    findings.sort(key=lambda f: (SEVERITIES.get(f.severity, 3), f.rule, f.command))</code> | Виконує виклик findings.sort: findings.sort(key=lambda f: (SEVERITIES.get(f.severity, 3), f.rule, f.command)) |
| 1417 | <code>analyze</code> | <code>    return findings</code> | Завершує поточну функцію та повертає findings |
| 1418 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1419 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1420 | <code>&lt;module&gt;</code> | <code># --- Budget ---------------------------------------------------------------</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 1421 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1422 | <code>Budget</code> | <code>@dataclass</code> | Decorator змінює створення class/function (dataclass або property). |
| 1423 | <code>Budget</code> | <code>class Budget:</code> | Оголошення класу `Budget` та базових класів; модель даних/поведінка розібрана вище. |
| 1424 | <code>Budget</code> | <code>    skills: int               # every discovered entry, skills and commands</code> | Типізує skills як int |
| 1425 | <code>Budget</code> | <code>    name_tokens: int          # every listed name; always in the listing</code> | Типізує name_tokens як int |
| 1426 | <code>Budget</code> | <code>    desc_tokens: int          # descriptions the full listing wants (per-entry capped)</code> | Типізує desc_tokens як int |
| 1427 | <code>Budget</code> | <code>    body_tokens: int</code> | Типізує body_tokens як int |
| 1428 | <code>Budget</code> | <code>    bundle_bytes: int</code> | Типізує bundle_bytes як int |
| 1429 | <code>Budget</code> | <code>    context_window: int</code> | Типізує context_window як int |
| 1430 | <code>Budget</code> | <code>    listing_budget: int       # tokens the harness allows the listing (1% of window)</code> | Типізує listing_budget як int |
| 1431 | <code>Budget</code> | <code>    commands: int = 0         # how many of `skills` are commands/*.md files</code> | Типізує commands як int; initial value 0 |
| 1432 | <code>Budget</code> | <code>    hidden: int = 0           # kept out of context (disable-model-invocation, overrides)</code> | Типізує hidden як int; initial value 0 |
| 1433 | <code>Budget</code> | <code>    retained_desc_tokens: Optional[int] = None</code> | Типізує retained_desc_tokens як Optional[int]; initial value None |
| 1434 | <code>Budget</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1435 | <code>Budget.requested_tokens</code> | <code>    @property</code> | Decorator змінює створення class/function (dataclass або property). |
| 1436 | <code>Budget.requested_tokens</code> | <code>    def requested_tokens(self) -&gt; int:</code> | Оголошення функції `requested_tokens` та її аргументів; детальний контракт розібраний вище. |
| 1437 | <code>Budget.requested_tokens</code> | <code>        """What the whole listing would cost if nothing were dropped."""</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1438 | <code>Budget.requested_tokens</code> | <code>        return self.name_tokens + self.desc_tokens</code> | Завершує поточну функцію та повертає self.name_tokens + self.desc_tokens |
| 1439 | <code>Budget</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1440 | <code>Budget.always_on_tokens</code> | <code>    @property</code> | Decorator змінює створення class/function (dataclass або property). |
| 1441 | <code>Budget.always_on_tokens</code> | <code>    def always_on_tokens(self) -&gt; int:</code> | Оголошення функції `always_on_tokens` та її аргументів; детальний контракт розібраний вище. |
| 1442 | <code>Budget.always_on_tokens</code> | <code>        """Estimated retained names and descriptions in the configured model."""</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1443 | <code>Budget.always_on_tokens</code> | <code>        if self.retained_desc_tokens is not None:</code> | Умовна гілка: self.retained_desc_tokens is not None; відповідний block виконується тільки коли умова true. |
| 1444 | <code>Budget.always_on_tokens</code> | <code>            return self.name_tokens + self.retained_desc_tokens</code> | Завершує поточну функцію та повертає self.name_tokens + self.retained_desc_tokens |
| 1445 | <code>Budget.always_on_tokens</code> | <code>        remaining = max(0, self.listing_budget - self.name_tokens)</code> | Обчислює та зберігає remaining ← max(0, self.listing_budget - self.name_tokens) |
| 1446 | <code>Budget.always_on_tokens</code> | <code>        return self.name_tokens + min(self.desc_tokens, remaining)</code> | Завершує поточну функцію та повертає self.name_tokens + min(self.desc_tokens, remaining) |
| 1447 | <code>Budget</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1448 | <code>Budget.overflows</code> | <code>    @property</code> | Decorator змінює створення class/function (dataclass або property). |
| 1449 | <code>Budget.overflows</code> | <code>    def overflows(self) -&gt; bool:</code> | Оголошення функції `overflows` та її аргументів; детальний контракт розібраний вище. |
| 1450 | <code>Budget.overflows</code> | <code>        return self.requested_tokens &gt; self.listing_budget</code> | Завершує поточну функцію та повертає self.requested_tokens &gt; self.listing_budget |
| 1451 | <code>Budget</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1452 | <code>Budget.context_percent</code> | <code>    @property</code> | Decorator змінює створення class/function (dataclass або property). |
| 1453 | <code>Budget.context_percent</code> | <code>    def context_percent(self) -&gt; float:</code> | Оголошення функції `context_percent` та її аргументів; детальний контракт розібраний вище. |
| 1454 | <code>Budget.context_percent</code> | <code>        return 100.0 * self.always_on_tokens / self.context_window if self.context_window else 0.0</code> | Завершує поточну функцію та повертає 100.0 * self.always_on_tokens / self.context_window if self.context_window else 0.0 |
| 1455 | <code>Budget</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1456 | <code>Budget.budget_percent</code> | <code>    @property</code> | Decorator змінює створення class/function (dataclass або property). |
| 1457 | <code>Budget.budget_percent</code> | <code>    def budget_percent(self) -&gt; float:</code> | Оголошення функції `budget_percent` та її аргументів; детальний контракт розібраний вище. |
| 1458 | <code>Budget.budget_percent</code> | <code>        return 100.0 * self.requested_tokens / self.listing_budget if self.listing_budget else 0.0</code> | Завершує поточну функцію та повертає 100.0 * self.requested_tokens / self.listing_budget if self.listing_budget else 0.0 |
| 1459 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1460 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1461 | <code>_name_tokens</code> | <code>def _name_tokens(skill: Skill, chars_per_token: float) -&gt; int:</code> | Оголошення функції `_name_tokens` та її аргументів; детальний контракт розібраний вище. |
| 1462 | <code>_name_tokens</code> | <code>    """The listing names each entry by the command you'd type."""</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1463 | <code>_name_tokens</code> | <code>    return estimate_tokens(skill.command + ": ", chars_per_token)</code> | Завершує поточну функцію та повертає estimate_tokens(skill.command + ': ', chars_per_token) |
| 1464 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1465 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1466 | <code>_desc_tokens</code> | <code>def _desc_tokens(skill: Skill, chars_per_token: float) -&gt; int:</code> | Оголошення функції `_desc_tokens` та її аргументів; детальний контракт розібраний вище. |
| 1467 | <code>_desc_tokens</code> | <code>    if skill.override == "name-only":</code> | Умовна гілка: skill.override == 'name-only'; відповідний block виконується тільки коли умова true. |
| 1468 | <code>_desc_tokens</code> | <code>        return 0</code> | Завершує поточну функцію та повертає 0 |
| 1469 | <code>_desc_tokens</code> | <code>    return estimate_tokens(skill.routing_text[:LISTING_CHAR_CAP], chars_per_token)</code> | Завершує поточну функцію та повертає estimate_tokens(skill.routing_text[:LISTING_CHAR_CAP], chars_per_token) |
| 1470 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1471 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1472 | <code>listing_tokens</code> | <code>def listing_tokens(skill: Skill, chars_per_token: float) -&gt; int:</code> | Оголошення функції `listing_tokens` та її аргументів; детальний контракт розібраний вище. |
| 1473 | <code>listing_tokens</code> | <code>    """Requested cost of an eligible entry, before collection budget/precedence."""</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1474 | <code>listing_tokens</code> | <code>    if not skill.in_listing:</code> | Умовна гілка: not skill.in_listing; відповідний block виконується тільки коли умова true. |
| 1475 | <code>listing_tokens</code> | <code>        return 0</code> | Завершує поточну функцію та повертає 0 |
| 1476 | <code>listing_tokens</code> | <code>    return _name_tokens(skill, chars_per_token) + _desc_tokens(skill, chars_per_token)</code> | Завершує поточну функцію та повертає _name_tokens(skill, chars_per_token) + _desc_tokens(skill, chars_per_token) |
| 1477 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1478 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1479 | <code>_listed</code> | <code>def _listed(skills: Sequence[Skill]) -&gt; List[Skill]:</code> | Оголошення функції `_listed` та її аргументів; детальний контракт розібраний вище. |
| 1480 | <code>_listed</code> | <code>    """The entries eligible for the estimated listing: one per</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1481 | <code>_listed</code> | <code>    command name. When a skill and a command file share a name, the skill wins,</code> | Продовження інструкції 1480: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1482 | <code>_listed</code> | <code>    so the duplicate never reaches the listing (SR020 still reports it)."""</code> | Продовження інструкції 1480: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1483 | <code>_listed</code> | <code>    chosen: Dict[str, Skill] = {}</code> | Типізує chosen як Dict[str, Skill]; initial value {} |
| 1484 | <code>_listed</code> | <code>    for skill in skills:</code> | Ітерує skills і зв’язує кожен елемент із skill |
| 1485 | <code>_listed</code> | <code>        if not skill.in_listing:</code> | Умовна гілка: not skill.in_listing; відповідний block виконується тільки коли умова true. |
| 1486 | <code>_listed</code> | <code>            continue</code> | Пропускає решту цієї ітерації; переходить до наступного елемента. |
| 1487 | <code>_listed</code> | <code>        key = skill.command.lower()</code> | Обчислює та зберігає key ← skill.command.lower() |
| 1488 | <code>_listed</code> | <code>        if key not in chosen or (chosen[key].kind == "command" and skill.kind == "skill"):</code> | Умовна гілка: key not in chosen or (chosen[key].kind == 'command' and skill.kind == 'skill'); відповідний block виконується тільки коли умова true. |
| 1489 | <code>_listed</code> | <code>            chosen[key] = skill</code> | Обчислює та зберігає chosen[key] ← skill |
| 1490 | <code>_listed</code> | <code>    return list(chosen.values())</code> | Завершує поточну функцію та повертає list(chosen.values()) |
| 1491 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1492 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1493 | <code>name_only_skills</code> | <code>def name_only_skills(</code> | Оголошення функції `name_only_skills` та її аргументів; детальний контракт розібраний вище. |
| 1494 | <code>name_only_skills</code> | <code>    skills: Sequence[Skill], usage: Dict[str, int], listing_budget: int, chars_per_token: float</code> | Оголошення функції `name_only_skills` та її аргументів; детальний контракт розібраний вище. |
| 1495 | <code>name_only_skills</code> | <code>) -&gt; List[Skill]:</code> | Оголошення функції `name_only_skills` та її аргументів; детальний контракт розібраний вище. |
| 1496 | <code>name_only_skills</code> | <code>    """Listed skills whose description won't fit the listing budget.</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1497 | <code>name_only_skills</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1498 | <code>name_only_skills</code> | <code>    Names of everything in the listing are always kept; the remaining budget</code> | Продовження інструкції 1496: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1499 | <code>name_only_skills</code> | <code>    fills with descriptions most-used first (Claude Code drops the least-used</code> | Продовження інструкції 1496: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1500 | <code>name_only_skills</code> | <code>    ones), tie-broken by the cheaper description so more of them fit. Skills</code> | Продовження інструкції 1496: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1501 | <code>name_only_skills</code> | <code>    hidden from the model, or set to name-only on purpose, are not reported.</code> | Продовження інструкції 1496: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1502 | <code>name_only_skills</code> | <code>    """</code> | Продовження інструкції 1496: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1503 | <code>name_only_skills</code> | <code>    listed = _listed(skills)</code> | Обчислює та зберігає listed ← _listed(skills) |
| 1504 | <code>name_only_skills</code> | <code>    remaining = max(0, listing_budget - sum(_name_tokens(s, chars_per_token) for s in listed))</code> | Обчислює та зберігає remaining ← max(0, listing_budget - sum((_name_tokens(s, chars_per_token) for s in listed))) |
| 1505 | <code>name_only_skills</code> | <code>    dropped: List[Skill] = []</code> | Типізує dropped як List[Skill]; initial value [] |
| 1506 | <code>name_only_skills</code> | <code>    candidates = [s for s in listed if s.override != "name-only" and s.routing_text]</code> | Обчислює та зберігає candidates ← [s for s in listed if s.override != 'name-only' and s.routing_text] |
| 1507 | <code>name_only_skills</code> | <code>    ordered = sorted(</code> | Обчислює та зберігає ordered ← sorted(candidates, key=lambda s: (-resolve_usage(s, usage, skills), _desc_tokens(s, chars_per_token))) |
| 1508 | <code>name_only_skills</code> | <code>        candidates,</code> | Продовження інструкції 1507: Обчислює та зберігає ordered ← sorted(candidates, key=lambda s: (-resolve_usage(s, usage, skills), _desc_tokens(s, chars_per_token))) |
| 1509 | <code>name_only_skills</code> | <code>        key=lambda s: (-resolve_usage(s, usage, skills), _desc_tokens(s, chars_per_token)),</code> | Продовження інструкції 1507: Обчислює та зберігає ordered ← sorted(candidates, key=lambda s: (-resolve_usage(s, usage, skills), _desc_tokens(s, chars_per_token))) |
| 1510 | <code>name_only_skills</code> | <code>    )</code> | Продовження інструкції 1507: Обчислює та зберігає ordered ← sorted(candidates, key=lambda s: (-resolve_usage(s, usage, skills), _desc_tokens(s, chars_per_token))) |
| 1511 | <code>name_only_skills</code> | <code>    for skill in ordered:</code> | Ітерує ordered і зв’язує кожен елемент із skill |
| 1512 | <code>name_only_skills</code> | <code>        cost = _desc_tokens(skill, chars_per_token)</code> | Обчислює та зберігає cost ← _desc_tokens(skill, chars_per_token) |
| 1513 | <code>name_only_skills</code> | <code>        if remaining &gt;= cost:</code> | Умовна гілка: remaining &gt;= cost; відповідний block виконується тільки коли умова true. |
| 1514 | <code>name_only_skills</code> | <code>            remaining -= cost</code> | Оновлює накопичене значення: remaining -= cost |
| 1515 | <code>name_only_skills</code> | <code>        else:</code> | Alternative branch для попередньої умови або завершення циклу без break. |
| 1516 | <code>name_only_skills</code> | <code>            dropped.append(skill)</code> | Виконує виклик dropped.append: dropped.append(skill) |
| 1517 | <code>name_only_skills</code> | <code>    return dropped</code> | Завершує поточну функцію та повертає dropped |
| 1518 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1519 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1520 | <code>retained_listing_costs</code> | <code>def retained_listing_costs(</code> | Оголошення функції `retained_listing_costs` та її аргументів; детальний контракт розібраний вище. |
| 1521 | <code>retained_listing_costs</code> | <code>    skills: Sequence[Skill], usage: Optional[Dict[str, int]],</code> | Оголошення функції `retained_listing_costs` та її аргументів; детальний контракт розібраний вище. |
| 1522 | <code>retained_listing_costs</code> | <code>    listing_budget: int, chars_per_token: float,</code> | Оголошення функції `retained_listing_costs` та її аргументів; детальний контракт розібраний вище. |
| 1523 | <code>retained_listing_costs</code> | <code>) -&gt; Dict[int, int]:</code> | Оголошення функції `retained_listing_costs` та її аргументів; детальний контракт розібраний вище. |
| 1524 | <code>retained_listing_costs</code> | <code>    """Per-entry costs for the same estimated retention model used by SR030.</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1525 | <code>retained_listing_costs</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1526 | <code>retained_listing_costs</code> | <code>    Identity keys distinguish shadowed entries with the same command name.</code> | Продовження інструкції 1524: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1527 | <code>retained_listing_costs</code> | <code>    They are internal only and are never serialized.</code> | Продовження інструкції 1524: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1528 | <code>retained_listing_costs</code> | <code>    """</code> | Продовження інструкції 1524: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1529 | <code>retained_listing_costs</code> | <code>    dropped = {id(s) for s in name_only_skills(skills, usage or {}, listing_budget, chars_per_token)}</code> | Обчислює та зберігає dropped ← {id(s) for s in name_only_skills(skills, usage or {}, listing_budget, chars_per_token)} |
| 1530 | <code>retained_listing_costs</code> | <code>    return {id(s): _name_tokens(s, chars_per_token) +</code> | Завершує поточну функцію та повертає {id(s): _name_tokens(s, chars_per_token) + (0 if id(s) in dropped else _desc_tokens(s, chars_per_token)) for s in _listed(skills)} |
| 1531 | <code>retained_listing_costs</code> | <code>            (0 if id(s) in dropped else _desc_tokens(s, chars_per_token))</code> | Продовження інструкції 1530: Завершує поточну функцію та повертає {id(s): _name_tokens(s, chars_per_token) + (0 if id(s) in dropped else _desc_tokens(s, chars_per_token)) for s in _listed(skills)} |
| 1532 | <code>retained_listing_costs</code> | <code>            for s in _listed(skills)}</code> | Продовження інструкції 1530: Завершує поточну функцію та повертає {id(s): _name_tokens(s, chars_per_token) + (0 if id(s) in dropped else _desc_tokens(s, chars_per_token)) for s in _listed(skills)} |
| 1533 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1534 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1535 | <code>budget</code> | <code>def budget(</code> | Оголошення функції `budget` та її аргументів; детальний контракт розібраний вище. |
| 1536 | <code>budget</code> | <code>    skills: Sequence[Skill],</code> | Оголошення функції `budget` та її аргументів; детальний контракт розібраний вище. |
| 1537 | <code>budget</code> | <code>    chars_per_token: float,</code> | Оголошення функції `budget` та її аргументів; детальний контракт розібраний вище. |
| 1538 | <code>budget</code> | <code>    context_window: int,</code> | Оголошення функції `budget` та її аргументів; детальний контракт розібраний вище. |
| 1539 | <code>budget</code> | <code>    budget_fraction: float = DEFAULT_BUDGET_FRACTION,</code> | Оголошення функції `budget` та її аргументів; детальний контракт розібраний вище. |
| 1540 | <code>budget</code> | <code>    listing_budget_tokens: Optional[int] = None,</code> | Оголошення функції `budget` та її аргументів; детальний контракт розібраний вище. |
| 1541 | <code>budget</code> | <code>    usage: Optional[Dict[str, int]] = None,</code> | Оголошення функції `budget` та її аргументів; детальний контракт розібраний вище. |
| 1542 | <code>budget</code> | <code>) -&gt; Budget:</code> | Оголошення функції `budget` та її аргументів; детальний контракт розібраний вище. |
| 1543 | <code>budget</code> | <code>    """Size the listing. Only skills advertised to the model count toward it;</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1544 | <code>budget</code> | <code>    `listing_budget_tokens` pins the budget (SLASH_COMMAND_TOOL_CHAR_BUDGET)."""</code> | Продовження інструкції 1543: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1545 | <code>budget</code> | <code>    listed = _listed(skills)</code> | Обчислює та зберігає listed ← _listed(skills) |
| 1546 | <code>budget</code> | <code>    if listing_budget_tokens is None:</code> | Умовна гілка: listing_budget_tokens is None; відповідний block виконується тільки коли умова true. |
| 1547 | <code>budget</code> | <code>        listing_budget_tokens = int(round(context_window * budget_fraction))</code> | Обчислює та зберігає listing_budget_tokens ← int(round(context_window * budget_fraction)) |
| 1548 | <code>budget</code> | <code>    retained = retained_listing_costs(skills, usage, listing_budget_tokens, chars_per_token)</code> | Обчислює та зберігає retained ← retained_listing_costs(skills, usage, listing_budget_tokens, chars_per_token) |
| 1549 | <code>budget</code> | <code>    names = sum(_name_tokens(s, chars_per_token) for s in listed)</code> | Обчислює та зберігає names ← sum((_name_tokens(s, chars_per_token) for s in listed)) |
| 1550 | <code>budget</code> | <code>    return Budget(</code> | Завершує поточну функцію та повертає Budget(skills=len(skills), name_tokens=names, desc_tokens=sum((_desc_tokens(s, chars_per_token) for s in listed)), body_tokens=sum((estimate_tokens(s.body, chars_per_token) for s in skills)), bundle_… |
| 1551 | <code>budget</code> | <code>        skills=len(skills),</code> | Продовження інструкції 1550: Завершує поточну функцію та повертає Budget(skills=len(skills), name_tokens=names, desc_tokens=sum((_desc_tokens(s, chars_per_token) for s in listed)), body_tokens=sum((estimate_tokens(s.body, chars_per_token) for s in skills)), bundle_… |
| 1552 | <code>budget</code> | <code>        name_tokens=names,</code> | Продовження інструкції 1550: Завершує поточну функцію та повертає Budget(skills=len(skills), name_tokens=names, desc_tokens=sum((_desc_tokens(s, chars_per_token) for s in listed)), body_tokens=sum((estimate_tokens(s.body, chars_per_token) for s in skills)), bundle_… |
| 1553 | <code>budget</code> | <code>        desc_tokens=sum(_desc_tokens(s, chars_per_token) for s in listed),</code> | Продовження інструкції 1550: Завершує поточну функцію та повертає Budget(skills=len(skills), name_tokens=names, desc_tokens=sum((_desc_tokens(s, chars_per_token) for s in listed)), body_tokens=sum((estimate_tokens(s.body, chars_per_token) for s in skills)), bundle_… |
| 1554 | <code>budget</code> | <code>        body_tokens=sum(estimate_tokens(s.body, chars_per_token) for s in skills),</code> | Продовження інструкції 1550: Завершує поточну функцію та повертає Budget(skills=len(skills), name_tokens=names, desc_tokens=sum((_desc_tokens(s, chars_per_token) for s in listed)), body_tokens=sum((estimate_tokens(s.body, chars_per_token) for s in skills)), bundle_… |
| 1555 | <code>budget</code> | <code>        bundle_bytes=sum(s.bundle_bytes for s in skills),</code> | Продовження інструкції 1550: Завершує поточну функцію та повертає Budget(skills=len(skills), name_tokens=names, desc_tokens=sum((_desc_tokens(s, chars_per_token) for s in listed)), body_tokens=sum((estimate_tokens(s.body, chars_per_token) for s in skills)), bundle_… |
| 1556 | <code>budget</code> | <code>        context_window=context_window,</code> | Продовження інструкції 1550: Завершує поточну функцію та повертає Budget(skills=len(skills), name_tokens=names, desc_tokens=sum((_desc_tokens(s, chars_per_token) for s in listed)), body_tokens=sum((estimate_tokens(s.body, chars_per_token) for s in skills)), bundle_… |
| 1557 | <code>budget</code> | <code>        listing_budget=listing_budget_tokens,</code> | Продовження інструкції 1550: Завершує поточну функцію та повертає Budget(skills=len(skills), name_tokens=names, desc_tokens=sum((_desc_tokens(s, chars_per_token) for s in listed)), body_tokens=sum((estimate_tokens(s.body, chars_per_token) for s in skills)), bundle_… |
| 1558 | <code>budget</code> | <code>        commands=sum(1 for s in skills if s.kind == "command"),</code> | Продовження інструкції 1550: Завершує поточну функцію та повертає Budget(skills=len(skills), name_tokens=names, desc_tokens=sum((_desc_tokens(s, chars_per_token) for s in listed)), body_tokens=sum((estimate_tokens(s.body, chars_per_token) for s in skills)), bundle_… |
| 1559 | <code>budget</code> | <code>        hidden=sum(1 for s in skills if not s.in_listing),</code> | Продовження інструкції 1550: Завершує поточну функцію та повертає Budget(skills=len(skills), name_tokens=names, desc_tokens=sum((_desc_tokens(s, chars_per_token) for s in listed)), body_tokens=sum((estimate_tokens(s.body, chars_per_token) for s in skills)), bundle_… |
| 1560 | <code>budget</code> | <code>        retained_desc_tokens=sum(retained.values()) - names,</code> | Продовження інструкції 1550: Завершує поточну функцію та повертає Budget(skills=len(skills), name_tokens=names, desc_tokens=sum((_desc_tokens(s, chars_per_token) for s in listed)), body_tokens=sum((estimate_tokens(s.body, chars_per_token) for s in skills)), bundle_… |
| 1561 | <code>budget</code> | <code>    )</code> | Продовження інструкції 1550: Завершує поточну функцію та повертає Budget(skills=len(skills), name_tokens=names, desc_tokens=sum((_desc_tokens(s, chars_per_token) for s in listed)), body_tokens=sum((estimate_tokens(s.body, chars_per_token) for s in skills)), bundle_… |
| 1562 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1563 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1564 | <code>&lt;module&gt;</code> | <code># --- Reporting ------------------------------------------------------------</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 1565 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1566 | <code>&lt;module&gt;</code> | <code>COLORS = {</code> | Обчислює та зберігає COLORS ← {'error': '\x1b[31m', 'warn': '\x1b[33m', 'info': '\x1b[36m', 'reset': '\x1b[0m', 'bold': '\x1b[1m', 'dim': '\x1b[2m'} |
| 1567 | <code>&lt;module&gt;</code> | <code>    "error": "\033[31m", "warn": "\033[33m", "info": "\033[36m",</code> | Продовження інструкції 1566: Обчислює та зберігає COLORS ← {'error': '\x1b[31m', 'warn': '\x1b[33m', 'info': '\x1b[36m', 'reset': '\x1b[0m', 'bold': '\x1b[1m', 'dim': '\x1b[2m'} |
| 1568 | <code>&lt;module&gt;</code> | <code>    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[2m",</code> | Продовження інструкції 1566: Обчислює та зберігає COLORS ← {'error': '\x1b[31m', 'warn': '\x1b[33m', 'info': '\x1b[36m', 'reset': '\x1b[0m', 'bold': '\x1b[1m', 'dim': '\x1b[2m'} |
| 1569 | <code>&lt;module&gt;</code> | <code>}</code> | Продовження інструкції 1566: Обчислює та зберігає COLORS ← {'error': '\x1b[31m', 'warn': '\x1b[33m', 'info': '\x1b[36m', 'reset': '\x1b[0m', 'bold': '\x1b[1m', 'dim': '\x1b[2m'} |
| 1570 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1571 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1572 | <code>_paint</code> | <code>def _paint(text: str, style: str, enabled: bool) -&gt; str:</code> | Оголошення функції `_paint` та її аргументів; детальний контракт розібраний вище. |
| 1573 | <code>_paint</code> | <code>    if not enabled:</code> | Умовна гілка: not enabled; відповідний block виконується тільки коли умова true. |
| 1574 | <code>_paint</code> | <code>        return text</code> | Завершує поточну функцію та повертає text |
| 1575 | <code>_paint</code> | <code>    return "{}{}{}".format(COLORS.get(style, ""), text, COLORS["reset"])</code> | Завершує поточну функцію та повертає '{}{}{}'.format(COLORS.get(style, ''), text, COLORS['reset']) |
| 1576 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1577 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1578 | <code>_human_bytes</code> | <code>def _human_bytes(count: int) -&gt; str:</code> | Оголошення функції `_human_bytes` та її аргументів; детальний контракт розібраний вище. |
| 1579 | <code>_human_bytes</code> | <code>    value = float(count)</code> | Обчислює та зберігає value ← float(count) |
| 1580 | <code>_human_bytes</code> | <code>    for unit in ("B", "KB", "MB"):</code> | Ітерує ('B', 'KB', 'MB') і зв’язує кожен елемент із unit |
| 1581 | <code>_human_bytes</code> | <code>        if value &lt; 1024:</code> | Умовна гілка: value &lt; 1024; відповідний block виконується тільки коли умова true. |
| 1582 | <code>_human_bytes</code> | <code>            return "{:.0f}{}".format(value, unit) if unit == "B" else "{:.1f}{}".format(value, unit)</code> | Завершує поточну функцію та повертає '{:.0f}{}'.format(value, unit) if unit == 'B' else '{:.1f}{}'.format(value, unit) |
| 1583 | <code>_human_bytes</code> | <code>        value /= 1024</code> | Оновлює накопичене значення: value /= 1024 |
| 1584 | <code>_human_bytes</code> | <code>    return "{:.1f}GB".format(value)</code> | Завершує поточну функцію та повертає '{:.1f}GB'.format(value) |
| 1585 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1586 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1587 | <code>_display_text</code> | <code>def _display_text(text: str, preserve_layout: bool = False) -&gt; str:</code> | Оголошення функції `_display_text` та її аргументів; детальний контракт розібраний вище. |
| 1588 | <code>_display_text</code> | <code>    """Render controls in untrusted file metadata as visible escape notation."""</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1589 | <code>_display_text</code> | <code>    return "".join(char if preserve_layout and char in "\n\t" else</code> | Завершує поточну функцію та повертає ''.join((char if preserve_layout and char in '\n\t' else '\\x{:02x}'.format(ord(char)) if ord(char) &lt; 32 or 127 &lt;= ord(char) &lt;= 159 else '\\u{:04x}'.format(ord(char)) if 55296 &lt;= ord(char) &lt;= 57343 o… |
| 1590 | <code>_display_text</code> | <code>                   "\\x{:02x}".format(ord(char)) if ord(char) &lt; 32 or 127 &lt;= ord(char) &lt;= 159</code> | Продовження інструкції 1589: Завершує поточну функцію та повертає ''.join((char if preserve_layout and char in '\n\t' else '\\x{:02x}'.format(ord(char)) if ord(char) &lt; 32 or 127 &lt;= ord(char) &lt;= 159 else '\\u{:04x}'.format(ord(char)) if 55296 &lt;= ord(char) &lt;= 57343 o… |
| 1591 | <code>_display_text</code> | <code>                   else "\\u{:04x}".format(ord(char)) if</code> | Продовження інструкції 1589: Завершує поточну функцію та повертає ''.join((char if preserve_layout and char in '\n\t' else '\\x{:02x}'.format(ord(char)) if ord(char) &lt; 32 or 127 &lt;= ord(char) &lt;= 159 else '\\u{:04x}'.format(ord(char)) if 55296 &lt;= ord(char) &lt;= 57343 o… |
| 1592 | <code>_display_text</code> | <code>                   0xD800 &lt;= ord(char) &lt;= 0xDFFF or ord(char) in (0xFFFE, 0xFFFF)</code> | Продовження інструкції 1589: Завершує поточну функцію та повертає ''.join((char if preserve_layout and char in '\n\t' else '\\x{:02x}'.format(ord(char)) if ord(char) &lt; 32 or 127 &lt;= ord(char) &lt;= 159 else '\\u{:04x}'.format(ord(char)) if 55296 &lt;= ord(char) &lt;= 57343 o… |
| 1593 | <code>_display_text</code> | <code>                   else char for char in text)</code> | Продовження інструкції 1589: Завершує поточну функцію та повертає ''.join((char if preserve_layout and char in '\n\t' else '\\x{:02x}'.format(ord(char)) if ord(char) &lt; 32 or 127 &lt;= ord(char) &lt;= 159 else '\\u{:04x}'.format(ord(char)) if 55296 &lt;= ord(char) &lt;= 57343 o… |
| 1594 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1595 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1596 | <code>render</code> | <code>def render(</code> | Оголошення функції `render` та її аргументів; детальний контракт розібраний вище. |
| 1597 | <code>render</code> | <code>    skills: Sequence[Skill],</code> | Оголошення функції `render` та її аргументів; детальний контракт розібраний вище. |
| 1598 | <code>render</code> | <code>    findings: Sequence[Finding],</code> | Оголошення функції `render` та її аргументів; детальний контракт розібраний вище. |
| 1599 | <code>render</code> | <code>    totals: Budget,</code> | Оголошення функції `render` та її аргументів; детальний контракт розібраний вище. |
| 1600 | <code>render</code> | <code>    usage: Optional[Dict[str, int]],</code> | Оголошення функції `render` та її аргументів; детальний контракт розібраний вище. |
| 1601 | <code>render</code> | <code>    chars_per_token: float,</code> | Оголошення функції `render` та її аргументів; детальний контракт розібраний вище. |
| 1602 | <code>render</code> | <code>    top: int,</code> | Оголошення функції `render` та її аргументів; детальний контракт розібраний вище. |
| 1603 | <code>render</code> | <code>    color: bool,</code> | Оголошення функції `render` та її аргументів; детальний контракт розібраний вище. |
| 1604 | <code>render</code> | <code>    per_rule_limit: int = 20,</code> | Оголошення функції `render` та її аргументів; детальний контракт розібраний вище. |
| 1605 | <code>render</code> | <code>) -&gt; str:</code> | Оголошення функції `render` та її аргументів; детальний контракт розібраний вище. |
| 1606 | <code>render</code> | <code>    out: List[str] = []</code> | Типізує out як List[str]; initial value [] |
| 1607 | <code>render</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1608 | <code>render.bold</code> | <code>    def bold(text: str) -&gt; str:</code> | Оголошення функції `bold` та її аргументів; детальний контракт розібраний вище. |
| 1609 | <code>render.bold</code> | <code>        return _paint(text, "bold", color)</code> | Завершує поточну функцію та повертає _paint(text, 'bold', color) |
| 1610 | <code>render</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1611 | <code>render.dim</code> | <code>    def dim(text: str) -&gt; str:</code> | Оголошення функції `dim` та її аргументів; детальний контракт розібраний вище. |
| 1612 | <code>render.dim</code> | <code>        return _paint(text, "dim", color)</code> | Завершує поточну функцію та повертає _paint(text, 'dim', color) |
| 1613 | <code>render</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1614 | <code>render</code> | <code>    errors = sum(1 for f in findings if f.severity == "error")</code> | Обчислює та зберігає errors ← sum((1 for f in findings if f.severity == 'error')) |
| 1615 | <code>render</code> | <code>    warns = sum(1 for f in findings if f.severity == "warn")</code> | Обчислює та зберігає warns ← sum((1 for f in findings if f.severity == 'warn')) |
| 1616 | <code>render</code> | <code>    dead = sum(1 for f in findings if f.rule == "SR024")</code> | Обчислює та зберігає dead ← sum((1 for f in findings if f.rule == 'SR024')) |
| 1617 | <code>render</code> | <code>    name_only = sum(1 for f in findings if f.rule == "SR030")</code> | Обчислює та зберігає name_only ← sum((1 for f in findings if f.rule == 'SR030')) |
| 1618 | <code>render</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1619 | <code>render</code> | <code>    out.append("")</code> | Виконує виклик out.append: out.append('') |
| 1620 | <code>render</code> | <code>    out.append(bold("skillrot {}".format(__version__)))</code> | Виконує виклик out.append: out.append(bold('skillrot {}'.format(__version__))) |
| 1621 | <code>render</code> | <code>    out.append("")</code> | Виконує виклик out.append: out.append('') |
| 1622 | <code>render</code> | <code>    out.append(bold("  Context bill (estimated Claude Code listing)"))</code> | Виконує виклик out.append: out.append(bold('  Context bill (estimated Claude Code listing)')) |
| 1623 | <code>render</code> | <code>    found = "{} skills".format(totals.skills - totals.commands)</code> | Обчислює та зберігає found ← '{} skills'.format(totals.skills - totals.commands) |
| 1624 | <code>render</code> | <code>    if totals.commands:</code> | Умовна гілка: totals.commands; відповідний block виконується тільки коли умова true. |
| 1625 | <code>render</code> | <code>        found += " + {} commands".format(totals.commands)</code> | Оновлює накопичене значення: found += ' + {} commands'.format(totals.commands) |
| 1626 | <code>render</code> | <code>    out.append("    {} discovered".format(found))</code> | Виконує виклик out.append: out.append('    {} discovered'.format(found)) |
| 1627 | <code>render</code> | <code>    if totals.hidden:</code> | Умовна гілка: totals.hidden; відповідний block виконується тільки коли умова true. |
| 1628 | <code>render</code> | <code>        out.append("    {} kept out of context (disable-model-invocation / skillOverrides)".format(</code> | Виконує виклик out.append: out.append('    {} kept out of context (disable-model-invocation / skillOverrides)'.format(totals.hidden)) |
| 1629 | <code>render</code> | <code>            totals.hidden))</code> | Продовження інструкції 1628: Виконує виклик out.append: out.append('    {} kept out of context (disable-model-invocation / skillOverrides)'.format(totals.hidden)) |
| 1630 | <code>render</code> | <code>    out.append("    ~{:,} tokens in the always-on listing  ({:.1f}% of a {:,}-token window)".format(</code> | Виконує виклик out.append: out.append('    ~{:,} tokens in the always-on listing  ({:.1f}% of a {:,}-token window)'.format(totals.always_on_tokens, totals.context_percent, totals.context_window)) |
| 1631 | <code>render</code> | <code>        totals.always_on_tokens, totals.context_percent, totals.context_window))</code> | Продовження інструкції 1630: Виконує виклик out.append: out.append('    ~{:,} tokens in the always-on listing  ({:.1f}% of a {:,}-token window)'.format(totals.always_on_tokens, totals.context_percent, totals.context_window)) |
| 1632 | <code>render</code> | <code>    out.append("    ~{:,} tok listing budget ({:.0f}% requested)".format(</code> | Виконує виклик out.append: out.append('    ~{:,} tok listing budget ({:.0f}% requested)'.format(totals.listing_budget, totals.budget_percent)) |
| 1633 | <code>render</code> | <code>        totals.listing_budget, totals.budget_percent))</code> | Продовження інструкції 1632: Виконує виклик out.append: out.append('    ~{:,} tok listing budget ({:.0f}% requested)'.format(totals.listing_budget, totals.budget_percent)) |
| 1634 | <code>render</code> | <code>    if totals.overflows:</code> | Умовна гілка: totals.overflows; відповідний block виконується тільки коли умова true. |
| 1635 | <code>render</code> | <code>        over = totals.requested_tokens - totals.listing_budget</code> | Обчислює та зберігає over ← totals.requested_tokens - totals.listing_budget |
| 1636 | <code>render</code> | <code>        out.append("    " + _paint(</code> | Виконує виклик out.append: out.append('    ' + _paint('over budget by ~{:,} tok: the model predicts description drops'.format(over), 'warn', color)) |
| 1637 | <code>render</code> | <code>            "over budget by ~{:,} tok: the model predicts description drops".format(over),</code> | Продовження інструкції 1636: Виконує виклик out.append: out.append('    ' + _paint('over budget by ~{:,} tok: the model predicts description drops'.format(over), 'warn', color)) |
| 1638 | <code>render</code> | <code>            "warn", color))</code> | Продовження інструкції 1636: Виконує виклик out.append: out.append('    ' + _paint('over budget by ~{:,} tok: the model predicts description drops'.format(over), 'warn', color)) |
| 1639 | <code>render</code> | <code>    out.append("    ~{:,} tokens of skill bodies waiting to load".format(totals.body_tokens))</code> | Виконує виклик out.append: out.append('    ~{:,} tokens of skill bodies waiting to load'.format(totals.body_tokens)) |
| 1640 | <code>render</code> | <code>    out.append("    {} on disk".format(_human_bytes(totals.bundle_bytes)))</code> | Виконує виклик out.append: out.append('    {} on disk'.format(_human_bytes(totals.bundle_bytes))) |
| 1641 | <code>render</code> | <code>    out.append("")</code> | Виконує виклик out.append: out.append('') |
| 1642 | <code>render</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1643 | <code>render</code> | <code>    if totals.skills and top &gt; 0:</code> | Умовна гілка: totals.skills and top &gt; 0; відповідний block виконується тільки коли умова true. |
| 1644 | <code>render</code> | <code>        ranked = sorted(_listed(skills), key=lambda s: listing_tokens(s, chars_per_token), reverse=True)[:top]</code> | Обчислює та зберігає ranked ← sorted(_listed(skills), key=lambda s: listing_tokens(s, chars_per_token), reverse=True)[:top] |
| 1645 | <code>render</code> | <code>        retained = retained_listing_costs(skills, usage, totals.listing_budget, chars_per_token)</code> | Обчислює та зберігає retained ← retained_listing_costs(skills, usage, totals.listing_budget, chars_per_token) |
| 1646 | <code>render</code> | <code>        out.append(bold("  Heaviest requested listings") + dim("  (requested / estimated retained)"))</code> | Виконує виклик out.append: out.append(bold('  Heaviest requested listings') + dim('  (requested / estimated retained)')) |
| 1647 | <code>render</code> | <code>        for skill in ranked:</code> | Ітерує ranked і зв’язує кожен елемент із skill |
| 1648 | <code>render</code> | <code>            fired = ""</code> | Обчислює та зберігає fired ← '' |
| 1649 | <code>render</code> | <code>            if usage is not None:</code> | Умовна гілка: usage is not None; відповідний block виконується тільки коли умова true. |
| 1650 | <code>render</code> | <code>                count = resolve_usage(skill, usage, skills)</code> | Обчислює та зберігає count ← resolve_usage(skill, usage, skills) |
| 1651 | <code>render</code> | <code>                fired = dim("  no observed calls") if count == 0 else dim("  {}x".format(count))</code> | Обчислює та зберігає fired ← dim('  no observed calls') if count == 0 else dim('  {}x'.format(count)) |
| 1652 | <code>render</code> | <code>            out.append("    {:&gt;5} / {:&gt;5} tok  /{}{}".format(</code> | Виконує виклик out.append: out.append('    {:&gt;5} / {:&gt;5} tok  /{}{}'.format(listing_tokens(skill, chars_per_token), retained.get(id(skill), 0), _display_text(skill.command), fired)) |
| 1653 | <code>render</code> | <code>                listing_tokens(skill, chars_per_token), retained.get(id(skill), 0), _display_text(skill.command), fired))</code> | Продовження інструкції 1652: Виконує виклик out.append: out.append('    {:&gt;5} / {:&gt;5} tok  /{}{}'.format(listing_tokens(skill, chars_per_token), retained.get(id(skill), 0), _display_text(skill.command), fired)) |
| 1654 | <code>render</code> | <code>        out.append("")</code> | Виконує виклик out.append: out.append('') |
| 1655 | <code>render</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1656 | <code>render</code> | <code>    if findings:</code> | Умовна гілка: findings; відповідний block виконується тільки коли умова true. |
| 1657 | <code>render</code> | <code>        out.append(bold("  Findings"))</code> | Виконує виклик out.append: out.append(bold('  Findings')) |
| 1658 | <code>render</code> | <code>        current = None</code> | Обчислює та зберігає current ← None |
| 1659 | <code>render</code> | <code>        shown: Dict[str, int] = {}</code> | Типізує shown як Dict[str, int]; initial value {} |
| 1660 | <code>render</code> | <code>        hidden: Dict[str, int] = {}</code> | Типізує hidden як Dict[str, int]; initial value {} |
| 1661 | <code>render</code> | <code>        for finding in findings:</code> | Ітерує findings і зв’язує кожен елемент із finding |
| 1662 | <code>render</code> | <code>            if finding.severity != current:</code> | Умовна гілка: finding.severity != current; відповідний block виконується тільки коли умова true. |
| 1663 | <code>render</code> | <code>                current = finding.severity</code> | Обчислює та зберігає current ← finding.severity |
| 1664 | <code>render</code> | <code>                out.append("")</code> | Виконує виклик out.append: out.append('') |
| 1665 | <code>render</code> | <code>                out.append("  " + _paint(current.upper(), current, color))</code> | Виконує виклик out.append: out.append('  ' + _paint(current.upper(), current, color)) |
| 1666 | <code>render</code> | <code>            count = shown.get(finding.rule, 0)</code> | Обчислює та зберігає count ← shown.get(finding.rule, 0) |
| 1667 | <code>render</code> | <code>            if per_rule_limit and count &gt;= per_rule_limit:</code> | Умовна гілка: per_rule_limit and count &gt;= per_rule_limit; відповідний block виконується тільки коли умова true. |
| 1668 | <code>render</code> | <code>                hidden[finding.rule] = hidden.get(finding.rule, 0) + 1</code> | Обчислює та зберігає hidden[finding.rule] ← hidden.get(finding.rule, 0) + 1 |
| 1669 | <code>render</code> | <code>                continue</code> | Пропускає решту цієї ітерації; переходить до наступного елемента. |
| 1670 | <code>render</code> | <code>            shown[finding.rule] = count + 1</code> | Обчислює та зберігає shown[finding.rule] ← count + 1 |
| 1671 | <code>render</code> | <code>            out.append("    {} /{}".format(</code> | Виконує виклик out.append: out.append('    {} /{}'.format(_paint(finding.rule, finding.severity, color), _display_text(finding.command))) |
| 1672 | <code>render</code> | <code>                _paint(finding.rule, finding.severity, color), _display_text(finding.command)))</code> | Продовження інструкції 1671: Виконує виклик out.append: out.append('    {} /{}'.format(_paint(finding.rule, finding.severity, color), _display_text(finding.command))) |
| 1673 | <code>render</code> | <code>            out.append("      {}".format(_display_text(finding.message)))</code> | Виконує виклик out.append: out.append('      {}'.format(_display_text(finding.message))) |
| 1674 | <code>render</code> | <code>            out.append("      {}".format(dim("fix: " + _display_text(finding.fix))))</code> | Виконує виклик out.append: out.append('      {}'.format(dim('fix: ' + _display_text(finding.fix)))) |
| 1675 | <code>render</code> | <code>        for rule in sorted(hidden):</code> | Ітерує sorted(hidden) і зв’язує кожен елемент із rule |
| 1676 | <code>render</code> | <code>            out.append("    {}  {}".format(</code> | Виконує виклик out.append: out.append('    {}  {}'.format(_paint(rule, 'info', color), dim('... and {} more (--full to show every one)'.format(hidden[rule])))) |
| 1677 | <code>render</code> | <code>                _paint(rule, "info", color),</code> | Продовження інструкції 1676: Виконує виклик out.append: out.append('    {}  {}'.format(_paint(rule, 'info', color), dim('... and {} more (--full to show every one)'.format(hidden[rule])))) |
| 1678 | <code>render</code> | <code>                dim("... and {} more (--full to show every one)".format(hidden[rule]))))</code> | Продовження інструкції 1676: Виконує виклик out.append: out.append('    {}  {}'.format(_paint(rule, 'info', color), dim('... and {} more (--full to show every one)'.format(hidden[rule])))) |
| 1679 | <code>render</code> | <code>        out.append("")</code> | Виконує виклик out.append: out.append('') |
| 1680 | <code>render</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1681 | <code>render</code> | <code>    verdict = "{} error(s), {} warning(s)".format(errors, warns)</code> | Обчислює та зберігає verdict ← '{} error(s), {} warning(s)'.format(errors, warns) |
| 1682 | <code>render</code> | <code>    if name_only:</code> | Умовна гілка: name_only; відповідний block виконується тільки коли умова true. |
| 1683 | <code>render</code> | <code>        verdict += ", {} predicted name-only".format(name_only)</code> | Оновлює накопичене значення: verdict += ', {} predicted name-only'.format(name_only) |
| 1684 | <code>render</code> | <code>    if usage is not None:</code> | Умовна гілка: usage is not None; відповідний block виконується тільки коли умова true. |
| 1685 | <code>render</code> | <code>        verdict += ", {} skill(s) with no observed calls".format(dead)</code> | Оновлює накопичене значення: verdict += ', {} skill(s) with no observed calls'.format(dead) |
| 1686 | <code>render</code> | <code>    out.append(bold("  " + verdict))</code> | Виконує виклик out.append: out.append(bold('  ' + verdict)) |
| 1687 | <code>render</code> | <code>    out.append(dim("  Estimates use characters per token; this does not inspect a live session."))</code> | Виконує виклик out.append: out.append(dim('  Estimates use characters per token; this does not inspect a live session.')) |
| 1688 | <code>render</code> | <code>    out.append("")</code> | Виконує виклик out.append: out.append('') |
| 1689 | <code>render</code> | <code>    return "\n".join(out)</code> | Завершує поточну функцію та повертає '\n'.join(out) |
| 1690 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1691 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1692 | <code>to_json</code> | <code>def to_json(</code> | Оголошення функції `to_json` та її аргументів; детальний контракт розібраний вище. |
| 1693 | <code>to_json</code> | <code>    skills: Sequence[Skill],</code> | Оголошення функції `to_json` та її аргументів; детальний контракт розібраний вище. |
| 1694 | <code>to_json</code> | <code>    findings: Sequence[Finding],</code> | Оголошення функції `to_json` та її аргументів; детальний контракт розібраний вище. |
| 1695 | <code>to_json</code> | <code>    totals: Budget,</code> | Оголошення функції `to_json` та її аргументів; детальний контракт розібраний вище. |
| 1696 | <code>to_json</code> | <code>    usage: Optional[Dict[str, int]],</code> | Оголошення функції `to_json` та її аргументів; детальний контракт розібраний вище. |
| 1697 | <code>to_json</code> | <code>    chars_per_token: float,</code> | Оголошення функції `to_json` та її аргументів; детальний контракт розібраний вище. |
| 1698 | <code>to_json</code> | <code>) -&gt; str:</code> | Оголошення функції `to_json` та її аргументів; детальний контракт розібраний вище. |
| 1699 | <code>to_json</code> | <code>    retained = retained_listing_costs(skills, usage, totals.listing_budget, chars_per_token)</code> | Обчислює та зберігає retained ← retained_listing_costs(skills, usage, totals.listing_budget, chars_per_token) |
| 1700 | <code>to_json</code> | <code>    payload = {</code> | Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1701 | <code>to_json</code> | <code>        "schema_version": 1,</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1702 | <code>to_json</code> | <code>        "version": __version__,</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1703 | <code>to_json</code> | <code>        "model": {</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1704 | <code>to_json</code> | <code>            "harness": "claude-code",</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1705 | <code>to_json</code> | <code>            "estimated": True,</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1706 | <code>to_json</code> | <code>            "chars_per_token": chars_per_token,</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1707 | <code>to_json</code> | <code>            "listing_char_cap": LISTING_CHAR_CAP,</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1708 | <code>to_json</code> | <code>            "usage_available": usage is not None,</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1709 | <code>to_json</code> | <code>        },</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1710 | <code>to_json</code> | <code>        "budget": {</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1711 | <code>to_json</code> | <code>            "skills": totals.skills,</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1712 | <code>to_json</code> | <code>            "always_on_tokens": totals.always_on_tokens,</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1713 | <code>to_json</code> | <code>            "requested_tokens": totals.requested_tokens,</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1714 | <code>to_json</code> | <code>            "name_tokens": totals.name_tokens,</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1715 | <code>to_json</code> | <code>            "desc_tokens": totals.desc_tokens,</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1716 | <code>to_json</code> | <code>            "retained_desc_tokens": totals.retained_desc_tokens,</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1717 | <code>to_json</code> | <code>            "listing_budget": totals.listing_budget,</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1718 | <code>to_json</code> | <code>            "budget_percent": round(totals.budget_percent, 2),</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1719 | <code>to_json</code> | <code>            "overflows": totals.overflows,</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1720 | <code>to_json</code> | <code>            "commands": totals.commands,</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1721 | <code>to_json</code> | <code>            "hidden": totals.hidden,</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1722 | <code>to_json</code> | <code>            "body_tokens": totals.body_tokens,</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1723 | <code>to_json</code> | <code>            "bundle_bytes": totals.bundle_bytes,</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1724 | <code>to_json</code> | <code>            "context_window": totals.context_window,</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1725 | <code>to_json</code> | <code>            "context_percent": round(totals.context_percent, 2),</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1726 | <code>to_json</code> | <code>        },</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1727 | <code>to_json</code> | <code>        "skills": [</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1728 | <code>to_json</code> | <code>            {</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1729 | <code>to_json</code> | <code>                "command": s.command,</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1730 | <code>to_json</code> | <code>                "kind": s.kind,</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1731 | <code>to_json</code> | <code>                "in_listing": s.in_listing,</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1732 | <code>to_json</code> | <code>                "override": s.override,</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1733 | <code>to_json</code> | <code>                "path": str(s.path),</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1734 | <code>to_json</code> | <code>                "origin": s.origin,</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1735 | <code>to_json</code> | <code>                "plugin": s.plugin,</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1736 | <code>to_json</code> | <code>                "listing_tokens": listing_tokens(s, chars_per_token),</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1737 | <code>to_json</code> | <code>                "retained_listing_tokens": retained.get(id(s), 0),</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1738 | <code>to_json</code> | <code>                "body_tokens": estimate_tokens(s.body, chars_per_token),</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1739 | <code>to_json</code> | <code>                "body_lines": s.body_lines,</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1740 | <code>to_json</code> | <code>                "invocations": resolve_usage(s, usage, skills) if usage is not None else None,</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1741 | <code>to_json</code> | <code>            }</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1742 | <code>to_json</code> | <code>            for s in skills</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1743 | <code>to_json</code> | <code>        ],</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1744 | <code>to_json</code> | <code>        "findings": [</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1745 | <code>to_json</code> | <code>            {</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1746 | <code>to_json</code> | <code>                "rule": f.rule, "severity": f.severity, "command": f.command,</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1747 | <code>to_json</code> | <code>                "path": f.path, "message": f.message, "fix": f.fix,</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1748 | <code>to_json</code> | <code>            }</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1749 | <code>to_json</code> | <code>            for f in findings</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1750 | <code>to_json</code> | <code>        ],</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1751 | <code>to_json</code> | <code>    }</code> | Продовження інструкції 1700: Обчислює та зберігає payload ← {'schema_version': 1, 'version': __version__, 'model': {'harness': 'claude-code', 'estimated': True, 'chars_per_token': chars_per_token, 'listing_char_cap': LISTING_CHAR_CAP, 'usage_available': usage… |
| 1752 | <code>to_json</code> | <code>    # Escaped JSON remains valid Unicode after decoding and is safe through</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 1753 | <code>to_json</code> | <code>    # Windows pipes whose active encoding cannot represent the audited path.</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 1754 | <code>to_json</code> | <code>    return json.dumps(payload, indent=2, ensure_ascii=True, allow_nan=False)</code> | Завершує поточну функцію та повертає json.dumps(payload, indent=2, ensure_ascii=True, allow_nan=False) |
| 1755 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1756 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1757 | <code>&lt;module&gt;</code> | <code># --- SVG visual -----------------------------------------------------------</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 1758 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1759 | <code>_svg_escape</code> | <code>def _svg_escape(text: str) -&gt; str:</code> | Оголошення функції `_svg_escape` та її аргументів; детальний контракт розібраний вище. |
| 1760 | <code>_svg_escape</code> | <code>    return (_display_text(text).replace("&amp;", "&amp;amp;").replace("&lt;", "&amp;lt;").replace("&gt;", "&amp;gt;"))</code> | Завершує поточну функцію та повертає _display_text(text).replace('&amp;', '&amp;amp;').replace('&lt;', '&amp;lt;').replace('&gt;', '&amp;gt;') |
| 1761 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1762 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1763 | <code>to_svg</code> | <code>def to_svg(</code> | Оголошення функції `to_svg` та її аргументів; детальний контракт розібраний вище. |
| 1764 | <code>to_svg</code> | <code>    skills: Sequence[Skill],</code> | Оголошення функції `to_svg` та її аргументів; детальний контракт розібраний вище. |
| 1765 | <code>to_svg</code> | <code>    totals: Budget,</code> | Оголошення функції `to_svg` та її аргументів; детальний контракт розібраний вище. |
| 1766 | <code>to_svg</code> | <code>    usage: Optional[Dict[str, int]],</code> | Оголошення функції `to_svg` та її аргументів; детальний контракт розібраний вище. |
| 1767 | <code>to_svg</code> | <code>    chars_per_token: float,</code> | Оголошення функції `to_svg` та її аргументів; детальний контракт розібраний вище. |
| 1768 | <code>to_svg</code> | <code>    top: int = 10,</code> | Оголошення функції `to_svg` та її аргументів; детальний контракт розібраний вище. |
| 1769 | <code>to_svg</code> | <code>) -&gt; str:</code> | Оголошення функції `to_svg` та її аргументів; детальний контракт розібраний вище. |
| 1770 | <code>to_svg</code> | <code>    """A self-contained, theme-aware budget chart.</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1771 | <code>to_svg</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1772 | <code>to_svg</code> | <code>    One bar for the listing (filled to the budget line, overflow hatched) and a</code> | Продовження інструкції 1770: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1773 | <code>to_svg</code> | <code>    ranked bar per heaviest skill. No dependencies: the ranking is the point,</code> | Продовження інструкції 1770: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1774 | <code>to_svg</code> | <code>    the numbers are the 4-char-per-token estimate the rest of the tool uses.</code> | Продовження інструкції 1770: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1775 | <code>to_svg</code> | <code>    """</code> | Продовження інструкції 1770: Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1776 | <code>to_svg</code> | <code>    ranked = sorted(_listed(skills), key=lambda s: listing_tokens(s, chars_per_token), reverse=True)[:top]</code> | Обчислює та зберігає ranked ← sorted(_listed(skills), key=lambda s: listing_tokens(s, chars_per_token), reverse=True)[:top] |
| 1777 | <code>to_svg</code> | <code>    row_h, pad_top, left, width = 30, 150, 250, 640</code> | Обчислює та зберігає (row_h, pad_top, left, width) ← (30, 150, 250, 640) |
| 1778 | <code>to_svg</code> | <code>    height = pad_top + row_h * (len(ranked) + 1) + 40</code> | Обчислює та зберігає height ← pad_top + row_h * (len(ranked) + 1) + 40 |
| 1779 | <code>to_svg</code> | <code>    budget_line = totals.listing_budget or 1</code> | Обчислює та зберігає budget_line ← totals.listing_budget or 1 |
| 1780 | <code>to_svg</code> | <code>    bar_scale = width / max(budget_line, totals.requested_tokens, 1)</code> | Обчислює та зберігає bar_scale ← width / max(budget_line, totals.requested_tokens, 1) |
| 1781 | <code>to_svg</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1782 | <code>to_svg.bar_row</code> | <code>    def bar_row(y, label, tokens, sub, fill):</code> | Оголошення функції `bar_row` та її аргументів; детальний контракт розібраний вище. |
| 1783 | <code>to_svg.bar_row</code> | <code>        lx = left + min(tokens * bar_scale, width)</code> | Обчислює та зберігає lx ← left + min(tokens * bar_scale, width) |
| 1784 | <code>to_svg.bar_row</code> | <code>        note = _svg_escape("{:,} tok  {}".format(tokens, sub))</code> | Обчислює та зберігає note ← _svg_escape('{:,} tok  {}'.format(tokens, sub)) |
| 1785 | <code>to_svg.bar_row</code> | <code>        return (</code> | Завершує поточну функцію та повертає '&lt;text x="{lx0}" y="{ty}" class="lbl" text-anchor="end"&gt;{lab}&lt;/text&gt;&lt;rect x="{x}" y="{by}" width="{w:.1f}" height="16" rx="3" fill="{fill}"/&gt;&lt;text x="{tx:.1f}" y="{ty}" class="val"&gt;{note}&lt;/text&gt;'.for… |
| 1786 | <code>to_svg.bar_row</code> | <code>            '&lt;text x="{lx0}" y="{ty}" class="lbl" text-anchor="end"&gt;{lab}&lt;/text&gt;'</code> | Продовження інструкції 1785: Завершує поточну функцію та повертає '&lt;text x="{lx0}" y="{ty}" class="lbl" text-anchor="end"&gt;{lab}&lt;/text&gt;&lt;rect x="{x}" y="{by}" width="{w:.1f}" height="16" rx="3" fill="{fill}"/&gt;&lt;text x="{tx:.1f}" y="{ty}" class="val"&gt;{note}&lt;/text&gt;'.for… |
| 1787 | <code>to_svg.bar_row</code> | <code>            '&lt;rect x="{x}" y="{by}" width="{w:.1f}" height="16" rx="3" fill="{fill}"/&gt;'</code> | Продовження інструкції 1785: Завершує поточну функцію та повертає '&lt;text x="{lx0}" y="{ty}" class="lbl" text-anchor="end"&gt;{lab}&lt;/text&gt;&lt;rect x="{x}" y="{by}" width="{w:.1f}" height="16" rx="3" fill="{fill}"/&gt;&lt;text x="{tx:.1f}" y="{ty}" class="val"&gt;{note}&lt;/text&gt;'.for… |
| 1788 | <code>to_svg.bar_row</code> | <code>            '&lt;text x="{tx:.1f}" y="{ty}" class="val"&gt;{note}&lt;/text&gt;'</code> | Продовження інструкції 1785: Завершує поточну функцію та повертає '&lt;text x="{lx0}" y="{ty}" class="lbl" text-anchor="end"&gt;{lab}&lt;/text&gt;&lt;rect x="{x}" y="{by}" width="{w:.1f}" height="16" rx="3" fill="{fill}"/&gt;&lt;text x="{tx:.1f}" y="{ty}" class="val"&gt;{note}&lt;/text&gt;'.for… |
| 1789 | <code>to_svg.bar_row</code> | <code>        ).format(lx0=left - 12, ty=y + 13, lab=_svg_escape(label), x=left, by=y,</code> | Продовження інструкції 1785: Завершує поточну функцію та повертає '&lt;text x="{lx0}" y="{ty}" class="lbl" text-anchor="end"&gt;{lab}&lt;/text&gt;&lt;rect x="{x}" y="{by}" width="{w:.1f}" height="16" rx="3" fill="{fill}"/&gt;&lt;text x="{tx:.1f}" y="{ty}" class="val"&gt;{note}&lt;/text&gt;'.for… |
| 1790 | <code>to_svg.bar_row</code> | <code>                 w=min(tokens * bar_scale, width), fill=fill, tx=lx + 8, note=note)</code> | Продовження інструкції 1785: Завершує поточну функцію та повертає '&lt;text x="{lx0}" y="{ty}" class="lbl" text-anchor="end"&gt;{lab}&lt;/text&gt;&lt;rect x="{x}" y="{by}" width="{w:.1f}" height="16" rx="3" fill="{fill}"/&gt;&lt;text x="{tx:.1f}" y="{ty}" class="val"&gt;{note}&lt;/text&gt;'.for… |
| 1791 | <code>to_svg</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1792 | <code>to_svg</code> | <code>    parts = [</code> | Обчислює та зберігає parts ← ['&lt;svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="ui-monospace,Menlo,Consolas,monospace"&gt;'.format(w=left + width + 240, h=height), '&lt;style&gt;:root{--… |
| 1793 | <code>to_svg</code> | <code>        '&lt;svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '</code> | Продовження інструкції 1792: Обчислює та зберігає parts ← ['&lt;svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="ui-monospace,Menlo,Consolas,monospace"&gt;'.format(w=left + width + 240, h=height), '&lt;style&gt;:root{--… |
| 1794 | <code>to_svg</code> | <code>        'viewBox="0 0 {w} {h}" '</code> | Продовження інструкції 1792: Обчислює та зберігає parts ← ['&lt;svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="ui-monospace,Menlo,Consolas,monospace"&gt;'.format(w=left + width + 240, h=height), '&lt;style&gt;:root{--… |
| 1795 | <code>to_svg</code> | <code>        'font-family="ui-monospace,Menlo,Consolas,monospace"&gt;'.format(w=left + width + 240, h=height),</code> | Продовження інструкції 1792: Обчислює та зберігає parts ← ['&lt;svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="ui-monospace,Menlo,Consolas,monospace"&gt;'.format(w=left + width + 240, h=height), '&lt;style&gt;:root{--… |
| 1796 | <code>to_svg</code> | <code>        "&lt;style&gt;"</code> | Продовження інструкції 1792: Обчислює та зберігає parts ← ['&lt;svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="ui-monospace,Menlo,Consolas,monospace"&gt;'.format(w=left + width + 240, h=height), '&lt;style&gt;:root{--… |
| 1797 | <code>to_svg</code> | <code>        ":root{--bg:#ffffff;--fg:#1a1a1a;--mut:#6b7280;--bar:#2563eb;--over:#dc2626;--line:#9ca3af}"</code> | Продовження інструкції 1792: Обчислює та зберігає parts ← ['&lt;svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="ui-monospace,Menlo,Consolas,monospace"&gt;'.format(w=left + width + 240, h=height), '&lt;style&gt;:root{--… |
| 1798 | <code>to_svg</code> | <code>        "@media (prefers-color-scheme:dark){:root{--bg:#0d1117;--fg:#e6edf3;--mut:#8b949e;"</code> | Продовження інструкції 1792: Обчислює та зберігає parts ← ['&lt;svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="ui-monospace,Menlo,Consolas,monospace"&gt;'.format(w=left + width + 240, h=height), '&lt;style&gt;:root{--… |
| 1799 | <code>to_svg</code> | <code>        "--bar:#3b82f6;--over:#f85149;--line:#484f58}}"</code> | Продовження інструкції 1792: Обчислює та зберігає parts ← ['&lt;svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="ui-monospace,Menlo,Consolas,monospace"&gt;'.format(w=left + width + 240, h=height), '&lt;style&gt;:root{--… |
| 1800 | <code>to_svg</code> | <code>        ".bg{fill:var(--bg)}.title{fill:var(--fg);font-size:22px;font-weight:700}"</code> | Продовження інструкції 1792: Обчислює та зберігає parts ← ['&lt;svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="ui-monospace,Menlo,Consolas,monospace"&gt;'.format(w=left + width + 240, h=height), '&lt;style&gt;:root{--… |
| 1801 | <code>to_svg</code> | <code>        ".sub{fill:var(--mut);font-size:13px}.lbl{fill:var(--fg);font-size:12px}"</code> | Продовження інструкції 1792: Обчислює та зберігає parts ← ['&lt;svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="ui-monospace,Menlo,Consolas,monospace"&gt;'.format(w=left + width + 240, h=height), '&lt;style&gt;:root{--… |
| 1802 | <code>to_svg</code> | <code>        ".val{fill:var(--mut);font-size:11px;dominant-baseline:middle}"</code> | Продовження інструкції 1792: Обчислює та зберігає parts ← ['&lt;svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="ui-monospace,Menlo,Consolas,monospace"&gt;'.format(w=left + width + 240, h=height), '&lt;style&gt;:root{--… |
| 1803 | <code>to_svg</code> | <code>        ".hd{fill:var(--fg);font-size:13px;font-weight:600}"</code> | Продовження інструкції 1792: Обчислює та зберігає parts ← ['&lt;svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="ui-monospace,Menlo,Consolas,monospace"&gt;'.format(w=left + width + 240, h=height), '&lt;style&gt;:root{--… |
| 1804 | <code>to_svg</code> | <code>        "&lt;/style&gt;",</code> | Продовження інструкції 1792: Обчислює та зберігає parts ← ['&lt;svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="ui-monospace,Menlo,Consolas,monospace"&gt;'.format(w=left + width + 240, h=height), '&lt;style&gt;:root{--… |
| 1805 | <code>to_svg</code> | <code>        '&lt;rect class="bg" x="0" y="0" width="{w}" height="{h}"/&gt;'.format(w=left + width + 240, h=height),</code> | Продовження інструкції 1792: Обчислює та зберігає parts ← ['&lt;svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="ui-monospace,Menlo,Consolas,monospace"&gt;'.format(w=left + width + 240, h=height), '&lt;style&gt;:root{--… |
| 1806 | <code>to_svg</code> | <code>        '&lt;text x="30" y="42" class="title"&gt;skillrot&lt;/text&gt;',</code> | Продовження інструкції 1792: Обчислює та зберігає parts ← ['&lt;svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="ui-monospace,Menlo,Consolas,monospace"&gt;'.format(w=left + width + 240, h=height), '&lt;style&gt;:root{--… |
| 1807 | <code>to_svg</code> | <code>        '&lt;text x="30" y="68" class="sub"&gt;{}&lt;/text&gt;'.format(_svg_escape(</code> | Продовження інструкції 1792: Обчислює та зберігає parts ← ['&lt;svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="ui-monospace,Menlo,Consolas,monospace"&gt;'.format(w=left + width + 240, h=height), '&lt;style&gt;:root{--… |
| 1808 | <code>to_svg</code> | <code>            "{:,} entries  •  ~{:,} tok retained  •  {:.1f}% of a {:,}-tok window".format(</code> | Продовження інструкції 1792: Обчислює та зберігає parts ← ['&lt;svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="ui-monospace,Menlo,Consolas,monospace"&gt;'.format(w=left + width + 240, h=height), '&lt;style&gt;:root{--… |
| 1809 | <code>to_svg</code> | <code>                totals.skills, totals.always_on_tokens, totals.context_percent, totals.context_window))),</code> | Продовження інструкції 1792: Обчислює та зберігає parts ← ['&lt;svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="ui-monospace,Menlo,Consolas,monospace"&gt;'.format(w=left + width + 240, h=height), '&lt;style&gt;:root{--… |
| 1810 | <code>to_svg</code> | <code>        '&lt;text x="30" y="90" class="sub"&gt;{}&lt;/text&gt;'.format(_svg_escape(</code> | Продовження інструкції 1792: Обчислює та зберігає parts ← ['&lt;svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="ui-monospace,Menlo,Consolas,monospace"&gt;'.format(w=left + width + 240, h=height), '&lt;style&gt;:root{--… |
| 1811 | <code>to_svg</code> | <code>            "listing budget {:,} tok  •  {:.0f}% requested{}".format(</code> | Продовження інструкції 1792: Обчислює та зберігає parts ← ['&lt;svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="ui-monospace,Menlo,Consolas,monospace"&gt;'.format(w=left + width + 240, h=height), '&lt;style&gt;:root{--… |
| 1812 | <code>to_svg</code> | <code>                totals.listing_budget, totals.budget_percent,</code> | Продовження інструкції 1792: Обчислює та зберігає parts ← ['&lt;svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="ui-monospace,Menlo,Consolas,monospace"&gt;'.format(w=left + width + 240, h=height), '&lt;style&gt;:root{--… |
| 1813 | <code>to_svg</code> | <code>                "  •  predicted description drops" if totals.overflows else "  •  estimated to fit"))),</code> | Продовження інструкції 1792: Обчислює та зберігає parts ← ['&lt;svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="ui-monospace,Menlo,Consolas,monospace"&gt;'.format(w=left + width + 240, h=height), '&lt;style&gt;:root{--… |
| 1814 | <code>to_svg</code> | <code>        '&lt;text x="30" y="{y}" class="hd"&gt;Listing&lt;/text&gt;'.format(y=pad_top - 18),</code> | Продовження інструкції 1792: Обчислює та зберігає parts ← ['&lt;svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="ui-monospace,Menlo,Consolas,monospace"&gt;'.format(w=left + width + 240, h=height), '&lt;style&gt;:root{--… |
| 1815 | <code>to_svg</code> | <code>    ]</code> | Продовження інструкції 1792: Обчислює та зберігає parts ← ['&lt;svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="ui-monospace,Menlo,Consolas,monospace"&gt;'.format(w=left + width + 240, h=height), '&lt;style&gt;:root{--… |
| 1816 | <code>to_svg</code> | <code>    over_fill = "var(--over)" if totals.overflows else "var(--bar)"</code> | Обчислює та зберігає over_fill ← 'var(--over)' if totals.overflows else 'var(--bar)' |
| 1817 | <code>to_svg</code> | <code>    parts.append(bar_row(pad_top, "requested", totals.requested_tokens,</code> | Виконує виклик parts.append: parts.append(bar_row(pad_top, 'requested', totals.requested_tokens, 'names + descriptions', over_fill)) |
| 1818 | <code>to_svg</code> | <code>                         "names + descriptions", over_fill))</code> | Продовження інструкції 1817: Виконує виклик parts.append: parts.append(bar_row(pad_top, 'requested', totals.requested_tokens, 'names + descriptions', over_fill)) |
| 1819 | <code>to_svg</code> | <code>    # budget line</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 1820 | <code>to_svg</code> | <code>    bx = left + min(budget_line * bar_scale, width)</code> | Обчислює та зберігає bx ← left + min(budget_line * bar_scale, width) |
| 1821 | <code>to_svg</code> | <code>    parts.append(</code> | Виконує виклик parts.append: parts.append('&lt;line x1="{bx:.1f}" y1="{y0}" x2="{bx:.1f}" y2="{y1}" stroke="var(--line)" stroke-dasharray="4 3"/&gt;&lt;text x="{bx:.1f}" y="{yt}" class="val" text-anchor="middle"&gt;budget&lt;/text&gt;'.format(bx=… |
| 1822 | <code>to_svg</code> | <code>        '&lt;line x1="{bx:.1f}" y1="{y0}" x2="{bx:.1f}" y2="{y1}" stroke="var(--line)" '</code> | Продовження інструкції 1821: Виконує виклик parts.append: parts.append('&lt;line x1="{bx:.1f}" y1="{y0}" x2="{bx:.1f}" y2="{y1}" stroke="var(--line)" stroke-dasharray="4 3"/&gt;&lt;text x="{bx:.1f}" y="{yt}" class="val" text-anchor="middle"&gt;budget&lt;/text&gt;'.format(bx=… |
| 1823 | <code>to_svg</code> | <code>        'stroke-dasharray="4 3"/&gt;'</code> | Продовження інструкції 1821: Виконує виклик parts.append: parts.append('&lt;line x1="{bx:.1f}" y1="{y0}" x2="{bx:.1f}" y2="{y1}" stroke="var(--line)" stroke-dasharray="4 3"/&gt;&lt;text x="{bx:.1f}" y="{yt}" class="val" text-anchor="middle"&gt;budget&lt;/text&gt;'.format(bx=… |
| 1824 | <code>to_svg</code> | <code>        '&lt;text x="{bx:.1f}" y="{yt}" class="val" text-anchor="middle"&gt;budget&lt;/text&gt;'.format(</code> | Продовження інструкції 1821: Виконує виклик parts.append: parts.append('&lt;line x1="{bx:.1f}" y1="{y0}" x2="{bx:.1f}" y2="{y1}" stroke="var(--line)" stroke-dasharray="4 3"/&gt;&lt;text x="{bx:.1f}" y="{yt}" class="val" text-anchor="middle"&gt;budget&lt;/text&gt;'.format(bx=… |
| 1825 | <code>to_svg</code> | <code>            bx=bx, y0=pad_top - 8, y1=pad_top + 24, yt=pad_top - 12))</code> | Продовження інструкції 1821: Виконує виклик parts.append: parts.append('&lt;line x1="{bx:.1f}" y1="{y0}" x2="{bx:.1f}" y2="{y1}" stroke="var(--line)" stroke-dasharray="4 3"/&gt;&lt;text x="{bx:.1f}" y="{yt}" class="val" text-anchor="middle"&gt;budget&lt;/text&gt;'.format(bx=… |
| 1826 | <code>to_svg</code> | <code>    parts.append('&lt;text x="30" y="{y}" class="hd"&gt;Heaviest requested listings&lt;/text&gt;'.format(</code> | Виконує виклик parts.append: parts.append('&lt;text x="30" y="{y}" class="hd"&gt;Heaviest requested listings&lt;/text&gt;'.format(y=pad_top + row_h + 12)) |
| 1827 | <code>to_svg</code> | <code>        y=pad_top + row_h + 12))</code> | Продовження інструкції 1826: Виконує виклик parts.append: parts.append('&lt;text x="30" y="{y}" class="hd"&gt;Heaviest requested listings&lt;/text&gt;'.format(y=pad_top + row_h + 12)) |
| 1828 | <code>to_svg</code> | <code>    for idx, s in enumerate(ranked):</code> | Ітерує enumerate(ranked) і зв’язує кожен елемент із (idx, s) |
| 1829 | <code>to_svg</code> | <code>        y = pad_top + row_h * (idx + 1) + 22</code> | Обчислює та зберігає y ← pad_top + row_h * (idx + 1) + 22 |
| 1830 | <code>to_svg</code> | <code>        sub = ""</code> | Обчислює та зберігає sub ← '' |
| 1831 | <code>to_svg</code> | <code>        if usage is not None:</code> | Умовна гілка: usage is not None; відповідний block виконується тільки коли умова true. |
| 1832 | <code>to_svg</code> | <code>            c = resolve_usage(s, usage, skills)</code> | Обчислює та зберігає c ← resolve_usage(s, usage, skills) |
| 1833 | <code>to_svg</code> | <code>            sub = "no observed calls" if c == 0 else "{}x".format(c)</code> | Обчислює та зберігає sub ← 'no observed calls' if c == 0 else '{}x'.format(c) |
| 1834 | <code>to_svg</code> | <code>        parts.append(bar_row(y, _display_text(s.command)[:30], listing_tokens(s, chars_per_token), sub, "var(--bar)"))</code> | Виконує виклик parts.append: parts.append(bar_row(y, _display_text(s.command)[:30], listing_tokens(s, chars_per_token), sub, 'var(--bar)')) |
| 1835 | <code>to_svg</code> | <code>    parts.append("&lt;/svg&gt;")</code> | Виконує виклик parts.append: parts.append('&lt;/svg&gt;') |
| 1836 | <code>to_svg</code> | <code>    return "".join(parts)</code> | Завершує поточну функцію та повертає ''.join(parts) |
| 1837 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1838 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1839 | <code>&lt;module&gt;</code> | <code># --- CLI ------------------------------------------------------------------</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 1840 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1841 | <code>_ReportArgumentParser</code> | <code>class _ReportArgumentParser(argparse.ArgumentParser):</code> | Оголошення класу `_ReportArgumentParser` та базових класів; модель даних/поведінка розібрана вище. |
| 1842 | <code>_ReportArgumentParser._print_message</code> | <code>    def _print_message(self, message, file=None):</code> | Оголошення функції `_print_message` та її аргументів; детальний контракт розібраний вище. |
| 1843 | <code>_ReportArgumentParser._print_message</code> | <code>        if message:</code> | Умовна гілка: message; відповідний block виконується тільки коли умова true. |
| 1844 | <code>_ReportArgumentParser._print_message</code> | <code>            _write_stream(file if file is not None else sys.stderr,</code> | Виконує виклик _write_stream: _write_stream(file if file is not None else sys.stderr, _display_text(message, preserve_layout=True)) |
| 1845 | <code>_ReportArgumentParser._print_message</code> | <code>                          _display_text(message, preserve_layout=True))</code> | Продовження інструкції 1844: Виконує виклик _write_stream: _write_stream(file if file is not None else sys.stderr, _display_text(message, preserve_layout=True)) |
| 1846 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1847 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1848 | <code>build_parser</code> | <code>def build_parser() -&gt; argparse.ArgumentParser:</code> | Оголошення функції `build_parser` та її аргументів; детальний контракт розібраний вище. |
| 1849 | <code>build_parser</code> | <code>    parser = _ReportArgumentParser(</code> | Обчислює та зберігає parser ← _ReportArgumentParser(prog='skillrot', description="Find the dead weight in your agent's skill library.") |
| 1850 | <code>build_parser</code> | <code>        prog="skillrot",</code> | Продовження інструкції 1849: Обчислює та зберігає parser ← _ReportArgumentParser(prog='skillrot', description="Find the dead weight in your agent's skill library.") |
| 1851 | <code>build_parser</code> | <code>        description="Find the dead weight in your agent's skill library.",</code> | Продовження інструкції 1849: Обчислює та зберігає parser ← _ReportArgumentParser(prog='skillrot', description="Find the dead weight in your agent's skill library.") |
| 1852 | <code>build_parser</code> | <code>    )</code> | Продовження інструкції 1849: Обчислює та зберігає parser ← _ReportArgumentParser(prog='skillrot', description="Find the dead weight in your agent's skill library.") |
| 1853 | <code>build_parser</code> | <code>    parser.add_argument(</code> | Виконує виклик parser.add_argument: parser.add_argument('paths', nargs='*', type=Path, help='Directories or SKILL.md files to scan. Default: installed Claude Code skills.') |
| 1854 | <code>build_parser</code> | <code>        "paths", nargs="*", type=Path,</code> | Продовження інструкції 1853: Виконує виклик parser.add_argument: parser.add_argument('paths', nargs='*', type=Path, help='Directories or SKILL.md files to scan. Default: installed Claude Code skills.') |
| 1855 | <code>build_parser</code> | <code>        help="Directories or SKILL.md files to scan. Default: installed Claude Code skills.")</code> | Продовження інструкції 1853: Виконує виклик parser.add_argument: parser.add_argument('paths', nargs='*', type=Path, help='Directories or SKILL.md files to scan. Default: installed Claude Code skills.') |
| 1856 | <code>build_parser</code> | <code>    parser.add_argument("--json", action="store_true", help="Machine-readable output.")</code> | Виконує виклик parser.add_argument: parser.add_argument('--json', action='store_true', help='Machine-readable output.') |
| 1857 | <code>build_parser</code> | <code>    parser.add_argument(</code> | Виконує виклик parser.add_argument: parser.add_argument('--portable', action='store_true', help='Check supported frontmatter against the six-field Agent Skills spec.') |
| 1858 | <code>build_parser</code> | <code>        "--portable", action="store_true",</code> | Продовження інструкції 1857: Виконує виклик parser.add_argument: parser.add_argument('--portable', action='store_true', help='Check supported frontmatter against the six-field Agent Skills spec.') |
| 1859 | <code>build_parser</code> | <code>        help="Check supported frontmatter against the six-field Agent Skills spec.")</code> | Продовження інструкції 1857: Виконує виклик parser.add_argument: parser.add_argument('--portable', action='store_true', help='Check supported frontmatter against the six-field Agent Skills spec.') |
| 1860 | <code>build_parser</code> | <code>    parser.add_argument(</code> | Виконує виклик parser.add_argument: parser.add_argument('--no-usage', action='store_true', help='Skip local transcript invocation evidence.') |
| 1861 | <code>build_parser</code> | <code>        "--no-usage", action="store_true",</code> | Продовження інструкції 1860: Виконує виклик parser.add_argument: parser.add_argument('--no-usage', action='store_true', help='Skip local transcript invocation evidence.') |
| 1862 | <code>build_parser</code> | <code>        help="Skip local transcript invocation evidence.")</code> | Продовження інструкції 1860: Виконує виклик parser.add_argument: parser.add_argument('--no-usage', action='store_true', help='Skip local transcript invocation evidence.') |
| 1863 | <code>build_parser</code> | <code>    parser.add_argument(</code> | Виконує виклик parser.add_argument: parser.add_argument('--transcripts', type=Path, default=None, help='Transcript directory. Default: ~/.claude/projects') |
| 1864 | <code>build_parser</code> | <code>        "--transcripts", type=Path, default=None,</code> | Продовження інструкції 1863: Виконує виклик parser.add_argument: parser.add_argument('--transcripts', type=Path, default=None, help='Transcript directory. Default: ~/.claude/projects') |
| 1865 | <code>build_parser</code> | <code>        help="Transcript directory. Default: ~/.claude/projects")</code> | Продовження інструкції 1863: Виконує виклик parser.add_argument: parser.add_argument('--transcripts', type=Path, default=None, help='Transcript directory. Default: ~/.claude/projects') |
| 1866 | <code>build_parser</code> | <code>    parser.add_argument("--top", type=int, default=10, help="How many heaviest skills to list.")</code> | Виконує виклик parser.add_argument: parser.add_argument('--top', type=int, default=10, help='How many heaviest skills to list.') |
| 1867 | <code>build_parser</code> | <code>    parser.add_argument("--context-window", type=int, default=DEFAULT_CONTEXT_WINDOW)</code> | Виконує виклик parser.add_argument: parser.add_argument('--context-window', type=int, default=DEFAULT_CONTEXT_WINDOW) |
| 1868 | <code>build_parser</code> | <code>    parser.add_argument(</code> | Виконує виклик parser.add_argument: parser.add_argument('--body-lines', type=int, default=DEFAULT_BODY_LINE_BUDGET, help='Flag skill bodies longer than this.') |
| 1869 | <code>build_parser</code> | <code>        "--body-lines", type=int, default=DEFAULT_BODY_LINE_BUDGET,</code> | Продовження інструкції 1868: Виконує виклик parser.add_argument: parser.add_argument('--body-lines', type=int, default=DEFAULT_BODY_LINE_BUDGET, help='Flag skill bodies longer than this.') |
| 1870 | <code>build_parser</code> | <code>        help="Flag skill bodies longer than this.")</code> | Продовження інструкції 1868: Виконує виклик parser.add_argument: parser.add_argument('--body-lines', type=int, default=DEFAULT_BODY_LINE_BUDGET, help='Flag skill bodies longer than this.') |
| 1871 | <code>build_parser</code> | <code>    parser.add_argument(</code> | Виконує виклик parser.add_argument: parser.add_argument('--similarity', type=float, default=DEFAULT_SIMILARITY, help='Description overlap that counts as a collision (0-1).') |
| 1872 | <code>build_parser</code> | <code>        "--similarity", type=float, default=DEFAULT_SIMILARITY,</code> | Продовження інструкції 1871: Виконує виклик parser.add_argument: parser.add_argument('--similarity', type=float, default=DEFAULT_SIMILARITY, help='Description overlap that counts as a collision (0-1).') |
| 1873 | <code>build_parser</code> | <code>        help="Description overlap that counts as a collision (0-1).")</code> | Продовження інструкції 1871: Виконує виклик parser.add_argument: parser.add_argument('--similarity', type=float, default=DEFAULT_SIMILARITY, help='Description overlap that counts as a collision (0-1).') |
| 1874 | <code>build_parser</code> | <code>    parser.add_argument(</code> | Виконує виклик parser.add_argument: parser.add_argument('--chars-per-token', type=float, default=DEFAULT_CHARS_PER_TOKEN, help='Token estimate divisor (0.1-100).') |
| 1875 | <code>build_parser</code> | <code>        "--chars-per-token", type=float, default=DEFAULT_CHARS_PER_TOKEN,</code> | Продовження інструкції 1874: Виконує виклик parser.add_argument: parser.add_argument('--chars-per-token', type=float, default=DEFAULT_CHARS_PER_TOKEN, help='Token estimate divisor (0.1-100).') |
| 1876 | <code>build_parser</code> | <code>        help="Token estimate divisor (0.1-100).")</code> | Продовження інструкції 1874: Виконує виклик parser.add_argument: parser.add_argument('--chars-per-token', type=float, default=DEFAULT_CHARS_PER_TOKEN, help='Token estimate divisor (0.1-100).') |
| 1877 | <code>build_parser</code> | <code>    parser.add_argument(</code> | Виконує виклик parser.add_argument: parser.add_argument('--budget-fraction', type=float, default=None, help="Listing budget as a fraction of the context window. Default: your skillListingBudgetFraction setting, else Claude Code's 0.01.… |
| 1878 | <code>build_parser</code> | <code>        "--budget-fraction", type=float, default=None,</code> | Продовження інструкції 1877: Виконує виклик parser.add_argument: parser.add_argument('--budget-fraction', type=float, default=None, help="Listing budget as a fraction of the context window. Default: your skillListingBudgetFraction setting, else Claude Code's 0.01.… |
| 1879 | <code>build_parser</code> | <code>        help="Listing budget as a fraction of the context window. Default: your "</code> | Продовження інструкції 1877: Виконує виклик parser.add_argument: parser.add_argument('--budget-fraction', type=float, default=None, help="Listing budget as a fraction of the context window. Default: your skillListingBudgetFraction setting, else Claude Code's 0.01.… |
| 1880 | <code>build_parser</code> | <code>             "skillListingBudgetFraction setting, else Claude Code's 0.01.")</code> | Продовження інструкції 1877: Виконує виклик parser.add_argument: parser.add_argument('--budget-fraction', type=float, default=None, help="Listing budget as a fraction of the context window. Default: your skillListingBudgetFraction setting, else Claude Code's 0.01.… |
| 1881 | <code>build_parser</code> | <code>    parser.add_argument(</code> | Виконує виклик parser.add_argument: parser.add_argument('--svg', type=Path, default=None, help='Write a budget chart (SVG) to this path.') |
| 1882 | <code>build_parser</code> | <code>        "--svg", type=Path, default=None,</code> | Продовження інструкції 1881: Виконує виклик parser.add_argument: parser.add_argument('--svg', type=Path, default=None, help='Write a budget chart (SVG) to this path.') |
| 1883 | <code>build_parser</code> | <code>        help="Write a budget chart (SVG) to this path.")</code> | Продовження інструкції 1881: Виконує виклик parser.add_argument: parser.add_argument('--svg', type=Path, default=None, help='Write a budget chart (SVG) to this path.') |
| 1884 | <code>build_parser</code> | <code>    parser.add_argument(</code> | Виконує виклик parser.add_argument: parser.add_argument('--all', action='store_true', help='Scan every SKILL.md instead of manifest-selected files; plugin ownership manifests are still validated. Recursive child directory links are ski… |
| 1885 | <code>build_parser</code> | <code>        "--all", action="store_true",</code> | Продовження інструкції 1884: Виконує виклик parser.add_argument: parser.add_argument('--all', action='store_true', help='Scan every SKILL.md instead of manifest-selected files; plugin ownership manifests are still validated. Recursive child directory links are ski… |
| 1886 | <code>build_parser</code> | <code>        help="Scan every SKILL.md instead of manifest-selected files; plugin ownership "</code> | Продовження інструкції 1884: Виконує виклик parser.add_argument: parser.add_argument('--all', action='store_true', help='Scan every SKILL.md instead of manifest-selected files; plugin ownership manifests are still validated. Recursive child directory links are ski… |
| 1887 | <code>build_parser</code> | <code>             "manifests are still validated. Recursive child directory links are skipped.")</code> | Продовження інструкції 1884: Виконує виклик parser.add_argument: parser.add_argument('--all', action='store_true', help='Scan every SKILL.md instead of manifest-selected files; plugin ownership manifests are still validated. Recursive child directory links are ski… |
| 1888 | <code>build_parser</code> | <code>    parser.add_argument(</code> | Виконує виклик parser.add_argument: parser.add_argument('--fail-on', choices=('never', 'error', 'warn'), default='never', help='Exit non-zero at this severity. Use in CI.') |
| 1889 | <code>build_parser</code> | <code>        "--fail-on", choices=("never", "error", "warn"), default="never",</code> | Продовження інструкції 1888: Виконує виклик parser.add_argument: parser.add_argument('--fail-on', choices=('never', 'error', 'warn'), default='never', help='Exit non-zero at this severity. Use in CI.') |
| 1890 | <code>build_parser</code> | <code>        help="Exit non-zero at this severity. Use in CI.")</code> | Продовження інструкції 1888: Виконує виклик parser.add_argument: parser.add_argument('--fail-on', choices=('never', 'error', 'warn'), default='never', help='Exit non-zero at this severity. Use in CI.') |
| 1891 | <code>build_parser</code> | <code>    parser.add_argument(</code> | Виконує виклик parser.add_argument: parser.add_argument('--fail-over-budget', action='store_true', help='Exit non-zero when the listing needs more than its budget, i.e. descriptions would be dropped. Use in CI.') |
| 1892 | <code>build_parser</code> | <code>        "--fail-over-budget", action="store_true",</code> | Продовження інструкції 1891: Виконує виклик parser.add_argument: parser.add_argument('--fail-over-budget', action='store_true', help='Exit non-zero when the listing needs more than its budget, i.e. descriptions would be dropped. Use in CI.') |
| 1893 | <code>build_parser</code> | <code>        help="Exit non-zero when the listing needs more than its budget, i.e. "</code> | Продовження інструкції 1891: Виконує виклик parser.add_argument: parser.add_argument('--fail-over-budget', action='store_true', help='Exit non-zero when the listing needs more than its budget, i.e. descriptions would be dropped. Use in CI.') |
| 1894 | <code>build_parser</code> | <code>             "descriptions would be dropped. Use in CI.")</code> | Продовження інструкції 1891: Виконує виклик parser.add_argument: parser.add_argument('--fail-over-budget', action='store_true', help='Exit non-zero when the listing needs more than its budget, i.e. descriptions would be dropped. Use in CI.') |
| 1895 | <code>build_parser</code> | <code>    parser.add_argument(</code> | Виконує виклик parser.add_argument: parser.add_argument('--full', action='store_true', help='Print every finding instead of the first 20 per rule.') |
| 1896 | <code>build_parser</code> | <code>        "--full", action="store_true",</code> | Продовження інструкції 1895: Виконує виклик parser.add_argument: parser.add_argument('--full', action='store_true', help='Print every finding instead of the first 20 per rule.') |
| 1897 | <code>build_parser</code> | <code>        help="Print every finding instead of the first 20 per rule.")</code> | Продовження інструкції 1895: Виконує виклик parser.add_argument: parser.add_argument('--full', action='store_true', help='Print every finding instead of the first 20 per rule.') |
| 1898 | <code>build_parser</code> | <code>    parser.add_argument("--no-color", action="store_true")</code> | Виконує виклик parser.add_argument: parser.add_argument('--no-color', action='store_true') |
| 1899 | <code>build_parser</code> | <code>    parser.add_argument("--version", action="version", version="skillrot " + __version__)</code> | Виконує виклик parser.add_argument: parser.add_argument('--version', action='version', version='skillrot ' + __version__) |
| 1900 | <code>build_parser</code> | <code>    return parser</code> | Завершує поточну функцію та повертає parser |
| 1901 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1902 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1903 | <code>_validate_cli_args</code> | <code>def _validate_cli_args(args) -&gt; None:</code> | Оголошення функції `_validate_cli_args` та її аргументів; детальний контракт розібраний вище. |
| 1904 | <code>_validate_cli_args</code> | <code>    if not 0 &lt; args.context_window &lt;= sys.maxsize:</code> | Умовна гілка: not 0 &lt; args.context_window &lt;= sys.maxsize; відповідний block виконується тільки коли умова true. |
| 1905 | <code>_validate_cli_args</code> | <code>        raise AuditError("--context-window must be a positive integer within the platform range")</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('--context-window must be a positive integer within the platform range') |
| 1906 | <code>_validate_cli_args</code> | <code>    for flag, value in (("--top", args.top), ("--body-lines", args.body_lines)):</code> | Ітерує (('--top', args.top), ('--body-lines', args.body_lines)) і зв’язує кожен елемент із (flag, value) |
| 1907 | <code>_validate_cli_args</code> | <code>        if value &lt; 0:</code> | Умовна гілка: value &lt; 0; відповідний block виконується тільки коли умова true. |
| 1908 | <code>_validate_cli_args</code> | <code>            raise AuditError("{} must be non-negative".format(flag))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('{} must be non-negative'.format(flag)) |
| 1909 | <code>_validate_cli_args</code> | <code>    if not math.isfinite(args.chars_per_token) or not 0.1 &lt;= args.chars_per_token &lt;= 100:</code> | Умовна гілка: not math.isfinite(args.chars_per_token) or not 0.1 &lt;= args.chars_per_token &lt;= 100; відповідний block виконується тільки коли умова true. |
| 1910 | <code>_validate_cli_args</code> | <code>        raise AuditError("--chars-per-token must be finite and between 0.1 and 100")</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('--chars-per-token must be finite and between 0.1 and 100') |
| 1911 | <code>_validate_cli_args</code> | <code>    if not math.isfinite(args.similarity) or not 0 &lt;= args.similarity &lt;= 1:</code> | Умовна гілка: not math.isfinite(args.similarity) or not 0 &lt;= args.similarity &lt;= 1; відповідний block виконується тільки коли умова true. |
| 1912 | <code>_validate_cli_args</code> | <code>        raise AuditError("--similarity must be finite and in [0, 1]")</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('--similarity must be finite and in [0, 1]') |
| 1913 | <code>_validate_cli_args</code> | <code>    if args.budget_fraction is not None and (not math.isfinite(args.budget_fraction)</code> | Умовна гілка: args.budget_fraction is not None and (not math.isfinite(args.budget_fraction) or not 0 &lt; args.budget_fraction &lt;= 1); відповідний block виконується тільки коли умова true. |
| 1914 | <code>_validate_cli_args</code> | <code>                                              or not 0 &lt; args.budget_fraction &lt;= 1):</code> | Продовження інструкції 1913: Умовна гілка: args.budget_fraction is not None and (not math.isfinite(args.budget_fraction) or not 0 &lt; args.budget_fraction &lt;= 1); відповідний block виконується тільки коли умова true. |
| 1915 | <code>_validate_cli_args</code> | <code>        raise AuditError("--budget-fraction must be finite and in (0, 1]")</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('--budget-fraction must be finite and in (0, 1]') |
| 1916 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1917 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1918 | <code>_ClosedOutputPipe</code> | <code>class _ClosedOutputPipe(Exception):</code> | Оголошення класу `_ClosedOutputPipe` та базових класів; модель даних/поведінка розібрана вище. |
| 1919 | <code>_ClosedOutputPipe</code> | <code>    """Only a stdout write can turn a closed pipe into normal termination."""</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1920 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1921 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1922 | <code>_write_stream</code> | <code>def _write_stream(stream, text: str) -&gt; None:</code> | Оголошення функції `_write_stream` та її аргументів; детальний контракт розібраний вище. |
| 1923 | <code>_write_stream</code> | <code>    """Keep reports usable on narrow terminal encodings without losing JSON."""</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1924 | <code>_write_stream</code> | <code>    try:</code> | Межа обробки винятків: виконати block і застосувати specified handlers. |
| 1925 | <code>_write_stream</code> | <code>        try:</code> | Межа обробки винятків: виконати block і застосувати specified handlers. |
| 1926 | <code>_write_stream</code> | <code>            stream.write(text)</code> | Виконує виклик stream.write: stream.write(text) |
| 1927 | <code>_write_stream</code> | <code>        except UnicodeEncodeError:</code> | Handler для зазначеного типу винятку; operational finding/fallback залежить від body нижче. |
| 1928 | <code>_write_stream</code> | <code>            encoding = getattr(stream, "encoding", None) or "utf-8"</code> | Обчислює та зберігає encoding ← getattr(stream, 'encoding', None) or 'utf-8' |
| 1929 | <code>_write_stream</code> | <code>            stream.write(text.encode(encoding, errors="backslashreplace").decode(encoding))</code> | Виконує виклик stream.write: stream.write(text.encode(encoding, errors='backslashreplace').decode(encoding)) |
| 1930 | <code>_write_stream</code> | <code>        stream.flush()</code> | Виконує виклик stream.flush: stream.flush() |
| 1931 | <code>_write_stream</code> | <code>    except OSError as exc:</code> | Handler для зазначеного типу винятку; operational finding/fallback залежить від body нижче. |
| 1932 | <code>_write_stream</code> | <code>        # Windows reports a closed redirected output pipe as EINVAL, not EPIPE.</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 1933 | <code>_write_stream</code> | <code>        if stream is sys.stdout and (isinstance(exc, BrokenPipeError)</code> | Умовна гілка: stream is sys.stdout and (isinstance(exc, BrokenPipeError) or (os.name == 'nt' and exc.errno == 22 and (not stream.isatty()))); відповідний block виконується тільки коли умова true. |
| 1934 | <code>_write_stream</code> | <code>                                     or (os.name == "nt" and exc.errno == 22 and not stream.isatty())):</code> | Продовження інструкції 1933: Умовна гілка: stream is sys.stdout and (isinstance(exc, BrokenPipeError) or (os.name == 'nt' and exc.errno == 22 and (not stream.isatty()))); відповідний block виконується тільки коли умова true. |
| 1935 | <code>_write_stream</code> | <code>            try:</code> | Межа обробки винятків: виконати block і застосувати specified handlers. |
| 1936 | <code>_write_stream</code> | <code>                stream.close()</code> | Виконує виклик stream.close: stream.close() |
| 1937 | <code>_write_stream</code> | <code>            except OSError:</code> | Handler для зазначеного типу винятку; operational finding/fallback залежить від body нижче. |
| 1938 | <code>_write_stream</code> | <code>                pass</code> | Свідомо порожня гілка; state/output на цьому кроці не змінюється. |
| 1939 | <code>_write_stream</code> | <code>            raise _ClosedOutputPipe from None</code> | Відхиляє unsupported/failed input або передає error вище: _ClosedOutputPipe |
| 1940 | <code>_write_stream</code> | <code>        raise</code> | Відхиляє unsupported/failed input або передає error вище: поточний виняток |
| 1941 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1942 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1943 | <code>_protect_audited_sources</code> | <code>def _protect_audited_sources(output: Path, skills: Sequence[Skill]) -&gt; None:</code> | Оголошення функції `_protect_audited_sources` та її аргументів; детальний контракт розібраний вище. |
| 1944 | <code>_protect_audited_sources</code> | <code>    """Refuse a chart target that aliases a discovered skill or command file."""</code> | Рядок docstring: пояснює контракт, assumptions або обмеження enclosing function/class. |
| 1945 | <code>_protect_audited_sources</code> | <code>    try:</code> | Межа обробки винятків: виконати block і застосувати specified handlers. |
| 1946 | <code>_protect_audited_sources</code> | <code>        resolved = output.resolve()</code> | Обчислює та зберігає resolved ← output.resolve() |
| 1947 | <code>_protect_audited_sources</code> | <code>        exists = output.exists()</code> | Обчислює та зберігає exists ← output.exists() |
| 1948 | <code>_protect_audited_sources</code> | <code>        for skill in skills:</code> | Ітерує skills і зв’язує кожен елемент із skill |
| 1949 | <code>_protect_audited_sources</code> | <code>            if resolved == skill.path.resolve() or (exists and output.samefile(skill.path)):</code> | Умовна гілка: resolved == skill.path.resolve() or (exists and output.samefile(skill.path)); відповідний block виконується тільки коли умова true. |
| 1950 | <code>_protect_audited_sources</code> | <code>                raise AuditError("SVG output would overwrite an audited source file: {}".format(output))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('SVG output would overwrite an audited source file: {}'.format(output)) |
| 1951 | <code>_protect_audited_sources</code> | <code>    except RuntimeError as exc:</code> | Handler для зазначеного типу винятку; operational finding/fallback залежить від body нижче. |
| 1952 | <code>_protect_audited_sources</code> | <code>        raise AuditError("could not resolve SVG output safely: {}".format(exc)) from None</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('could not resolve SVG output safely: {}'.format(exc)) |
| 1953 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1954 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1955 | <code>_run_audit</code> | <code>def _run_audit(args) -&gt; int:</code> | Оголошення функції `_run_audit` та її аргументів; детальний контракт розібраний вище. |
| 1956 | <code>_run_audit</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1957 | <code>_run_audit</code> | <code>    # When the user passes paths, audit everything under them. With no paths we</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 1958 | <code>_run_audit</code> | <code>    # audit the supported local Claude Code profile: personal and project</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 1959 | <code>_run_audit</code> | <code>    # skills one level deep, command files, and the plugins enabled in settings.</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 1960 | <code>_run_audit</code> | <code>    home, cwd = Path.home(), Path.cwd()</code> | Обчислює та зберігає (home, cwd) ← (Path.home(), Path.cwd()) |
| 1961 | <code>_run_audit</code> | <code>    settings: dict = {}</code> | Типізує settings як dict; initial value {} |
| 1962 | <code>_run_audit</code> | <code>    extra: List[Entry] = []</code> | Типізує extra як List[Entry]; initial value [] |
| 1963 | <code>_run_audit</code> | <code>    if args.paths:</code> | Умовна гілка: args.paths; відповідний block виконується тільки коли умова true. |
| 1964 | <code>_run_audit</code> | <code>        roots, shallow = list(args.paths), []</code> | Обчислює та зберігає (roots, shallow) ← (list(args.paths), []) |
| 1965 | <code>_run_audit</code> | <code>    else:</code> | Alternative branch для попередньої умови або завершення циклу без break. |
| 1966 | <code>_run_audit</code> | <code>        settings = load_settings(home, cwd)</code> | Обчислює та зберігає settings ← load_settings(home, cwd) |
| 1967 | <code>_run_audit</code> | <code>        roots = default_roots(cwd)</code> | Обчислює та зберігає roots ← default_roots(cwd) |
| 1968 | <code>_run_audit</code> | <code>        plugins = installed_plugin_entries(home, settings)</code> | Обчислює та зберігає plugins ← installed_plugin_entries(home, settings) |
| 1969 | <code>_run_audit</code> | <code>        if plugins is not None:</code> | Умовна гілка: plugins is not None; відповідний block виконується тільки коли умова true. |
| 1970 | <code>_run_audit</code> | <code>            roots = [r for r in roots if r.name != "plugins"]</code> | Обчислює та зберігає roots ← [r for r in roots if r.name != 'plugins'] |
| 1971 | <code>_run_audit</code> | <code>            extra += plugins</code> | Оновлює накопичене значення: extra += plugins |
| 1972 | <code>_run_audit</code> | <code>        shallow = [r for r in roots if r.name != "plugins"]</code> | Обчислює та зберігає shallow ← [r for r in roots if r.name != 'plugins'] |
| 1973 | <code>_run_audit</code> | <code>        for folder in [home] + _project_dirs(cwd):</code> | Ітерує [home] + _project_dirs(cwd) і зв’язує кожен елемент із folder |
| 1974 | <code>_run_audit</code> | <code>            extra += command_entries(folder / ".claude" / "commands")</code> | Оновлює накопичене значення: extra += command_entries(folder / '.claude' / 'commands') |
| 1975 | <code>_run_audit</code> | <code>    if not roots and not extra:</code> | Умовна гілка: not roots and (not extra); відповідний block виконується тільки коли умова true. |
| 1976 | <code>_run_audit</code> | <code>        raise AuditError("no skills found. Pass a path to scan.")</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('no skills found. Pass a path to scan.') |
| 1977 | <code>_run_audit</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1978 | <code>_run_audit</code> | <code>    missing = [r for r in roots if not r.exists()]</code> | Обчислює та зберігає missing ← [r for r in roots if not r.exists()] |
| 1979 | <code>_run_audit</code> | <code>    if missing:</code> | Умовна гілка: missing; відповідний block виконується тільки коли умова true. |
| 1980 | <code>_run_audit</code> | <code>        raise AuditError("no such path: {}".format(", ".join(str(path) for path in missing)))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('no such path: {}'.format(', '.join((str(path) for path in missing)))) |
| 1981 | <code>_run_audit</code> | <code>    if not args.no_usage and args.transcripts is not None and not args.transcripts.is_dir():</code> | Умовна гілка: not args.no_usage and args.transcripts is not None and (not args.transcripts.is_dir()); відповідний block виконується тільки коли умова true. |
| 1982 | <code>_run_audit</code> | <code>        raise AuditError("--transcripts must be an existing directory: {}".format(args.transcripts))</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('--transcripts must be an existing directory: {}'.format(args.transcripts)) |
| 1983 | <code>_run_audit</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1984 | <code>_run_audit</code> | <code>    skills = discover(roots, shallow_roots=shallow, scan_all=args.all, extra=extra)</code> | Обчислює та зберігає skills ← discover(roots, shallow_roots=shallow, scan_all=args.all, extra=extra) |
| 1985 | <code>_run_audit</code> | <code>    if not skills:</code> | Умовна гілка: not skills; відповідний block виконується тільки коли умова true. |
| 1986 | <code>_run_audit</code> | <code>        raise AuditError("found no locally installable skills or commands under {}".format(</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('found no locally installable skills or commands under {}'.format(', '.join((str(r) for r in roots)))) |
| 1987 | <code>_run_audit</code> | <code>            ", ".join(str(r) for r in roots)))</code> | Продовження інструкції 1986: Відхиляє unsupported/failed input або передає error вище: AuditError('found no locally installable skills or commands under {}'.format(', '.join((str(r) for r in roots)))) |
| 1988 | <code>_run_audit</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1989 | <code>_run_audit</code> | <code>    overrides = {str(k).lower(): v for k, v in (settings.get("skillOverrides") or {}).items()}</code> | Обчислює та зберігає overrides ← {str(k).lower(): v for k, v in (settings.get('skillOverrides') or {}).items()} |
| 1990 | <code>_run_audit</code> | <code>    for skill in skills:</code> | Ітерує skills і зв’язує кожен елемент із skill |
| 1991 | <code>_run_audit</code> | <code>        # Claude Code applies skillOverrides to local skills, not plugin skills.</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 1992 | <code>_run_audit</code> | <code>        if skill.origin != "plugin":</code> | Умовна гілка: skill.origin != 'plugin'; відповідний block виконується тільки коли умова true. |
| 1993 | <code>_run_audit</code> | <code>            skill.override = overrides.get(skill.command.lower())</code> | Обчислює та зберігає skill.override ← overrides.get(skill.command.lower()) |
| 1994 | <code>_run_audit</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 1995 | <code>_run_audit</code> | <code>    fraction = args.budget_fraction</code> | Обчислює та зберігає fraction ← args.budget_fraction |
| 1996 | <code>_run_audit</code> | <code>    if fraction is None:</code> | Умовна гілка: fraction is None; відповідний block виконується тільки коли умова true. |
| 1997 | <code>_run_audit</code> | <code>        fraction = settings.get("skillListingBudgetFraction")</code> | Обчислює та зберігає fraction ← settings.get('skillListingBudgetFraction') |
| 1998 | <code>_run_audit</code> | <code>        fraction = fraction if isinstance(fraction, (int, float)) else DEFAULT_BUDGET_FRACTION</code> | Обчислює та зберігає fraction ← fraction if isinstance(fraction, (int, float)) else DEFAULT_BUDGET_FRACTION |
| 1999 | <code>_run_audit</code> | <code>    char_budget = (os.environ.get("SLASH_COMMAND_TOOL_CHAR_BUDGET")</code> | Обчислює та зберігає char_budget ← os.environ.get('SLASH_COMMAND_TOOL_CHAR_BUDGET') or (settings.get('env') or {}).get('SLASH_COMMAND_TOOL_CHAR_BUDGET') |
| 2000 | <code>_run_audit</code> | <code>                   or (settings.get("env") or {}).get("SLASH_COMMAND_TOOL_CHAR_BUDGET"))</code> | Продовження інструкції 1999: Обчислює та зберігає char_budget ← os.environ.get('SLASH_COMMAND_TOOL_CHAR_BUDGET') or (settings.get('env') or {}).get('SLASH_COMMAND_TOOL_CHAR_BUDGET') |
| 2001 | <code>_run_audit</code> | <code>    fixed = None</code> | Обчислює та зберігає fixed ← None |
| 2002 | <code>_run_audit</code> | <code>    if args.budget_fraction is None and char_budget:</code> | Умовна гілка: args.budget_fraction is None and char_budget; відповідний block виконується тільки коли умова true. |
| 2003 | <code>_run_audit</code> | <code>        try:</code> | Межа обробки винятків: виконати block і застосувати specified handlers. |
| 2004 | <code>_run_audit</code> | <code>            if not str(char_budget).isascii() or not str(char_budget).isdigit():</code> | Умовна гілка: not str(char_budget).isascii() or not str(char_budget).isdigit(); відповідний block виконується тільки коли умова true. |
| 2005 | <code>_run_audit</code> | <code>                raise ValueError</code> | Відхиляє unsupported/failed input або передає error вище: ValueError |
| 2006 | <code>_run_audit</code> | <code>            value = int(char_budget)</code> | Обчислює та зберігає value ← int(char_budget) |
| 2007 | <code>_run_audit</code> | <code>            if not 0 &lt; value &lt;= sys.maxsize:</code> | Умовна гілка: not 0 &lt; value &lt;= sys.maxsize; відповідний block виконується тільки коли умова true. |
| 2008 | <code>_run_audit</code> | <code>                raise ValueError</code> | Відхиляє unsupported/failed input або передає error вище: ValueError |
| 2009 | <code>_run_audit</code> | <code>        except ValueError:</code> | Handler для зазначеного типу винятку; operational finding/fallback залежить від body нижче. |
| 2010 | <code>_run_audit</code> | <code>            raise AuditError("SLASH_COMMAND_TOOL_CHAR_BUDGET must be a positive integer within the platform range") from None</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('SLASH_COMMAND_TOOL_CHAR_BUDGET must be a positive integer within the platform range') |
| 2011 | <code>_run_audit</code> | <code>        fixed = int(value / args.chars_per_token)</code> | Обчислює та зберігає fixed ← int(value / args.chars_per_token) |
| 2012 | <code>_run_audit</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 2013 | <code>_run_audit</code> | <code>    usage = None if args.no_usage else usage_counts(args.transcripts)</code> | Обчислює та зберігає usage ← None if args.no_usage else usage_counts(args.transcripts) |
| 2014 | <code>_run_audit</code> | <code>    if not usage:</code> | Умовна гілка: not usage; відповідний block виконується тільки коли умова true. |
| 2015 | <code>_run_audit</code> | <code>        # Empty or unavailable history is insufficient evidence to recommend</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 2016 | <code>_run_audit</code> | <code>        # uninstalling every skill as never fired.</code> | Коментар автора про інваріант, edge case або межу block; не executable instruction. |
| 2017 | <code>_run_audit</code> | <code>        usage = None</code> | Обчислює та зберігає usage ← None |
| 2018 | <code>_run_audit</code> | <code>    totals = budget(skills, args.chars_per_token, args.context_window, fraction, fixed, usage=usage)</code> | Обчислює та зберігає totals ← budget(skills, args.chars_per_token, args.context_window, fraction, fixed, usage=usage) |
| 2019 | <code>_run_audit</code> | <code>    findings = analyze(</code> | Обчислює та зберігає findings ← analyze(skills, usage=usage, portable=args.portable, body_line_budget=args.body_lines, similarity=args.similarity, listing_budget=totals.listing_budget, chars_per_token=args.chars_per_token) |
| 2020 | <code>_run_audit</code> | <code>        skills, usage=usage, portable=args.portable,</code> | Продовження інструкції 2019: Обчислює та зберігає findings ← analyze(skills, usage=usage, portable=args.portable, body_line_budget=args.body_lines, similarity=args.similarity, listing_budget=totals.listing_budget, chars_per_token=args.chars_per_token) |
| 2021 | <code>_run_audit</code> | <code>        body_line_budget=args.body_lines, similarity=args.similarity,</code> | Продовження інструкції 2019: Обчислює та зберігає findings ← analyze(skills, usage=usage, portable=args.portable, body_line_budget=args.body_lines, similarity=args.similarity, listing_budget=totals.listing_budget, chars_per_token=args.chars_per_token) |
| 2022 | <code>_run_audit</code> | <code>        listing_budget=totals.listing_budget, chars_per_token=args.chars_per_token,</code> | Продовження інструкції 2019: Обчислює та зберігає findings ← analyze(skills, usage=usage, portable=args.portable, body_line_budget=args.body_lines, similarity=args.similarity, listing_budget=totals.listing_budget, chars_per_token=args.chars_per_token) |
| 2023 | <code>_run_audit</code> | <code>    )</code> | Продовження інструкції 2019: Обчислює та зберігає findings ← analyze(skills, usage=usage, portable=args.portable, body_line_budget=args.body_lines, similarity=args.similarity, listing_budget=totals.listing_budget, chars_per_token=args.chars_per_token) |
| 2024 | <code>_run_audit</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 2025 | <code>_run_audit</code> | <code>    if args.svg:</code> | Умовна гілка: args.svg; відповідний block виконується тільки коли умова true. |
| 2026 | <code>_run_audit</code> | <code>        try:</code> | Межа обробки винятків: виконати block і застосувати specified handlers. |
| 2027 | <code>_run_audit</code> | <code>            _protect_audited_sources(args.svg, skills)</code> | Виконує виклик _protect_audited_sources: _protect_audited_sources(args.svg, skills) |
| 2028 | <code>_run_audit</code> | <code>            args.svg.write_text(</code> | Виконує виклик args.svg.write_text: args.svg.write_text(to_svg(skills, totals, usage, args.chars_per_token, args.top), encoding='utf-8') |
| 2029 | <code>_run_audit</code> | <code>                to_svg(skills, totals, usage, args.chars_per_token, args.top), encoding="utf-8")</code> | Продовження інструкції 2028: Виконує виклик args.svg.write_text: args.svg.write_text(to_svg(skills, totals, usage, args.chars_per_token, args.top), encoding='utf-8') |
| 2030 | <code>_run_audit</code> | <code>            _write_stream(sys.stderr, "skillrot: wrote {}\n".format(_display_text(str(args.svg))))</code> | Виконує виклик _write_stream: _write_stream(sys.stderr, 'skillrot: wrote {}\n'.format(_display_text(str(args.svg)))) |
| 2031 | <code>_run_audit</code> | <code>        except OSError as exc:</code> | Handler для зазначеного типу винятку; operational finding/fallback залежить від body нижче. |
| 2032 | <code>_run_audit</code> | <code>            raise AuditError("could not write {}: {}".format(args.svg, exc)) from None</code> | Відхиляє unsupported/failed input або передає error вище: AuditError('could not write {}: {}'.format(args.svg, exc)) |
| 2033 | <code>_run_audit</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 2034 | <code>_run_audit</code> | <code>    if args.json:</code> | Умовна гілка: args.json; відповідний block виконується тільки коли умова true. |
| 2035 | <code>_run_audit</code> | <code>        _write_stream(sys.stdout, to_json(skills, findings, totals, usage, args.chars_per_token) + "\n")</code> | Виконує виклик _write_stream: _write_stream(sys.stdout, to_json(skills, findings, totals, usage, args.chars_per_token) + '\n') |
| 2036 | <code>_run_audit</code> | <code>    else:</code> | Alternative branch для попередньої умови або завершення циклу без break. |
| 2037 | <code>_run_audit</code> | <code>        color = (not args.no_color and sys.stdout.isatty()</code> | Обчислює та зберігає color ← not args.no_color and sys.stdout.isatty() and (os.environ.get('NO_COLOR') is None) |
| 2038 | <code>_run_audit</code> | <code>                 and os.environ.get("NO_COLOR") is None)</code> | Продовження інструкції 2037: Обчислює та зберігає color ← not args.no_color and sys.stdout.isatty() and (os.environ.get('NO_COLOR') is None) |
| 2039 | <code>_run_audit</code> | <code>        _write_stream(sys.stdout, render(skills, findings, totals, usage, args.chars_per_token,</code> | Виконує виклик _write_stream: _write_stream(sys.stdout, render(skills, findings, totals, usage, args.chars_per_token, args.top, color, 0 if args.full else 20) + '\n') |
| 2040 | <code>_run_audit</code> | <code>                                        args.top, color, 0 if args.full else 20) + "\n")</code> | Продовження інструкції 2039: Виконує виклик _write_stream: _write_stream(sys.stdout, render(skills, findings, totals, usage, args.chars_per_token, args.top, color, 0 if args.full else 20) + '\n') |
| 2041 | <code>_run_audit</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 2042 | <code>_run_audit</code> | <code>    if args.fail_on == "error" and any(f.severity == "error" for f in findings):</code> | Умовна гілка: args.fail_on == 'error' and any((f.severity == 'error' for f in findings)); відповідний block виконується тільки коли умова true. |
| 2043 | <code>_run_audit</code> | <code>        return 1</code> | Завершує поточну функцію та повертає 1 |
| 2044 | <code>_run_audit</code> | <code>    if args.fail_on == "warn" and any(f.severity in ("error", "warn") for f in findings):</code> | Умовна гілка: args.fail_on == 'warn' and any((f.severity in ('error', 'warn') for f in findings)); відповідний block виконується тільки коли умова true. |
| 2045 | <code>_run_audit</code> | <code>        return 1</code> | Завершує поточну функцію та повертає 1 |
| 2046 | <code>_run_audit</code> | <code>    if args.fail_over_budget and totals.overflows:</code> | Умовна гілка: args.fail_over_budget and totals.overflows; відповідний block виконується тільки коли умова true. |
| 2047 | <code>_run_audit</code> | <code>        return 1</code> | Завершує поточну функцію та повертає 1 |
| 2048 | <code>_run_audit</code> | <code>    return 0</code> | Завершує поточну функцію та повертає 0 |
| 2049 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 2050 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 2051 | <code>main</code> | <code>def main(argv: Optional[Sequence[str]] = None) -&gt; int:</code> | Оголошення функції `main` та її аргументів; детальний контракт розібраний вище. |
| 2052 | <code>main</code> | <code>    try:</code> | Межа обробки винятків: виконати block і застосувати specified handlers. |
| 2053 | <code>main</code> | <code>        args = build_parser().parse_args(argv)</code> | Обчислює та зберігає args ← build_parser().parse_args(argv) |
| 2054 | <code>main</code> | <code>        _validate_cli_args(args)</code> | Виконує виклик _validate_cli_args: _validate_cli_args(args) |
| 2055 | <code>main</code> | <code>        return _run_audit(args)</code> | Завершує поточну функцію та повертає _run_audit(args) |
| 2056 | <code>main</code> | <code>    except _ClosedOutputPipe:</code> | Handler для зазначеного типу винятку; operational finding/fallback залежить від body нижче. |
| 2057 | <code>main</code> | <code>        return 0</code> | Завершує поточну функцію та повертає 0 |
| 2058 | <code>main</code> | <code>    except (AuditError, OSError) as exc:</code> | Handler для зазначеного типу винятку; operational finding/fallback залежить від body нижче. |
| 2059 | <code>main</code> | <code>        _write_stream(sys.stderr, "skillrot: {}\n".format(_display_text(str(exc))))</code> | Виконує виклик _write_stream: _write_stream(sys.stderr, 'skillrot: {}\n'.format(_display_text(str(exc)))) |
| 2060 | <code>main</code> | <code>        return 2</code> | Завершує поточну функцію та повертає 2 |
| 2061 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 2062 | <code>&lt;module&gt;</code> | <code></code> | Порожній рядок: візуально відділяє логічні blocks; виконання не змінює. |
| 2063 | <code>&lt;module&gt;</code> | <code>if __name__ == "__main__":</code> | Умовна гілка: __name__ == '__main__'; відповідний block виконується тільки коли умова true. |
| 2064 | <code>&lt;module&gt;</code> | <code>    sys.exit(main())</code> | Виконує виклик sys.exit: sys.exit(main()) |

## AST inventory кожного тесту

Нижче наведені всі поточні test methods, source spans і фактичні assertions. Arrange/action видно в exact source atlas репозиторію; assertions показують незалежно очікуваний behavior, а не лише факт існування function.

### `tests/test_accounting_usage.py` — 19 methods

SHA-256 `8e8cc8c938c6fd6ce63aae2a6b98e0a23c344dac3d48b812857bb7645bbd3b84`; 173 physical lines.

| Test | Рядки | Behavior assertions |
| --- | --- | --- |
| <code>ListingAccountingRegressionTests.test_unfilled_budget_does_not_bill_a_dropped_description</code> | 20–25 | <code>self.assertEqual(totals.requested_tokens, 63)</code><br><code>self.assertEqual(totals.always_on_tokens, 23)</code> |
| <code>ListingAccountingRegressionTests.test_aggregate_and_per_entry_costs_use_the_same_usage_order</code> | 27–34 | <code>self.assertEqual(totals.always_on_tokens, 18)</code><br><code>self.assertEqual([s['retained_listing_tokens'] for s in payload['skills']], [17, 1])</code> |
| <code>ListingAccountingRegressionTests.test_hidden_skill_has_zero_requested_listing_cost</code> | 36–38 | <code>self.assertEqual(skillrot.listing_tokens(skill, 4.0), 0)</code> |
| <code>ListingAccountingRegressionTests.test_name_only_override_bills_only_the_name</code> | 40–43 | <code>self.assertEqual(skillrot.listing_tokens(skill, 4.0), 2)</code> |
| <code>ListingAccountingRegressionTests.test_json_costs_reconcile_with_hidden_and_dropped_entries</code> | 45–55 | <code>self.assertEqual(payload.get('schema_version'), 1)</code><br><code>self.assertTrue(payload['model']['estimated'])</code><br><code>self.assertEqual(costs, {'a': 21, 'b': 1, 'manual': 0})</code><br><code>self.assertEqual(sum(costs.values()), payload['budget']['always_on_tokens'])</code> |
| <code>ListingAccountingRegressionTests.test_shadowed_command_is_not_billed_twice_in_json</code> | 57–66 | <code>self.assertEqual([row.get('retained_listing_tokens') for row in payload['skills']], [21, 0])</code><br><code>self.assertEqual(totals.always_on_tokens, 21)</code> |
| <code>ListingAccountingRegressionTests.test_json_unicode_is_safe_in_legacy_windows_pipes</code> | 68–74 | <code>self.assertEqual(json.loads(text)['skills'][0]['path'], str(skill.path))</code><br><code>self.assertTrue(text.isascii())</code> |
| <code>TranscriptEvidenceRegressionTests.test_tool_call_key_order_and_spacing_do_not_change_usage</code> | 84–87 | <code>self.assertEqual(self.counts([json.dumps(record)]), {'deploy': 1})</code> |
| <code>TranscriptEvidenceRegressionTests.test_nested_assistant_tool_blocks_are_counted</code> | 89–94 | <code>self.assertEqual(self.counts([json.dumps(record)]), {'plugin:deploy': 1})</code> |
| <code>TranscriptEvidenceRegressionTests.test_user_command_json_whitespace_is_irrelevant</code> | 96–99 | <code>self.assertEqual(self.counts([json.dumps(record)]), {'deploy': 1})</code> |
| <code>TranscriptEvidenceRegressionTests.test_unrelated_records_and_invalid_json_are_not_invocations</code> | 101–107 | <code>self.assertEqual(self.counts([json.dumps({'type': 'system', 'name': 'Skill', 'input': {'skill': 'deploy'}}), 'invalid "name":"Skill","input":{"skill":"deploy"}', json.dumps({'type…</code> |
| <code>TranscriptEvidenceRegressionTests.test_tool_result_content_is_not_recursively_counted_as_an_invocation</code> | 109–114 | <code>self.assertEqual(self.counts([json.dumps(record)]), {})</code> |
| <code>TranscriptEvidenceRegressionTests.test_bare_local_command_is_not_credited_to_namespaced_plugins</code> | 116–120 | <code>self.assertEqual([s['invocations'] for s in payload['skills']], [3, 0, 0])</code> |
| <code>TranscriptEvidenceRegressionTests.test_ambiguous_bare_usage_has_no_attributed_plugin_invocations</code> | 122–127 | <code>self.assertEqual([s['invocations'] for s in payload['skills']], [2, 0])</code> |
| <code>UntrustedReportTextTests.test_escaped_yaml_controls_cannot_corrupt_svg_xml</code> | 131–140 |  |
| <code>UntrustedReportTextTests.test_untrusted_names_cannot_emit_terminal_escape_sequences</code> | 142–147 | <code>self.assertNotIn('\x1b', report)</code><br><code>self.assertNotIn('\x07', report)</code> |
| <code>CollisionBoundaryRegressionTests.test_body_description_fallback_keeps_when_to_use</code> | 151–155 | <code>self.assertEqual(skill.routing_text, 'Deploy after required checks. Only after review.')</code> |
| <code>CollisionBoundaryRegressionTests.test_exact_duplicates_survive_the_common_word_cutoff</code> | 157–164 | <code>self.assertEqual(len(clusters), 1)</code><br><code>self.assertEqual(len(clusters[0]), size)</code> |
| <code>CollisionBoundaryRegressionTests.test_unicode_duplicate_descriptions_are_detected</code> | 166–169 | <code>self.assertEqual(len(skillrot.cluster_by_description(skills)), 1)</code> |
### `tests/test_discovery_cli.py` — 42 methods

SHA-256 `5e021e46a17c4cd107041037a1499764593fc12012752166d4dc2522f74952e8`; 495 physical lines.

| Test | Рядки | Behavior assertions |
| --- | --- | --- |
| <code>DiscoveryBoundaryTests.test_plain_skills_folder_does_not_invent_plugin_namespace</code> | 63–66 | <code>self.assertEqual([(s.command, s.plugin) for s in skills], [('deploy', None)])</code> |
| <code>DiscoveryBoundaryTests.test_other_harness_paths_do_not_invent_plugin_namespace</code> | 68–73 | <code>self.assertEqual(skillrot.discover([root])[0].command, 'deploy')</code> |
| <code>DiscoveryBoundaryTests.test_generic_plugins_directory_is_not_plugin_ownership_evidence</code> | 75–77 | <code>self.assertEqual(skillrot.discover([self.root])[0].command, 'deploy')</code> |
| <code>DiscoveryBoundaryTests.test_default_roots_only_include_the_modeled_claude_profile</code> | 79–86 | <code>self.assertEqual(skillrot.default_roots(cwd), [home / '.claude' / 'skills'])</code> |
| <code>DiscoveryBoundaryTests.test_scan_all_overrides_shallow_installed_discovery</code> | 88–92 | <code>self.assertEqual(sorted((s.command for s in skills)), ['nested', 'top'])</code> |
| <code>DiscoveryBoundaryTests.test_empty_plugin_manifest_does_not_count_documentation_mirrors</code> | 94–97 | <code>self.assertEqual(skillrot.discover([root]), [])</code> |
| <code>DiscoveryBoundaryTests.test_explicit_empty_skills_does_not_enable_root_skill_fallback</code> | 99–102 | <code>self.assertEqual(skillrot.discover([root]), [])</code> |
| <code>DiscoveryBoundaryTests.test_existing_empty_skills_directory_disables_root_skill_fallback</code> | 104–108 | <code>self.assertEqual(skillrot.discover([root]), [])</code> |
| <code>DiscoveryBoundaryTests.test_plugin_json_requires_a_name</code> | 110–116 | <code>self.assertEqual(code, 2)</code><br><code>self.assertIn('name', err)</code><br><code>self.assertEqual(out, '')</code> |
| <code>DiscoveryBoundaryTests.test_missing_explicit_manifest_components_are_operational_errors</code> | 118–126 | <code>self.assertEqual(code, 2)</code><br><code>self.assertIn('missing', err)</code><br><code>self.assertEqual(out, '')</code> |
| <code>DiscoveryBoundaryTests.test_missing_local_marketplace_source_is_an_operational_error</code> | 128–135 | <code>self.assertEqual(code, 2)</code><br><code>self.assertIn('source', err)</code><br><code>self.assertIn('missing', err)</code><br><code>self.assertEqual(out, '')</code> |
| <code>DiscoveryBoundaryTests.test_remote_only_marketplace_does_not_count_documentation_mirrors</code> | 137–141 | <code>self.assertEqual(skillrot.discover([self.root]), [])</code> |
| <code>DiscoveryBoundaryTests.test_required_marketplace_fields_cannot_be_silently_omitted</code> | 143–156 | <code>self.assertEqual(code, 2)</code><br><code>self.assertIn('marketplace.json', err)</code><br><code>self.assertIn(field, err)</code><br><code>self.assertEqual(out, '')</code> |
| <code>DiscoveryBoundaryTests.test_explicit_empty_marketplace_is_accepted_alongside_other_inputs</code> | 158–164 | <code>self.assertEqual(code, 0)</code><br><code>self.assertEqual([s['command'] for s in json.loads(out)['skills']], ['valid'])</code> |
| <code>DiscoveryBoundaryTests.test_marketplace_component_extensions_with_plugin_json_are_diagnosed</code> | 166–187 | <code>self.assertEqual(code, 2)</code><br><code>self.assertIn('plugin.json', err)</code><br><code>self.assertIn(key, err)</code><br><code>self.assertIn('conflict' if strict is False else 'unsupported', err.lower())</code><br><code>self.assertEqual(out, '')</code> |
| <code>DiscoveryBoundaryTests.test_marketplace_strict_flag_must_be_boolean</code> | 189–198 | <code>self.assertEqual(code, 2)</code><br><code>self.assertIn('strict', err)</code><br><code>self.assertEqual(out, '')</code> |
| <code>DiscoveryBoundaryTests.test_empty_remote_source_identifier_is_diagnosed</code> | 200–209 | <code>self.assertEqual(code, 2)</code><br><code>self.assertIn('source type', err)</code><br><code>self.assertEqual(out, '')</code> |
| <code>DiscoveryBoundaryTests.test_strict_false_conflict_in_non_listing_component_is_diagnosed</code> | 211–223 | <code>self.assertEqual(code, 2)</code><br><code>self.assertIn('conflict', err)</code><br><code>self.assertIn('hooks', err)</code><br><code>self.assertEqual(out, '')</code> |
| <code>DiscoveryBoundaryTests.test_nested_plugin_commands_keep_path_qualified_names</code> | 225–232 | <code>self.assertEqual([(s.command, s.kind) for s in skills], [('p:frontend:component', 'command')])</code> |
| <code>DiscoveryBoundaryTests.test_manifest_skill_paths_cannot_escape_checkout</code> | 234–242 | <code>self.assertEqual(code, 2)</code><br><code>self.assertIn('skills', err)</code><br><code>self.assertEqual(out, '')</code> |
| <code>DiscoveryBoundaryTests.test_marketplace_source_cannot_escape_checkout</code> | 244–252 | <code>self.assertEqual(code, 2)</code><br><code>self.assertIn('source', err)</code><br><code>self.assertEqual(out, '')</code> |
| <code>DiscoveryBoundaryTests.test_manifest_command_path_cannot_escape_checkout</code> | 254–261 | <code>self.assertEqual(code, 2)</code><br><code>self.assertIn('commands', err)</code><br><code>self.assertEqual(out, '')</code> |
| <code>DiscoveryBoundaryTests.test_manifest_symlink_path_cannot_escape_checkout</code> | 263–282 | <code>self.assertEqual(code, 2)</code><br><code>self.assertIn('skills', err)</code><br><code>self.assertEqual(out, '')</code> |
| <code>DiscoveryBoundaryTests.test_malformed_manifest_shapes_are_operational_errors</code> | 284–293 | <code>self.assertEqual(code, 2)</code><br><code>self.assertIn('plugin.json', err)</code><br><code>self.assertEqual(out, '')</code> |
| <code>DiscoveryBoundaryTests.test_invalid_manifest_json_is_not_a_recursive_scan</code> | 295–302 | <code>self.assertEqual(code, 2)</code><br><code>self.assertIn('plugin.json', err)</code><br><code>self.assertEqual(out, '')</code> |
| <code>DiscoveryBoundaryTests.test_direct_skill_audit_diagnoses_its_malformed_owning_manifest</code> | 304–311 | <code>self.assertEqual(code, 2)</code><br><code>self.assertIn('plugin.json', err)</code><br><code>self.assertEqual(out, '')</code> |
| <code>DiscoveryBoundaryTests.test_excessively_nested_manifest_json_is_an_operational_error</code> | 313–322 | <code>self.assertEqual(code, 2)</code><br><code>self.assertIn('plugin.json', err)</code><br><code>self.assertEqual(out, '')</code> |
| <code>OperationalCliTests.test_a_missing_input_among_valid_inputs_is_an_operational_failure</code> | 338–341 | <code>self.assertEqual(code, 2)</code><br><code>self.assertIn('missing', err)</code> |
| <code>OperationalCliTests.test_svg_write_failure_is_an_operational_failure</code> | 343–347 | <code>self.assertEqual(code, 2)</code><br><code>self.assertIn('could not write', err)</code> |
| <code>OperationalCliTests.test_invalid_numeric_options_are_rejected_before_audit</code> | 349–360 | <code>self.assertEqual(code, 2)</code><br><code>self.assertIn(flag, err)</code><br><code>self.assertEqual(out, '')</code> |
| <code>OperationalCliTests.test_malformed_nested_settings_are_operational_failures</code> | 362–373 | <code>self.assertEqual(code, 2)</code><br><code>self.assertIn('settings.json', err)</code><br><code>self.assertEqual(out, '')</code> |
| <code>OperationalCliTests.test_malformed_plugin_registry_is_an_operational_failure</code> | 375–383 | <code>self.assertEqual(code, 2)</code><br><code>self.assertIn('installed_plugins.json', err)</code><br><code>self.assertEqual(out, '')</code> |
| <code>OperationalCliTests.test_distinct_scoped_plugin_roots_are_an_explicit_profile_limitation</code> | 385–398 | <code>self.assertEqual(code, 2)</code><br><code>self.assertIn('p@m', err)</code><br><code>self.assertIn('explicit', err.lower())</code><br><code>self.assertEqual(out, '')</code> |
| <code>OperationalCliTests.test_repeated_registry_records_for_one_physical_root_are_accepted</code> | 400–410 | <code>self.assertEqual(code, 0)</code><br><code>self.assertEqual([s['command'] for s in json.loads(out)['skills']], ['deploy', 'p:one'])</code> |
| <code>OperationalCliTests.test_malformed_marketplace_registry_is_an_operational_failure</code> | 412–419 | <code>self.assertEqual(code, 2)</code><br><code>self.assertIn('known_marketplaces.json', err)</code><br><code>self.assertEqual(out, '')</code> |
| <code>OperationalCliTests.test_unresolved_enabled_plugin_does_not_report_a_clean_inventory</code> | 421–426 | <code>self.assertEqual(code, 2)</code><br><code>self.assertIn('p@m', err)</code><br><code>self.assertEqual(out, '')</code> |
| <code>OperationalCliTests.test_absent_enabled_plugins_does_not_inventory_disabled_cache</code> | 428–433 | <code>self.assertEqual(code, 0)</code><br><code>self.assertEqual([s['command'] for s in json.loads(out)['skills']], ['deploy'])</code> |
| <code>OperationalCliTests.test_plugin_overrides_do_not_change_plugin_listing</code> | 435–446 | <code>self.assertEqual(code, 0)</code><br><code>self.assertTrue(item['in_listing'])</code><br><code>self.assertIsNone(item['override'])</code> |
| <code>OperationalCliTests.test_no_transcript_evidence_does_not_claim_never_invoked</code> | 448–455 | <code>self.assertEqual(code, 0)</code><br><code>self.assertNotIn('SR024', [f['rule'] for f in payload['findings']])</code><br><code>self.assertIsNone(payload['skills'][0]['invocations'])</code> |
| <code>OperationalCliTests.test_text_output_falls_back_safely_on_ascii_streams</code> | 457–468 | <code>self.assertEqual(code, 0)</code><br><code>self.assertIn('caf', out)</code> |
| <code>OperationalCliTests.test_closed_output_pipe_does_not_print_a_traceback</code> | 470–480 | <code>self.assertEqual(process.wait(timeout=10), 0, stderr)</code><br><code>self.assertNotIn('Traceback', stderr)</code> |
| <code>OperationalCliTests.test_help_and_version_handle_closed_output_pipes</code> | 482–491 | <code>self.assertEqual(process.wait(timeout=10), 0, stderr)</code> |
### `tests/test_frontmatter_hardening.py` — 35 methods

SHA-256 `8676e9b6722e66898886f85bd7e55cbe703f1496ab1aaa83976923d62cc55919`; 242 physical lines.

| Test | Рядки | Behavior assertions |
| --- | --- | --- |
| <code>FrontmatterHardeningTests.test_boolean_comments_preserve_invocation_controls</code> | 27–32 | <code>self.assertIn('SR004', {f.rule for f in findings})</code><br><code>self.assertNotIn('SR005', {f.rule for f in findings})</code> |
| <code>FrontmatterHardeningTests.test_quoted_keys_cannot_hide_nonportable_fields</code> | 34–37 | <code>self.assertIn('SR010', {f.rule for f in findings})</code> |
| <code>FrontmatterHardeningTests.test_comment_marker_inside_quotes_is_text</code> | 39–42 | <code>self.assertEqual(fm['description'], 'Use when #tag appears.')</code><br><code>self.assertEqual(problems, [])</code> |
| <code>FrontmatterHardeningTests.test_quoted_escapes_decode_without_losing_trigger_text</code> | 44–48 | <code>self.assertEqual(fm['name'], "it's")</code><br><code>self.assertEqual(fm['description'], 'Use when "quoted" paths use \\ here.')</code><br><code>self.assertEqual(problems, [])</code> |
| <code>FrontmatterHardeningTests.test_multiline_quoted_scalar_folds_newlines</code> | 50–53 | <code>self.assertEqual(fm['description'], 'Use when asked to inspect a skill.')</code><br><code>self.assertEqual(problems, [])</code> |
| <code>FrontmatterHardeningTests.test_multiline_quoted_scalar_preserves_blank_line</code> | 55–58 | <code>self.assertEqual(fm['description'], 'Use when asked\nto inspect a skill.')</code><br><code>self.assertEqual(problems, [])</code> |
| <code>FrontmatterHardeningTests.test_multiline_double_quote_backslash_joins_lines</code> | 60–63 | <code>self.assertEqual(fm['description'], 'Use when asked to inspect a skill.')</code><br><code>self.assertEqual(problems, [])</code> |
| <code>FrontmatterHardeningTests.test_plain_scalar_preserves_blank_line_paragraph</code> | 65–68 | <code>self.assertEqual(fm['description'], 'Use when asked\nto inspect a skill.')</code><br><code>self.assertEqual(problems, [])</code> |
| <code>FrontmatterHardeningTests.test_indented_block_delimiter_does_not_end_frontmatter</code> | 70–74 | <code>self.assertEqual(fm['description'], 'Use when asked.\n---\nMore.')</code><br><code>self.assertEqual(body, 'Body.')</code><br><code>self.assertEqual(problems, [])</code> |
| <code>FrontmatterHardeningTests.test_flat_flow_list_preserves_quoted_comment_characters</code> | 76–79 | <code>self.assertEqual(fm.get('allowed-tools'), 'Read Bash(git:*) # scope')</code><br><code>self.assertEqual(problems, [])</code> |
| <code>FrontmatterHardeningTests.test_indentless_block_sequence_is_supported</code> | 81–84 | <code>self.assertEqual(fm.get('allowed-tools'), 'Read Bash(git:*)')</code><br><code>self.assertEqual(problems, [])</code> |
| <code>FrontmatterHardeningTests.test_plain_continuation_comments_do_not_become_routing_text</code> | 86–90 | <code>self.assertEqual(fm['description'], 'Use when asked to inspect a skill.')</code><br><code>self.assertEqual(problems, [])</code> |
| <code>FrontmatterHardeningTests.test_plain_continuations_preserve_quotes_and_boolean_looking_text</code> | 92–97 | <code>self.assertEqual(fm.get('description'), 'Use when the user says ' + continuation)</code><br><code>self.assertEqual(problems, [])</code> |
| <code>FrontmatterHardeningTests.test_empty_flow_items_and_sequence_indicator_are_invalid</code> | 99–103 | <code>self.assertTrue(any((p.startswith('invalid-frontmatter:') for p in problems)))</code> |
| <code>FrontmatterHardeningTests.test_top_level_comments_do_not_split_a_metadata_mapping</code> | 105–108 | <code>self.assertEqual(problems, [])</code><br><code>self.assertEqual(getattr(fm.get('metadata'), 'members', None), {'a': 'text', 'b': 'text'})</code> |
| <code>FrontmatterHardeningTests.test_flow_delimiters_require_quoted_items</code> | 110–118 | <code>self.assertTrue(any((p.startswith('invalid-frontmatter:') for p in problems)))</code><br><code>self.assertEqual(problems, [])</code> |
| <code>FrontmatterHardeningTests.test_literal_scalar_preserves_indentation_and_comments</code> | 120–123 | <code>self.assertEqual(fm['description'], 'Use when asked.\n  # example\nLast.')</code><br><code>self.assertEqual(problems, [])</code> |
| <code>FrontmatterHardeningTests.test_folded_scalar_preserves_paragraph_break</code> | 125–128 | <code>self.assertEqual(fm['description'], 'Use when asked.\nInspect a skill.')</code><br><code>self.assertEqual(problems, [])</code> |
| <code>FrontmatterHardeningTests.test_block_scalar_cannot_silently_change_uneven_indentation</code> | 130–132 | <code>self.assertIn('SR009', {f.rule for f in findings})</code> |
| <code>FrontmatterHardeningTests.test_supported_block_tool_list_is_not_flattened_with_dashes</code> | 134–143 | <code>self.assertEqual(skill.frontmatter['allowed-tools'], 'Read Bash(git:*)')</code><br><code>self.assertNotIn('SR009', {f.rule for f in skillrot.analyze([skill])})</code><br><code>self.assertIn('SR014', {f.rule for f in skillrot.analyze([skill], portable=True)})</code> |
| <code>FrontmatterHardeningTests.test_simple_metadata_string_map_passes_portable</code> | 145–147 | <code>self.assertEqual(self.errors('name: thing\ndescription: Use when asked.\nmetadata:\n  author: \'A # team\'\n  version: "1.0"'), [])</code> |
| <code>FrontmatterHardeningTests.test_metadata_nonstring_value_is_not_silently_stringified</code> | 149–154 | <code>self.assertIn('SR014', {f.rule for f in findings})</code> |
| <code>FrontmatterHardeningTests.test_scalar_metadata_is_not_a_valid_map</code> | 156–158 | <code>self.assertIn('SR014', {f.rule for f in self.errors('name: thing\ndescription: Use when asked.\nmetadata: author')})</code> |
| <code>FrontmatterHardeningTests.test_invalid_or_unsupported_yaml_cannot_pass_validation</code> | 160–174 | <code>self.assertIn('SR009', {f.rule for f in findings})</code> |
| <code>FrontmatterHardeningTests.test_missing_description_is_warning_for_claude</code> | 176–179 | <code>self.assertEqual(item.severity, 'warn')</code> |
| <code>FrontmatterHardeningTests.test_empty_frontmatter_still_requires_portable_fields</code> | 181–184 | <code>self.assertIn('SR002', {f.rule for f in findings})</code><br><code>self.assertIn('SR013', {f.rule for f in findings})</code> |
| <code>FrontmatterHardeningTests.test_nonstring_routing_fields_are_rejected</code> | 186–190 | <code>self.assertIn('SR014', {f.rule for f in self.errors('name: thing\ndescription: ' + value)})</code> |
| <code>FrontmatterHardeningTests.test_quoted_numeric_description_is_a_string</code> | 192–193 | <code>self.assertNotIn('SR014', {f.rule for f in self.errors('name: thing\ndescription: "42"')})</code> |
| <code>FrontmatterHardeningTests.test_portable_description_limit_is_1024</code> | 195–197 | <code>self.assertEqual(self.errors('name: thing\ndescription: ' + 'x' * 1024), [])</code><br><code>self.assertIn('SR014', {f.rule for f in self.errors('name: thing\ndescription: ' + 'x' * 1025)})</code> |
| <code>FrontmatterHardeningTests.test_description_limit_includes_quoted_whitespace</code> | 199–201 | <code>self.assertIn('SR014', {f.rule for f in self.errors('name: thing\ndescription: "' + 'x' * 1024 + ' "')})</code> |
| <code>FrontmatterHardeningTests.test_portable_name_constraints_and_directory_match</code> | 203–207 | <code>self.assertIn('SR013', {f.rule for f in self.errors('name: ' + name + '\ndescription: Use when asked.')})</code> |
| <code>FrontmatterHardeningTests.test_portable_unicode_lowercase_name_matches_directory</code> | 209–211 | <code>self.assertEqual([f for f in self.findings('name: пример\ndescription: Use when asked.', portable=True, name='пример') if f.severity == 'error'], [])</code> |
| <code>FrontmatterHardeningTests.test_portable_relative_and_absolute_paths_match_the_same_directory</code> | 213–227 | <code>self.assertNotIn('SR013', {f.rule for f in findings})</code> |
| <code>FrontmatterHardeningTests.test_portable_compatibility_limit_is_error</code> | 229–231 | <code>self.assertIn('SR011', {f.rule for f in findings})</code> |
| <code>FrontmatterHardeningTests.test_invalid_utf8_is_an_unreadable_file</code> | 233–238 | <code>self.assertIn('SR007', {f.rule for f in findings})</code> |
### `tests/test_production_edges.py` — 27 methods

SHA-256 `bf549260a27210ca227ffc39b6ab2ae4c9be1a77592089f20940d7dba072e567`; 333 physical lines.

| Test | Рядки | Behavior assertions |
| --- | --- | --- |
| <code>TypedFrontmatterEdgeTests.test_collection_cannot_become_a_string_via_plain_continuation</code> | 27–33 | <code>self.assertIn('SR009', {f.rule for f in findings})</code><br><code>self.assertEqual(skill.frontmatter, {})</code> |
| <code>TypedFrontmatterEdgeTests.test_collection_comments_do_not_erase_type_evidence</code> | 35–39 | <code>self.assertEqual(getattr(skill.frontmatter['description'], 'kind'), 'sequence')</code><br><code>self.assertIn('SR014', {f.rule for f in skillrot.analyze([skill])})</code><br><code>self.assertNotIn('SR009', {f.rule for f in skillrot.analyze([skill])})</code> |
| <code>TypedFrontmatterEdgeTests.test_metadata_boolean_and_null_keys_are_not_string_keys</code> | 41–45 | <code>self.assertIn('SR009', {f.rule for f in skillrot.analyze([skill], portable=True)})</code> |
| <code>TypedFrontmatterEdgeTests.test_quoted_boolean_and_null_metadata_keys_remain_strings</code> | 47–52 | <code>self.assertEqual(getattr(skill.frontmatter['metadata'], 'members'), {'true': 'text', 'null': 'text'})</code><br><code>self.assertEqual([f for f in skillrot.analyze([skill], portable=True) if f.severity == 'error'], [])</code> |
| <code>TypedFrontmatterEdgeTests.test_boolean_collections_are_flagged_and_do_not_hide_the_skill</code> | 54–59 | <code>self.assertIn('SR005', {f.rule for f in skillrot.analyze([skill])})</code><br><code>self.assertTrue(skill.in_listing)</code> |
| <code>TypedFrontmatterEdgeTests.test_folded_keep_chomping_preserves_trailing_blank_lines</code> | 61–67 | <code>self.assertEqual(skill.frontmatter.get('description'), expected)</code> |
| <code>OperationalSourceBoundaryTests.test_missing_explicit_transcript_directory_is_an_operational_failure</code> | 92–97 | <code>self.assertEqual(code, 2)</code><br><code>self.assertEqual(out, '')</code><br><code>self.assertIn('--transcripts', err)</code> |
| <code>OperationalSourceBoundaryTests.test_file_is_not_an_explicit_transcript_directory</code> | 99–103 | <code>self.assertEqual(code, 2)</code><br><code>self.assertEqual(out, '')</code><br><code>self.assertIn('--transcripts', err)</code> |
| <code>OperationalSourceBoundaryTests.test_no_usage_does_not_require_an_explicit_transcript_path</code> | 105–109 | <code>self.assertEqual(code, 0)</code><br><code>self.assertIsNone(json.loads(out)['skills'][0]['invocations'])</code> |
| <code>OperationalSourceBoundaryTests.test_operational_error_paths_cannot_emit_terminal_controls</code> | 111–115 | <code>self.assertEqual(code, 2)</code><br><code>self.assertNotIn('\x1b', err)</code><br><code>self.assertNotIn('\x07', err)</code> |
| <code>OperationalSourceBoundaryTests.test_c1_controls_cannot_escape_reports_or_diagnostics</code> | 117–129 | <code>self.assertEqual(code, 2)</code><br><code>self.assertNotIn(control, err)</code><br><code>self.assertNotIn(control, report)</code> |
| <code>OperationalSourceBoundaryTests.test_argparse_errors_cannot_emit_terminal_controls</code> | 131–135 | <code>self.assertEqual(code, 2)</code><br><code>self.assertNotIn('\x1b', err)</code><br><code>self.assertNotIn('\x07', err)</code> |
| <code>OperationalSourceBoundaryTests.test_svg_status_path_cannot_emit_terminal_controls</code> | 137–147 | <code>self.assertEqual(code, 0)</code><br><code>self.assertTrue(target.is_file())</code><br><code>self.assertNotIn('\x1b', err)</code><br><code>self.assertNotIn('\x07', err)</code> |
| <code>OperationalSourceBoundaryTests.test_svg_status_is_safe_when_the_filesystem_accepts_a_control_path</code> | 149–157 | <code>self.assertEqual(code, 0)</code><br><code>self.assertNotIn('\x1b', err)</code><br><code>self.assertNotIn('\x07', err)</code> |
| <code>OperationalSourceBoundaryTests.test_svg_cannot_overwrite_an_audited_skill</code> | 159–165 | <code>self.assertEqual(code, 2)</code><br><code>self.assertEqual(self.path.read_bytes(), original)</code><br><code>self.assertEqual(out, '')</code><br><code>self.assertIn('audited', err.lower())</code> |
| <code>OperationalSourceBoundaryTests.test_svg_cannot_overwrite_a_hardlinked_audited_skill</code> | 167–176 | <code>self.assertEqual(code, 2)</code><br><code>self.assertEqual(self.path.read_bytes(), original)</code> |
| <code>OperationalSourceBoundaryTests.test_recursive_inventory_failure_cannot_report_a_clean_partial_library</code> | 190–200 | <code>self.assertEqual(code, 2)</code><br><code>self.assertEqual(out, '')</code><br><code>self.assertIn('denied', err)</code> |
| <code>OperationalSourceBoundaryTests.test_shallow_inventory_surfaces_denied_skill_directory</code> | 202–207 | <code>self.assertRaises(skillrot.AuditError)</code> |
| <code>OperationalSourceBoundaryTests.test_plugin_skill_inventory_surfaces_denied_component_directory</code> | 209–224 | <code>self.assertEqual(code, 2)</code><br><code>self.assertEqual(out, '')</code><br><code>self.assertIn('denied', err)</code> |
| <code>OperationalSourceBoundaryTests.test_plugin_command_inventory_surfaces_denied_nested_directory</code> | 226–239 | <code>self.assertEqual(code, 2)</code><br><code>self.assertEqual(out, '')</code><br><code>self.assertIn('denied', err)</code> |
| <code>OperationalSourceBoundaryTests.test_local_command_inventory_surfaces_denied_nested_directory</code> | 241–248 | <code>self.assertRaises(skillrot.AuditError)</code> |
| <code>OperationalSourceBoundaryTests.test_absent_optional_commands_directory_stays_empty</code> | 250–251 | <code>self.assertEqual(skillrot.command_entries(self.root / 'absent'), [])</code> |
| <code>OperationalSourceBoundaryTests.test_recursive_inventory_does_not_follow_child_directory_links</code> | 264–278 | <code>self.assertEqual(code, 0)</code><br><code>self.assertEqual(len(json.loads(out)['skills']), 1)</code><br><code>self.assertEqual(code, 0)</code><br><code>self.assertEqual(len(json.loads(out)['skills']), 1)</code> |
| <code>OperationalSourceBoundaryTests.test_recursive_directory_link_cycle_terminates_without_duplicate_inventory</code> | 280–290 | <code>self.assertEqual(result.returncode, 0, result.stderr)</code><br><code>self.assertEqual(len(json.loads(result.stdout)['skills']), 1)</code> |
| <code>OperationalSourceBoundaryTests.test_bundle_footprint_does_not_count_directory_link_cycles</code> | 292–300 | <code>self.assertEqual(code, 0, err)</code><br><code>self.assertEqual(json.loads(out)['budget']['bundle_bytes'], expected)</code> |
| <code>OperationalSourceBoundaryTests.test_bundle_footprint_excludes_files_behind_child_directory_links</code> | 302–309 | <code>self.assertEqual(code, 0, err)</code><br><code>self.assertEqual(json.loads(out)['budget']['bundle_bytes'], expected)</code> |
| <code>OperationalSourceBoundaryTests.test_discovered_path_resolution_loop_is_an_operational_failure</code> | 311–329 | <code>self.assertEqual(code, 2)</code><br><code>self.assertEqual(out, '')</code><br><code>self.assertIn('resolve', err.lower())</code><br><code>self.assertNotIn('Traceback', err)</code> |
### `tests/test_skill_bundle.py` — 7 methods

SHA-256 `6add93e0cf993e7e94fcefd6f2f8bebb5ba89efbd4e9161dd811100da490f8cc`; 189 physical lines.

| Test | Рядки | Behavior assertions |
| --- | --- | --- |
| <code>SkillBundleTests.test_builder_cli_works_outside_the_checkout</code> | 43–49 | <code>self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))</code><br><code>self.assertEqual(len(archives), 1)</code><br><code>self.assertEqual(archives[0].name, 'skillrot-' + skillrot.__version__ + '-local.zip')</code> |
| <code>SkillBundleTests.test_archive_resources_have_one_root_and_complete_checksums</code> | 51–73 | <code>self.assertEqual(set(archive.namelist()), {'skillrot/' + name for name in resources &#124; {'manifest.json'}})</code><br><code>self.assertEqual(manifest['schema_version'], 1)</code><br><code>self.assertEqual(manifest['name'], 'skillrot')</code><br><code>self.assertEqual(manifest['version'], skillrot.__version__)</code><br><code>self.assertEqual(manifest['profile'], profile)</code><br><code>self.assertEqual(set(manifest['files']), resources)</code><br><code>self.assertEqual(manifest['files'][name]['sha256'], hashlib.sha256(payload).hexdigest())</code><br><code>self.assertEqual(manifest['files'][name]['size'], len(payload))</code> |
| <code>SkillBundleTests.test_archives_are_byte_deterministic_and_exclude_repository_noise</code> | 75–106 | <code>self.assertEqual(first.read_bytes(), second.read_bytes())</code><br><code>self.assertTrue(all((member.date_time == (1980, 1, 1, 0, 0, 0) for member in archive.infolist())))</code><br><code>self.assertTrue(all((member.external_attr &gt;&gt; 16 == 33188 for member in archive.infolist())))</code><br><code>self.assertTrue(all((b'private delivery noise' not in archive.read(name) for name in archive.namelist())))</code> |
| <code>SkillBundleTests.test_extracted_local_cli_audits_real_files_outside_the_checkout</code> | 108–134 | <code>self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))</code><br><code>self.assertEqual(payload['version'], skillrot.__version__)</code><br><code>self.assertEqual(payload['schema_version'], 1)</code><br><code>self.assertEqual(payload['budget']['skills'], 1)</code><br><code>self.assertEqual(payload['skills'][0]['command'], 'notes')</code><br><code>self.assertEqual(payload['findings'], [])</code> |
| <code>SkillBundleTests.test_both_extracted_skill_frontmatters_are_portable</code> | 136–147 | <code>self.assertEqual(errors, [])</code> |
| <code>SkillBundleTests.test_symlink_or_junction_resource_is_rejected_instead_of_embedded</code> | 149–178 | <code>self.assertRaises(ValueError)</code> |
| <code>SkillBundleTests.test_unknown_profile_is_rejected_without_an_archive</code> | 180–185 | <code>self.assertEqual(result.returncode, 2)</code><br><code>self.assertFalse(output.exists())</code><br><code>self.assertNotIn(b'Traceback', result.stderr)</code> |
### `tests/test_skillrot.py` — 83 methods

SHA-256 `56b96d62085186d05fdc6cd0624202ea1b93b42fa2bc3395306105fd519b4456`; 751 physical lines.

| Test | Рядки | Behavior assertions |
| --- | --- | --- |
| <code>FrontmatterTests.test_parses_scalars_and_body</code> | 46–51 | <code>self.assertEqual(fm['name'], 'deploy')</code><br><code>self.assertIn('Use when', fm['description'])</code><br><code>self.assertEqual(problems, [])</code><br><code>self.assertIn('# Deploy', body)</code> |
| <code>FrontmatterTests.test_leading_blank_line_breaks_frontmatter</code> | 53–57 | <code>self.assertEqual(fm, {})</code><br><code>self.assertIn('frontmatter-not-first-line', problems)</code><br><code>self.assertIn('---', body)</code> |
| <code>FrontmatterTests.test_missing_frontmatter</code> | 59–62 | <code>self.assertEqual(fm, {})</code><br><code>self.assertIn('no-frontmatter', problems)</code> |
| <code>FrontmatterTests.test_unterminated_frontmatter</code> | 64–66 | <code>self.assertIn('unterminated-frontmatter', problems)</code> |
| <code>FrontmatterTests.test_folded_block_scalar</code> | 68–71 | <code>self.assertEqual(fm['description'], 'first line second line')</code> |
| <code>FrontmatterTests.test_nested_map_captured_as_key</code> | 73–77 | <code>self.assertIn('metadata', fm)</code><br><code>self.assertEqual(fm['description'], 'Use when asked.')</code> |
| <code>FrontmatterTests.test_quotes_stripped</code> | 79–81 | <code>self.assertEqual(fm['name'], 'x')</code> |
| <code>RuleTests.test_clean_skill_has_no_errors</code> | 97–100 | <code>self.assertEqual([f.rule for f in findings if f.severity == 'error'], [])</code> |
| <code>RuleTests.test_sr001_frontmatter_not_first_line</code> | 102–103 | <code>self.assertIn('SR001', self.rules_for('\n' + GOOD))</code> |
| <code>RuleTests.test_sr002_missing_description</code> | 105–106 | <code>self.assertIn('SR002', self.rules_for('---\nname: x\n---\nbody\n'))</code> |
| <code>RuleTests.test_sr003_listing_cap</code> | 108–111 | <code>self.assertIn('SR003', self.rules_for('---\nname: x\ndescription: {}\n---\nbody\n'.format(long_text)))</code> |
| <code>RuleTests.test_sr003_counts_when_to_use_toward_the_cap</code> | 113–117 | <code>self.assertIn('SR003', self.rules_for(text))</code> |
| <code>RuleTests.test_sr004_unreachable_skill</code> | 119–122 | <code>self.assertIn('SR004', self.rules_for(text))</code> |
| <code>RuleTests.test_sr004_not_raised_when_only_one_is_set</code> | 124–127 | <code>self.assertNotIn('SR004', self.rules_for(text))</code> |
| <code>RuleTests.test_boolean_synonyms_accepted</code> | 129–134 | <code>self.assertIn('SR004', rules)</code><br><code>self.assertNotIn('SR005', rules)</code> |
| <code>RuleTests.test_sr005_invalid_boolean</code> | 136–139 | <code>self.assertIn('SR005', self.rules_for(text))</code> |
| <code>RuleTests.test_sr022_description_without_trigger</code> | 141–143 | <code>self.assertIn('SR022', self.rules_for(text))</code> |
| <code>RuleTests.test_sr022_silent_when_trigger_present</code> | 145–146 | <code>self.assertNotIn('SR022', self.rules_for(GOOD))</code> |
| <code>RuleTests.test_sr023_oversized_body</code> | 148–151 | <code>self.assertIn('SR023', self.rules_for(text, body_line_budget=50))</code> |
| <code>RuleTests.test_sr025_thin_description</code> | 153–154 | <code>self.assertIn('SR025', self.rules_for('---\nname: x\ndescription: hi\n---\nbody\n'))</code> |
| <code>RuleTests.test_sr010_portable_rejects_extra_fields</code> | 156–160 | <code>self.assertIn('SR010', self.rules_for(text, portable=True))</code><br><code>self.assertNotIn('SR010', self.rules_for(text, name='other', portable=False))</code> |
| <code>RuleTests.test_sr011_compatibility_cap</code> | 162–165 | <code>self.assertIn('SR011', self.rules_for(text, portable=True))</code> |
| <code>RuleTests.test_sr012_unknown_field</code> | 167–169 | <code>self.assertIn('SR012', self.rules_for(text))</code> |
| <code>RuleTests.test_sr020_duplicate_command_names</code> | 171–175 | <code>self.assertIn('SR020', {f.rule for f in findings})</code> |
| <code>RuleTests.test_sr021_near_duplicate_descriptions</code> | 177–185 | <code>self.assertIn('SR021', {f.rule for f in findings})</code> |
| <code>RuleTests.test_sr021_ignores_distinct_descriptions</code> | 187–193 | <code>self.assertNotIn('SR021', {f.rule for f in findings})</code> |
| <code>RuleTests.test_sr024_never_fired</code> | 195–200 | <code>self.assertIn('SR024', {f.rule for f in skillrot.analyze(skills, usage={})})</code><br><code>self.assertNotIn('SR024', {f.rule for f in skillrot.analyze(skills, usage={'deploy': 3})})</code> |
| <code>UsageTests.test_counts_skill_invocations_in_transcripts</code> | 204–214 | <code>self.assertEqual(counts['anthropic-skills:docx'], 2)</code> |
| <code>UsageTests.test_missing_transcript_dir_is_not_an_error</code> | 216–217 | <code>self.assertEqual(skillrot.usage_counts(Path('/nope/does/not/exist')), {})</code> |
| <code>UsageTests.test_resolve_usage_falls_back_to_bare_name</code> | 219–224 | <code>self.assertEqual(skillrot.resolve_usage(skill, {'docx': 5}), 5)</code><br><code>self.assertEqual(skillrot.resolve_usage(skill, {'myplugin:docx': 2, 'docx': 5}), 2)</code> |
| <code>BudgetTests.test_listing_cost_is_capped_at_the_spec_limit</code> | 228–233 | <code>self.assertLessEqual(capped, skillrot.LISTING_CHAR_CAP / 4 + 1)</code> |
| <code>BudgetTests.test_totals_add_up</code> | 235–249 | <code>self.assertEqual(totals.skills, 2)</code><br><code>self.assertEqual(totals.body_tokens, 300)</code><br><code>self.assertGreater(totals.always_on_tokens, 0)</code><br><code>self.assertAlmostEqual(totals.context_percent, 100 * totals.always_on_tokens / 200000, places=6)</code> |
| <code>BudgetTests.test_zero_context_window_does_not_divide_by_zero</code> | 251–253 | <code>self.assertEqual(totals.context_percent, 0.0)</code> |
| <code>DiscoveryTests.test_plugin_command_is_namespaced_from_manifest</code> | 257–268 | <code>self.assertEqual(skills[0].command, 'myplug:review')</code><br><code>self.assertEqual(skills[0].origin, 'plugin')</code> |
| <code>DiscoveryTests.test_plugin_name_falls_back_past_a_version_directory</code> | 270–275 | <code>self.assertEqual(skills[0].plugin, 'figma')</code> |
| <code>DiscoveryTests.test_frontmatter_name_sets_the_plugin_command_leaf</code> | 277–283 | <code>self.assertEqual(skills[0].command, 'myplug:fancy')</code> |
| <code>DiscoveryTests.test_same_skill_is_not_counted_twice</code> | 285–289 | <code>self.assertEqual(len(skillrot.discover([root, root, path])), 1)</code> |
| <code>DiscoveryTests.test_a_direct_file_path_is_accepted</code> | 291–294 | <code>self.assertEqual(len(skillrot.discover([path])), 1)</code> |
| <code>DiscoveryTests.test_relative_path_still_yields_a_command_name</code> | 296–307 | <code>self.assertEqual(skills[0].command, 'myskill')</code> |
| <code>CliTests.test_json_output_is_valid</code> | 319–324 | <code>self.assertEqual(payload['budget']['skills'], 1)</code><br><code>self.assertEqual(payload['skills'][0]['command'], 'deploy')</code> |
| <code>CliTests.test_exit_zero_on_clean_library</code> | 326–329 | <code>self.assertEqual(code, 0)</code><br><code>self.assertEqual(json.loads(out)['budget']['skills'], 1)</code> |
| <code>CliTests.test_fail_on_error_exits_nonzero</code> | 331–334 | <code>self.assertEqual(run_cli([str(self.root), '--no-usage', '--json', '--fail-on', 'error'])[0], 1)</code> |
| <code>CliTests.test_fail_over_budget_exits_nonzero_only_when_over</code> | 336–343 | <code>self.assertEqual(run_cli([str(self.root), '--no-usage', '--json', '--fail-over-budget'])[0], 0)</code><br><code>self.assertEqual(code, 1)</code> |
| <code>CliTests.test_missing_path_exits_two</code> | 345–346 | <code>self.assertEqual(run_cli([str(self.root / 'nope'), '--no-usage'])[0], 2)</code> |
| <code>CliTests.test_render_is_plain_text_without_color</code> | 348–354 | <code>self.assertNotIn('\x1b[', text)</code><br><code>self.assertIn('Context bill', text)</code> |
| <code>ClusterTests.test_identical_descriptions_form_one_cluster</code> | 363–368 | <code>self.assertEqual(len(clusters), 1)</code><br><code>self.assertEqual([s.command for s in clusters[0]], ['a', 'b', 'c'])</code> |
| <code>ClusterTests.test_distinct_descriptions_do_not_cluster</code> | 370–375 | <code>self.assertEqual(skillrot.cluster_by_description(skills, 0.8), [])</code> |
| <code>ClusterTests.test_separate_duplicate_pairs_stay_separate</code> | 377–385 | <code>self.assertEqual(sorted((len(c) for c in clusters)), [2, 2])</code> |
| <code>ClusterTests.test_single_skill_library_has_no_clusters</code> | 387–388 | <code>self.assertEqual(skillrot.cluster_by_description([self.make('a', 'x y z')], 0.8), [])</code> |
| <code>ClusterTests.test_one_finding_per_cluster_not_per_pair</code> | 390–395 | <code>self.assertEqual(len(findings), 1)</code><br><code>self.assertIn('5 skills', findings[0].message)</code> |
| <code>SymlinkStubTests.test_detects_a_path_only_file</code> | 399–400 | <code>self.assertTrue(skillrot._looks_like_symlink_stub('../../shared/skills/x/SKILL.md'))</code> |
| <code>SymlinkStubTests.test_ignores_real_markdown</code> | 402–404 | <code>self.assertFalse(skillrot._looks_like_symlink_stub('# Title\n\nSome prose.'))</code><br><code>self.assertFalse(skillrot._looks_like_symlink_stub(''))</code> |
| <code>SymlinkStubTests.test_reported_as_sr008_not_sr001</code> | 406–411 | <code>self.assertIn('SR008', rules)</code><br><code>self.assertNotIn('SR001', rules)</code> |
| <code>RenderLimitTests.test_findings_are_capped_per_rule</code> | 425–433 | <code>self.assertIn('and 20 more', capped)</code><br><code>self.assertNotIn('and 20 more', full)</code><br><code>self.assertEqual(full.count('SR022'), 25)</code> |
| <code>FoldedScalarTests.test_plain_scalar_folds_indented_continuations</code> | 437–444 | <code>self.assertEqual(problems, [])</code><br><code>self.assertEqual(fm['description'], 'First line and its folded continuation about when to use it.')</code> |
| <code>FoldedScalarTests.test_folded_description_is_seen_by_the_trigger_rule</code> | 446–454 | <code>self.assertNotIn('SR022', rules)</code> |
| <code>TriggerSourceTests.test_sr022_silent_when_trigger_is_in_when_to_use</code> | 458–464 | <code>self.assertNotIn('SR022', rules)</code> |
| <code>ListingBudgetTests.test_names_are_always_counted_even_over_budget</code> | 473–480 | <code>self.assertTrue(totals.overflows)</code><br><code>self.assertGreaterEqual(totals.always_on_tokens, totals.name_tokens)</code><br><code>self.assertEqual(totals.name_tokens, sum((skillrot._name_tokens(s, 4.0) for s in skills)))</code> |
| <code>ListingBudgetTests.test_name_only_skills_reported_as_sr030</code> | 482–487 | <code>self.assertTrue(sr030)</code> |
| <code>ListingBudgetTests.test_no_sr030_when_everything_fits</code> | 489–492 | <code>self.assertNotIn('SR030', {f.rule for f in findings})</code> |
| <code>ListingBudgetTests.test_most_used_descriptions_survive_the_budget</code> | 494–500 | <code>self.assertEqual([s.command for s in dropped], ['drop'])</code> |
| <code>BundleBytesTests.test_nested_skill_is_not_counted_in_parent_bundle</code> | 504–515 | <code>self.assertLess(total, 5000)</code> |
| <code>CommandNameTests.test_frontmatter_name_beats_directory_for_local_skills</code> | 519–523 | <code>self.assertEqual(skillrot.discover([Path(tmp)])[0].command, 'deploy')</code> |
| <code>CommandNameTests.test_same_name_in_two_dirs_is_a_command_collision</code> | 525–530 | <code>self.assertIn('SR020', rules)</code> |
| <code>ShallowDiscoveryTests.test_shallow_root_scans_one_level_only</code> | 534–542 | <code>self.assertEqual([s.path.parent.name for s in shallow], ['top'])</code><br><code>self.assertEqual(sorted((s.path.parent.name for s in deep)), ['buried', 'top'])</code> |
| <code>ManifestDiscoveryTests.test_marketplace_counts_only_what_the_manifest_installs</code> | 562–567 | <code>self.assertEqual(sorted((s.command for s in skills)), ['p:deploy', 'p:deploy'])</code><br><code>self.assertTrue(all((s.origin == 'plugin' for s in skills)))</code> |
| <code>ManifestDiscoveryTests.test_scan_all_still_counts_every_skill_md</code> | 569–572 | <code>self.assertEqual(len(skillrot.discover([Path(tmp)], scan_all=True)), 4)</code> |
| <code>ManifestDiscoveryTests.test_root_plugin_counts_when_marketplace_source_is_remote</code> | 574–586 | <code>self.assertEqual([s.command for s in skillrot.discover([root])], ['a:one'])</code> |
| <code>ManifestDiscoveryTests.test_remote_only_marketplace_does_not_count_local_catalog</code> | 588–595 | <code>self.assertEqual(len(skillrot.discover([root])), 0)</code> |
| <code>ManifestDiscoveryTests.test_plugin_root_skill_md_loads_as_single_skill</code> | 597–603 | <code>self.assertEqual(len(skillrot.discover([root])), 1)</code> |
| <code>CommandFileTests.test_plugin_commands_join_the_listing</code> | 614–618 | <code>self.assertEqual(found, {('p:review', 'skill'), ('p:ship', 'command')})</code> |
| <code>CommandFileTests.test_manifest_commands_key_replaces_the_default_folder</code> | 620–627 | <code>self.assertEqual(commands, {'p:lint'})</code> |
| <code>CommandFileTests.test_local_command_names_follow_the_path</code> | 629–636 | <code>self.assertEqual(names, ['deploy', 'frontend:component'])</code> |
| <code>CommandFileTests.test_command_without_frontmatter_is_not_an_error</code> | 638–642 | <code>self.assertEqual([f for f in findings if f.command == 'p:ship'], [])</code> |
| <code>CommandFileTests.test_skill_and_command_with_one_name_list_once</code> | 644–652 | <code>self.assertEqual(len(skills), 3)</code><br><code>self.assertEqual(len(skillrot._listed(skills)), 2)</code><br><code>self.assertIn('SR020', {f.rule for f in skillrot.analyze(skills)})</code> |
| <code>ListingVisibilityTests.test_disable_model_invocation_is_not_billed</code> | 662–667 | <code>self.assertEqual(totals.requested_tokens, alone.requested_tokens)</code><br><code>self.assertEqual(totals.hidden, 1)</code> |
| <code>ListingVisibilityTests.test_overrides_off_and_name_only</code> | 669–676 | <code>self.assertEqual(totals.hidden, 1)</code><br><code>self.assertEqual(totals.desc_tokens, 0)</code><br><code>self.assertNotIn('SR030', {f.rule for f in findings})</code> |
| <code>ListingVisibilityTests.test_missing_description_falls_back_to_first_body_line</code> | 678–681 | <code>self.assertEqual(skill.routing_text, 'Format tables')</code> |
| <code>InstalledPluginTests.test_enabled_plugins_resolve_through_cache_and_directory_marketplaces</code> | 685–708 | <code>self.assertEqual(sorted((s.command for s in skills)), ['cached:a', 'local:b'])</code> |
| <code>InstalledPluginTests.test_no_enabled_plugins_does_not_scan_disabled_cache</code> | 710–711 | <code>self.assertEqual(skillrot.installed_plugin_entries(Path('/nowhere'), {}), [])</code> |
| <code>InstalledPluginTests.test_settings_merge_project_over_user</code> | 713–727 | <code>self.assertEqual(merged['enabledPlugins'], {'a@m': True, 'b@m': True})</code><br><code>self.assertEqual(merged['skillListingBudgetFraction'], 0.02)</code> |
| <code>TypedCommandUsageTests.test_user_typed_slash_commands_count_as_invocations</code> | 731–736 | <code>self.assertEqual(skillrot.usage_counts(Path(tmp))['caveman:caveman'], 2)</code> |
| <code>SvgTests.test_svg_is_well_formed_xml</code> | 740–747 | <code>self.assertEqual(doc.documentElement.tagName, 'svg')</code> |
