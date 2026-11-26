"""Control de seguridad del repositorio — ejecutar antes de cada commit.

Revisa los archivos que Git versionaría (tracked + staged; o, con --all, todo lo que .gitignore no excluye)
y falla si encuentra:
  - tipos prohibidos (Excel, CSV, PDF, Word, imágenes, comprimidos)
  - carpetas de datos (data/, source/, deliverables/, validation/, continuity/, work/, archive/)
  - JSON que no sea scripts/config.json o examples/*.example.json; scripts/audit_sources.json (registro privado)
  - rutas personales absolutas (Google Drive, carpetas de usuario), correos, tokens, llaves privadas
  - números largos tipo cuenta/tarjeta (10+ dígitos) y montos grandes con separadores (>= 1.000.000)
Código de salida 1 si encuentra algo. No se omite: se corrige el archivo o se excluye.

Uso:  python scripts/repo_safety_check.py          (dentro del repositorio git)
      python scripts/repo_safety_check.py --all    (todo archivo no ignorado de la carpeta)
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FORBIDDEN_EXT = {".csv", ".tsv", ".xlsx", ".xlsm", ".xls", ".docx", ".doc", ".pdf", ".png", ".jpg", ".jpeg", ".gif",
                 ".zip", ".tgz", ".gz", ".gscript", ".pem", ".key", ".pfx", ".p12", ".log"}
DATA_DIRS = ("data/", "source/", "deliverables/", "validation/", "continuity/", "work/", "archive/")
ALLOWED_JSON = re.compile(r"^(scripts/config\.json|examples/[^/]+\.example\.json)$")
PATTERNS = {
    "personal_path": re.compile(r"(?i)(?:[A-Z]:\\(?:My Drive|Users\\[^\\\s]+)|/Users/[^/\s]+|My Drive\\Personal Finance)"),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "long_number": re.compile(r"(?<![\w.])\d{10,}(?![\w.])"),
    "amount": re.compile(r"\b\d{1,3}(?:[.,]\d{3}){2,}(?:[.,]\d{1,2})?\b"),
}
# Literales sintéticos permitidos (cuentas de ejemplo y el ejemplo de materialidad del procedimiento)
ALLOW = re.compile(r"^(999000000\d{4}|1\.000\.000|1,000,000|1\.234\.567,00|1,234,567\.00)$")
SELF = "scripts/repo_safety_check.py"
VENDOR = "js/vendor/"


def candidate_files(scan_all: bool) -> list[str]:
    def git(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    inside = git("rev-parse", "--is-inside-work-tree").returncode == 0
    if inside and not scan_all:
        files = set(git("ls-files").stdout.splitlines()) | set(git("diff", "--cached", "--name-only").stdout.splitlines())
        return sorted(f for f in files if f)
    if not inside:
        sys.exit("Ejecute `git init` primero: --all usa .gitignore (git check-ignore) para decidir qué se versionaría.")
    r = git("ls-files", "--others", "--cached", "--exclude-standard")
    return sorted(f for f in r.stdout.splitlines() if f)


def check(files: list[str]) -> list[str]:
    problems = []
    for f in files:
        low = f.lower()
        ext = os.path.splitext(low)[1]
        if ext in FORBIDDEN_EXT:
            problems.append(f"{f}: tipo de archivo prohibido '{ext}'")
            continue
        if low.startswith(DATA_DIRS):
            problems.append(f"{f}: carpeta de datos privada")
            continue
        if low == "scripts/audit_sources.json":
            problems.append(f"{f}: registro privado de productos")
            continue
        if os.path.basename(low).startswith(".env"):
            problems.append(f"{f}: archivo de entorno")
            continue
        if ext == ".json" and not ALLOWED_JSON.match(f):
            problems.append(f"{f}: JSON no permitido (puede contener cifras financieras)")
            continue
        if f == SELF or f.startswith(VENDOR):
            continue
        path = os.path.join(ROOT, f)
        if not os.path.isfile(path):
            continue
        try:
            text = open(path, encoding="utf-8").read()
        except UnicodeDecodeError:
            problems.append(f"{f}: archivo binario o no UTF-8")
            continue
        for name, rx in PATTERNS.items():
            for m in rx.finditer(text):
                if ALLOW.match(m.group(0)):
                    continue
                line = text.count("\n", 0, m.start()) + 1
                problems.append(f"{f}:{line}: {name} -> {m.group(0)[:40]}")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="revisar todo archivo no ignorado, no solo tracked/staged")
    a = ap.parse_args()
    sys.stdout.reconfigure(errors="backslashreplace")
    files = candidate_files(a.all)
    problems = check(files)
    print(f"Archivos revisados: {len(files)}")
    if problems:
        print("REPOSITORY SAFETY CHECK: FAIL")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("REPOSITORY SAFETY CHECK: PASS")


if __name__ == "__main__":
    main()
