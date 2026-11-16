"""Build TeX source packages for submission: arXiv (main.tex, article class) and Springer Nature Snapp (main-sn.tex, sn-jnl).

Run: ../.venv/bin/python make_submission.py [--pdflatex]
  -> paper/arxiv/ + paper/arxiv.tar.gz      (keeps the figures/ and tables/ subdirectories; arXiv accepts subdirectories)
  -> paper/springer/ + paper/springer.zip   (flat: every file at the top; Snapp takes a .zip and compiles with pdfLaTeX)
  -> paper/arxiv-metadata.txt               (arXiv form fields: title, authors, ASCII abstract <= 1920 characters)
- Figures are copied from ../results/figures and their paths rewritten in content.tex; TeX comments are removed from every .tex file.
- Includes the .bbl (arXiv does not run BibTeX) and refs.bib; the Springer package includes sn-jnl.cls and sn-mathphys-ay.bst.
- Each package is recompiled on its own to check that it stands alone (tectonic); --pdflatex also compiles with pdfLaTeX in Docker
  (texlive/texlive:latest-medium), the compiler arXiv and Snapp use. Reports any \todo left.
"""
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMMENT = re.compile(r"(?<!\\)%.*$")
SHARED = ["content.tex", "abstract.tex", "macros.tex"]
TARGETS = {
    "arxiv": {"main": "main", "extra": [], "flat": False, "tlmgr": []},
    # sn-jnl.cls needs these packages; they are in full TeX Live but not in the "medium" image
    "springer": {"main": "main-sn", "extra": ["sn-jnl.cls", "sn-mathphys-ay.bst"], "flat": True,
                 "tlmgr": ["sttools", "threeparttable", "appendix", "wrapfig"]},
}
TEXLIVE = "texlive/texlive:latest-medium"


def strip_comments(text):
    out = []
    for line in text.splitlines():
        if line.lstrip().startswith("%"):
            continue
        out.append(COMMENT.sub("%", line) if COMMENT.search(line) else line)
    return "\n".join(out) + "\n"


def build(name, main, extra, flat, tlmgr):
    out = HERE / name
    subprocess.run(["tectonic", "--keep-intermediates", f"{main}.tex"], cwd=HERE, check=True, capture_output=True)
    if out.exists():
        shutil.rmtree(out)
    fig_dir, tab_dir = (out, out) if flat else (out / "figures", out / "tables")
    for d in (out, fig_dir, tab_dir):
        d.mkdir(parents=True, exist_ok=True)
    for src in [f"{main}.tex"] + SHARED:
        text = (HERE / src).read_text()
        for fig in re.findall(r"\.\./results/figures/([\w.-]+)", text):
            shutil.copy2(HERE.parent / "results" / "figures" / fig, fig_dir / fig)
        text = text.replace("../results/figures/", "" if flat else "figures/")
        if flat:
            text = text.replace("\\input{tables/", "\\input{")
        (out / src).write_text(strip_comments(text))
    for t in (HERE / "tables").glob("*.tex"):
        (tab_dir / t.name).write_text(strip_comments(t.read_text()))
    for f in [f"{main}.bbl", "refs.bib"] + extra:
        shutil.copy2(HERE / f, out / f)
    for p in HERE.glob(f"{main}.*"):
        if p.suffix in (".aux", ".bbl", ".blg", ".out", ".toc"):
            p.unlink()
    check = subprocess.run(["tectonic", f"{main}.tex"], cwd=out, capture_output=True, text=True)
    (out / f"{main}.pdf").unlink(missing_ok=True)
    if check.returncode != 0:
        sys.exit(f"package {name} does not compile (tectonic):\n" + check.stderr[-2000:])
    files = sorted(p for p in out.rglob("*") if p.is_file())
    if flat:
        with zipfile.ZipFile(HERE / f"{name}.zip", "w", zipfile.ZIP_DEFLATED) as z:
            for p in files:
                z.write(p, arcname=p.name)
        archive = HERE / f"{name}.zip"
    else:
        with tarfile.open(HERE / f"{name}.tar.gz", "w:gz") as tar:
            for p in files:
                tar.add(p, arcname=str(p.relative_to(out)))
        archive = HERE / f"{name}.tar.gz"
    print(f"Package {name}: {out} and {archive} ({len(files)} files), standalone compile (tectonic): ok")
    return out, main, tlmgr


