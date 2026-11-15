"""Compara el código de esta carpeta con la versión del profesor (solo lectura) y escribe
docs/comparacion-profesor.md separado en tres grupos:
  (a) diferencias de plataforma (.venv/Scripts vs .venv/bin, CRLF, salto final de archivo)
  (b) desviaciones ya documentadas en el README
  (c) cualquier otra diferencia

No abre archivos con secretos (nombre con «.env» o «secretos») ni nada de las carpetas excluidas.
Uso: .venv/Scripts/python spikes/comparar_profesor.py "<ruta a sesion04 del profesor>"
"""
import difflib
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PROF = Path(sys.argv[1])

DIRS_EXCLUIDOS = {".venv", "node_modules", "salida", "app", "spikes", "docs", ".idea", "__pycache__", ".git",
                  ".pytest_cache", "ejemplos_salidas", "test-results"}
RUTAS_EXCLUIDAS = {"ejemplos/salidas"}
ARCHIVOS_EXCLUIDOS = {".DS_Store", "auditoria.jsonl"}
MAX_LINEAS_DIFF = 70

# Desviaciones documentadas en el README (grupo b): ruta -> motivo
GRUPO_B = {
    ".claude/settings.json": "deny del señuelo se conserva; sin pip/uv en allow; sin permisos mcp__directorio__",
    "hooks/rol.py": "compara programas por prefijo (Windows)",
    "hooks/roles.py": "programas con prefijo `.venv/Scripts/python -m pytest` (Windows)",
    "verificacion/comun.py": "decodifica la salida de subprocesos en UTF-8",
    "verificacion/__main__.py": "imprime en UTF-8",
    ".mcp.json": "fuera del repo (conexión local con PyCharm)",
}
PREFIJOS_B = (("ejemplos/", "ejemplos/ no se implementó"),)


def secreto(ruta: Path) -> bool:
    nombre = ruta.name.lower()
    return ".env" in nombre or "secretos" in nombre


def archivos(base: Path) -> dict[str, Path]:
    res = {}
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(base)
        if set(rel.parts[:-1]) & DIRS_EXCLUIDOS or p.name in ARCHIVOS_EXCLUIDOS or secreto(p):
            continue
        if any(rel.as_posix().startswith(x) for x in RUTAS_EXCLUIDAS):
            continue
        res[rel.as_posix()] = p
    return res


