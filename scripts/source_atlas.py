"""Generate a local, searchable explanation of every executable source line.

This documentation tool uses only the standard library. It never imports or executes
the inspected files. Python descriptions follow syntax trees; configuration/demo
details are accompanied by the manually reviewed reverse-engineering reports.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import html
import json
from pathlib import Path
from typing import Dict, List, Tuple


SOURCE_SUFFIXES = {".py", ".toml", ".yml", ".yaml", ".html", ".in"}
EXCLUDED = {".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist",
            ".mypy_cache", ".ruff_cache", ".pytest_cache"}


def expression(node: ast.AST) -> str:
    try:
        text = ast.unparse(node)
    except (ValueError, RecursionError):
        text = type(node).__name__
    return text if len(text) <= 180 else text[:177] + "..."


def explain(node: ast.AST) -> str:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return "Визначає функцію {}({}); її інструкції виконуються при виклику.".format(
            node.name, ", ".join(argument.arg for argument in node.args.args))
    if isinstance(node, ast.ClassDef):
        return "Визначає клас {}; об'єднує стан і методи цього компонента.".format(node.name)
    if isinstance(node, ast.Import):
        return "Імпортує модулі: {}.".format(", ".join(alias.name for alias in node.names))
    if isinstance(node, ast.ImportFrom):
        return "Імпортує {} з {}.".format(", ".join(alias.name for alias in node.names), node.module)
    if isinstance(node, ast.Assign):
        return "Обчислює {} і зберігає результат у {}.".format(
            expression(node.value), ", ".join(expression(target) for target in node.targets))
    if isinstance(node, ast.AnnAssign):
        return "Оголошує {} типу {}{}.".format(expression(node.target), expression(node.annotation),
            "; присвоює " + expression(node.value) if node.value is not None else "")
    if isinstance(node, ast.AugAssign):
        return "Оновлює {} операцією {} із {}.".format(
            expression(node.target), type(node.op).__name__, expression(node.value))
    if isinstance(node, ast.If):
        return "Виконує гілку лише якщо {} істинне; else задає альтернативу.".format(expression(node.test))
    if isinstance(node, (ast.For, ast.AsyncFor)):
        return "Перебирає {}; поточний елемент доступний як {}.".format(
            expression(node.iter), expression(node.target))
    if isinstance(node, ast.While):
        return "Повторює цикл, поки {} істинне.".format(expression(node.test))
    if isinstance(node, (ast.With, ast.AsyncWith)):
        return "Відкриває контекст {} і забезпечує вихід із нього після блоку.".format(
            ", ".join(expression(item.context_expr) for item in node.items))
    if isinstance(node, ast.Try):
        return "Починає блок контрольованих винятків; except/finally визначають відновлення/очищення."
    if isinstance(node, ast.ExceptHandler):
        return "Обробляє винятки {}{}.".format(expression(node.type) if node.type else "всіх типів",
            " під ім'ям " + node.name if node.name else "")
    if isinstance(node, ast.Return):
        return "Завершує функцію та повертає {}.".format(expression(node.value) if node.value else "None")
    if isinstance(node, ast.Raise):
        return "Перериває поточну операцію винятком {}.".format(expression(node.exc) if node.exc else "з попереднього except")
    if isinstance(node, ast.Assert):
        return "Перевіряє інваріант {}; порушення дає AssertionError.".format(expression(node.test))
    if isinstance(node, ast.Expr):
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return "Документує призначення/контракт компонента (рядковий літерал/docstring)."
        return "Виконує вираз {}; результат окремо не зберігається.".format(expression(node.value))
    if isinstance(node, ast.Continue):
        return "Переходить до наступного елемента поточного циклу."
    if isinstance(node, ast.Break):
        return "Завершує поточний цикл."
    if isinstance(node, ast.Pass):
        return "Залишає цей блок без додаткової дії."
    if isinstance(node, ast.Delete):
        return "Видаляє прив'язку/елемент {}.".format(", ".join(expression(target) for target in node.targets))
    return "Синтаксичний елемент {}: {}.".format(type(node).__name__, expression(node))


def python_lines(text: str) -> Dict[int, str]:
    tree = ast.parse(text)
    descriptions: Dict[int, Tuple[int, str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.stmt, ast.ExceptHandler)):
            continue
        start = node.lineno
        end = getattr(node, "end_lineno", start) or start
        size = end - start
        description = explain(node)
        for line in range(start, end + 1):
            if line not in descriptions or size < descriptions[line][0]:
                descriptions[line] = (size, description)
    return {line: description for line, (_, description) in descriptions.items()}


def annotate(line: str, number: int, suffix: str, descriptions: Dict[int, str]) -> str:
    stripped = line.strip()
    if not stripped:
        return "Порожній рядок: відокремлює логічні блоки; дій не виконує."
    if stripped.startswith("#") and suffix != ".html":
        return "Коментар автора; пояснює намір або обмеження, не виконується."
    if suffix == ".py":
        if stripped.startswith("@"):
            return "Декоратор {}; змінює спосіб створення/виклику наступної функції або класу.".format(stripped[1:])
        if stripped.startswith("else:"):
            return "Альтернативна гілка попередньої умови/циклу."
        if stripped.startswith("finally:"):
            return "Гілка очищення, яка виконується незалежно від винятку."
        return descriptions.get(number, "Продовження багаторядкового виразу або літерала; див. сусідні інструкції.")
    if suffix == ".toml":
        if stripped.startswith("["):
            return "Вибирає таблицю/секцію TOML, до якої належать наступні параметри."
        if "=" in stripped:
            return "Задає параметр {}; значення визначає метадані/пакування інструмента.".format(stripped.split("=", 1)[0].strip())
        return "Продовжує список/значення TOML; детальний контракт описано в delivery-звіті."
    if suffix in (".yml", ".yaml"):
        if stripped.startswith("- uses:"):
            return "Запускає вказаний GitHub Action як крок workflow."
        if stripped.startswith("- name:"):
            return "Називає наступний крок CI; його команди/умови наведено нижче."
        if ":" in stripped:
            return "Задає YAML-поле {} або починає його вкладений блок.".format(stripped.split(":", 1)[0])
        return "Елемент матриці/списку або рядок shell-скрипта CI; див. delivery-звіт для потоку виконання."
    if suffix == ".in":
        return "Правило setuptools manifest: включає або виключає ресурси source distribution."
    if not suffix:
        return "Шаблон .gitignore: виключає відповідні локальні/згенеровані файли зі звичайного Git tracking."
    if "<script" in stripped or "addEventListener" in stripped:
        return "Оголошує/підключає поведінку інтерактивної демонстрації в браузері."
    if "<style" in stripped or "{" in stripped:
        return "Описує стилі/код демонстрації; повний потік і обмеження пояснено в delivery-звіті."
    return "Розмітка/вміст історичної HTML-демонстрації; не бере участі в runtime CLI."


def generate(root: Path, output: Path) -> None:
    sources: List[dict] = []
    sections: List[str] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if (not path.is_file() or (path.suffix not in SOURCE_SUFFIXES and path.name != ".gitignore")
                or any(part in EXCLUDED for part in relative.parts)
                or "audit" in relative.parts):
            continue
        data = path.read_bytes()
        content = data.decode("utf-8")
        lines = content.splitlines()
        descriptions = python_lines(content) if path.suffix == ".py" else {}
        sources.append({"path": relative.as_posix(), "sha256": hashlib.sha256(data).hexdigest(),
                        "bytes": len(data), "lines": len(lines)})
        rows = []
        for number, line in enumerate(lines, 1):
            rows.append('<tr id="f{}-l{}"><td>{}</td><td><code>{}</code></td><td>{}</td></tr>'.format(
                len(sources), number, number, html.escape(line),
                html.escape(annotate(line, number, path.suffix, descriptions))))
        sections.append('<details><summary>{} — {} рядків</summary><div class="scroll"><table>{}</table></div></details>'.format(
            html.escape(relative.as_posix()), len(lines), "".join(rows)))
    output.mkdir(parents=True, exist_ok=True)
    inventory = {"schema_version": 1, "source_files": sources,
                 "total_files": len(sources), "total_lines": sum(item["lines"] for item in sources)}
    (output / "source-inventory.json").write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    document = '''<!doctype html><html lang="uk"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Skillrot — атлас вихідного коду</title>
<style>body{background:#0f172a;color:#e2e8f0;font:15px system-ui;margin:0;padding:24px}
header{max-width:1100px;margin:0 auto 24px}h1{font-size:32px}p{line-height:1.6;color:#cbd5e1}
input,button{font:inherit;border:1px solid #475569;border-radius:6px;padding:10px;background:#1e293b;color:#f8fafc}
input{width:min(540px,70%)}button{cursor:pointer}details{background:#17233b;border:1px solid #334155;border-radius:8px;margin:10px 0}
summary{cursor:pointer;padding:15px;font-weight:650}.scroll{overflow:auto}table{border-collapse:collapse;table-layout:fixed;width:100%;font-size:13px}
td{border-top:1px solid #334155;vertical-align:top;padding:7px 10px}td:first-child{color:#94a3b8;text-align:right;width:48px}
td:nth-child(2){width:55%}td:last-child{line-height:1.5;color:#cbd5e1}code{display:block;overflow:auto;white-space:pre;font:13px Consolas,monospace;color:#a5f3fc}
.hidden{display:none}a{color:#7dd3fc}.meta{color:#a7f3d0}</style>
<header><h1>Skillrot · атлас вихідного коду</h1><p class="meta">FILES файлів · LINES рядків · Python 3.9+ · offline</p>
<p>Кожен рядок коду доступний з номером та поясненням його синтаксичної дії. Python розібрано через AST без виконання.
Пояснення AST не замінюють ручний аналіз алгоритмів: читайте CORE_REVERSE_ENGINEERING.md і DELIVERY_REVERSE_ENGINEERING.md.
Конфігурацію та історичну HTML-демонстрацію пояснено вручну у delivery-звіті. SHA256 кожного файлу збережено у source-inventory.json.</p>
<p>Це знімок перевіреного дерева: після змін виконайте python scripts/source_atlas.py. Зовнішні бібліотеки, Git-історія
та бінарні медіафайли не є виконуваним кодом цього продукту й до таблиць не включені.</p>
<input id="query" placeholder="Шукати файл, функцію, правило чи фрагмент коду" aria-label="Пошук коду">
<button id="expand">Розгорнути видимі файли</button> <button id="collapse">Згорнути</button><p id="count"></p></header>
<main>SECTIONS</main><script>
const blocks=[...document.querySelectorAll('details')],query=document.getElementById('query');
query.addEventListener('input',()=>{const value=query.value.toLowerCase();let visible=0;
blocks.forEach(block=>{const match=block.textContent.toLowerCase().includes(value);block.classList.toggle('hidden',!match);if(match)visible++});
document.getElementById('count').textContent=visible+' файлів відповідають пошуку';});
document.getElementById('expand').onclick=()=>blocks.filter(b=>!b.classList.contains('hidden')).forEach(b=>b.open=true);
document.getElementById('collapse').onclick=()=>blocks.forEach(b=>b.open=false);
</script></html>'''
    document = document.replace("FILES", str(inventory["total_files"])).replace("LINES", str(inventory["total_lines"]))
    (output / "SOURCE_ATLAS.html").write_text(document.replace("SECTIONS", "".join(sections)), encoding="utf-8")
    print("{} files, {} lines -> {}".format(inventory["total_files"], inventory["total_lines"], output))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    root = args.root.resolve()
    generate(root, args.output or root / "docs" / "audit")


if __name__ == "__main__":
    main()