def pdflatex(out, main, tlmgr):
    """Compile as arXiv does (with .bbl, no BibTeX): pdflatex three times on a copy (arXiv and Snapp rerun until
    references settle), and report LaTeX errors and warnings from the last pass."""
    tmp = out.parent / f".{out.name}-pdflatex"
    if tmp.exists():
        shutil.rmtree(tmp)
    shutil.copytree(out, tmp)
    cmd = " && ".join([f"pdflatex -interaction=nonstopmode -halt-on-error {main}.tex >/dev/null"] * 3)
    if tlmgr:
        cmd = f"tlmgr install {' '.join(tlmgr)} >/dev/null 2>&1; " + cmd
    run = subprocess.run(["docker", "run", "--rm", "-v", f"{tmp}:/w", "-w", "/w", TEXLIVE, "sh", "-c", cmd],
                         capture_output=True, text=True)
    log = (tmp / f"{main}.log").read_text(errors="replace") if (tmp / f"{main}.log").exists() else ""
    version = re.search(r"pdfTeX, Version [^\n]*", log)
    warnings = re.findall(r"^(?:LaTeX|Package \w+) Warning:[^\n]*", log, re.M)
    ok = run.returncode == 0 and (tmp / f"{main}.pdf").exists()
    pages = re.search(r"Output written on [^(]*\((\d+) pages", log)
    shutil.rmtree(tmp)
    if not ok:
        sys.exit(f"{out.name}: pdfLaTeX loi\n" + "\n".join(l for l in log.splitlines() if l.startswith("!"))[:2000])
    print(f"  pdfLaTeX ({version.group(0) if version else '?'}): dat, {pages.group(1) if pages else '?'} trang, "
          f"{len(warnings)} canh bao LaTeX")
    for w in warnings:
        print("   ", w)


def arxiv_metadata():
    """arXiv form fields: ASCII text, no TeX commands; the abstract comes from abstract.tex, numbers from tables/numbers.tex."""
    macros = dict(re.findall(r"\\newcommand\{\\(\w+)\}\{([^}]*)\}", (HERE / "tables" / "numbers.tex").read_text()))
    text = (HERE / "abstract.tex").read_text()
    text = re.sub(r"\\(num\w+)(\{\})?", lambda m: macros[m.group(1)], text)
    text = re.sub(r"\\texttt\{([^}]*)\}", r"\1", text).replace("\\%", "%").replace("~", " ")
    abstract = " ".join(text.split())
    title = re.search(r"\\title\{(.*?)\}\n", (HERE / "main.tex").read_text(), re.S).group(1)
    title = " ".join(re.sub(r"\\\\(\[[^]]*\])?", " ", title).split())
    content = (HERE / "content.tex").read_text()
    n_fig, n_tab = content.count(r"\begin{figure}"), content.count(r"\begin{table}")
    info = subprocess.run(["pdfinfo", str(HERE / "main.pdf")], capture_output=True, text=True).stdout  # build() just produced it
    pages = re.search(r"Pages:\s+(\d+)", info)
    if "\\" in abstract + title or not (abstract + title).isascii() or len(abstract) > 1920:
        sys.exit(f"abstract not valid for arXiv ({len(abstract)} characters; needs ASCII and no TeX commands)")
    (HERE / "arxiv-metadata.txt").write_text(
        f"Title: {title}\nAuthors: Khanh Minh Man Pham\nPrimary category: cs.SE\n"
        f"Comments: {pages.group(1) + ' pages, ' if pages else ''}{n_fig} figures, {n_tab} tables\n\n"
        f"Abstract ({len(abstract)}/1920 characters):\n{abstract}\n")
    print(f"arXiv form fields: {HERE / 'arxiv-metadata.txt'} (abstract {len(abstract)} characters)")


def main():
    built = [build(name, **t) for name, t in TARGETS.items()]
    arxiv_metadata()
    if "--pdflatex" in sys.argv:
        for out, main_name, tlmgr in built:
            pdflatex(out, main_name, tlmgr)
    todos = sorted({" ".join(m.split()) for out, _, _ in built for p in out.rglob("*.tex")
                    for m in re.findall(r"\\todo\{([^}]*)\}", p.read_text())})
    for t in todos:
        print("  TODO LEFT (remove before submitting):", t)


if __name__ == "__main__":
    main()