def texto(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None                                        # binario: solo se compara por bytes


def plano(t: str) -> str:
    """Texto sin diferencias de plataforma: CRLF, ruta del entorno y salto de línea final."""
    t = t.replace("\r\n", "\n").replace("\\", "/")
    t = t.replace(".venv/Scripts/python.exe", ".venv/bin/python").replace(".venv/Scripts/python", ".venv/bin/python")
    return t.rstrip("\n") + "\n"


def secciones(md: str) -> dict[str, str]:
    partes, titulo, buf = {}, "(título)", []
    for linea in plano(md).splitlines():
        if linea.startswith("## "):
            partes[titulo] = "\n".join(buf).strip()
            titulo, buf = linea[3:].strip(), []
        else:
            buf.append(linea)
    partes[titulo] = "\n".join(buf).strip()
    return partes


def diff(mio: str, prof: str, etiqueta_mia="esta carpeta", etiqueta_prof="profesor") -> str:
    lineas = list(difflib.unified_diff(plano(prof).splitlines(), plano(mio).splitlines(),
                                       f"profesor/{etiqueta_prof}", f"mio/{etiqueta_mia}", lineterm="", n=1))
    extra = len(lineas) - MAX_LINEAS_DIFF
    if extra > 0:
        lineas = lineas[:MAX_LINEAS_DIFF] + [f"... ({extra} líneas más)"]
    return "\n".join(lineas)


mios, profs = archivos(RAIZ), archivos(PROF)
solo_mio = sorted(set(mios) - set(profs))
solo_prof = sorted(set(profs) - set(mios))
comunes = sorted(set(mios) & set(profs))

grupo_a, grupo_b, grupo_c = [], [], []          # (ruta, detalle)
iguales = 0
for rel in comunes:
    tm, tp = texto(mios[rel]), texto(profs[rel])
    if tm is None or tp is None:
        if mios[rel].read_bytes() != profs[rel].read_bytes():
            grupo_c.append((rel, "binario distinto"))
        else:
            iguales += 1
        continue
    if rel == "README.md":
        continue                                   # se compara por secciones, más abajo
    if tm == tp:
        iguales += 1
    elif plano(tm) == plano(tp):
        grupo_a.append((rel, "solo plataforma (CRLF / .venv/Scripts / salto final)"))
    else:
        d = diff(tm, tp, rel, rel)
        (grupo_b if rel in GRUPO_B else grupo_c).append((rel, d))

for rel in solo_mio + solo_prof:
    lado = "solo en esta carpeta" if rel in solo_mio else "solo en el profesor"
    motivo = next((m for pre, m in PREFIJOS_B if rel.startswith(pre)), GRUPO_B.get(rel))
    (grupo_b if motivo else grupo_c).append((rel, f"{lado}" + (f" · {motivo}" if motivo else "")))

# README por secciones
sm, sp = secciones(mios["README.md"].read_text(encoding="utf-8")), \
         secciones(profs["README.md"].read_text(encoding="utf-8")) if "README.md" in profs else {}
readme_solo_mio = [s for s in sm if s not in sp]
readme_solo_prof = [s for s in sp if s not in sm]
readme_dist = [s for s in sm if s in sp and sm[s] != sp[s]]
readme_igual = [s for s in sm if s in sp and sm[s] == sp[s]]

out = ["# Comparación con la versión del profesor (sesion04)", "",
       "Solo lectura. Excluido: .venv, node_modules, salida/, app/, spikes/, docs/, .idea, __pycache__, .git, "
       "archivos con secretos.", "",
       f"- Archivos comparados: {len(set(mios) | set(profs))} · idénticos: {iguales} · "
       f"solo en esta carpeta: {len(solo_mio)} · solo en el profesor: {len(solo_prof)}", ""]

out += ["## (a) Diferencias de plataforma", ""]
out += [f"- `{r}` — {d}" for r, d in grupo_a] or ["- ninguna"]
out += ["", "## (b) Desviaciones ya documentadas en el README", ""]
for r, d in grupo_b:
    out += [f"### `{r}`" + (f" — {GRUPO_B[r]}" if r in GRUPO_B else ""), "", "```diff" if "\n" in d or d.startswith("---") else "", d,
            "```" if "\n" in d or d.startswith("---") else "", ""]
if not grupo_b:
    out += ["- ninguna", ""]
out += ["## (c) Otras diferencias", ""]
for r, d in grupo_c:
    out += [f"### `{r}`", "", "```diff" if d.startswith("---") else "", d, "```" if d.startswith("---") else "", ""]
if not grupo_c:
    out += ["- ninguna", ""]

out += ["## README.md por secciones", "",
        f"- Iguales (normalizando plataforma): {', '.join(readme_igual) or 'ninguna'}",
        f"- Distintas: {', '.join(readme_dist) or 'ninguna'}",
        f"- Solo en esta carpeta: {', '.join(readme_solo_mio) or 'ninguna'}",
        f"- Solo en el profesor: {', '.join(readme_solo_prof) or 'ninguna'}", ""]

destino = RAIZ / "docs" / "comparacion-profesor.md"
destino.write_text("\n".join(out), encoding="utf-8")
print(f"Reporte escrito en {destino.relative_to(RAIZ)}")
print(f"idénticos={iguales} (a)={len(grupo_a)} (b)={len(grupo_b)} (c)={len(grupo_c)} "
      f"solo_mio={len(solo_mio)} solo_prof={len(solo_prof)}")
