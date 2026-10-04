# Paper: Authority Should Survive Rewording

LaTeX source for the paper written from the studies in this repository.
`main.tex` is the current version, rebuilt from the author's rewrite.
`first-draft.tex` (*Same Authority, Different Text*) is the first draft, kept
for the record.

| File | What it is |
| --- | --- |
| `main.tex` | The paper |
| `refs.bib` | References |
| `make_figures.py` | Regenerates `tables/*.tex` (the shaded count tables), `figures/*.pdf` and `numbers.tex` (the totals quoted in the text) from `reports/paid-runs/` |
| `numbers.tex`, `tables/`, `figures/` | Generated; do not edit by hand |
| `main.pdf` | The compiled paper |
| `first-draft.tex`, `first-draft.pdf` | The first draft |

Build, from the repository root:

```sh
python3 paper/make_figures.py
cd paper && latexmk -pdf main.tex
```

Needs Python 3 with matplotlib and numpy, and a TeX installation with
`mathpazo`, `tikz`, `natbib`, `booktabs`, `tabularx`, `float`, `caption`, `colortbl`, `tcolorbox` and `titlesec`.

Every count in the figures and the totals is computed from the archived run
reports. Counts quoted in the text and tables were checked against the
archived reports, the checker outputs and the results documents in `docs/`.
