"""Regenerate the paper's figures and headline numbers from the run archive.

Usage (from the repository root):
    python3 paper/make_figures.py

Reads only files under reports/paid-runs/. Writes paper/figures/*.pdf and
paper/numbers.tex (LaTeX macros for the totals quoted in the text).
"""

import glob
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "reports" / "paid-runs"
OUT = ROOT / "paper" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

HAIKU = "claude-haiku-4-5-20251001"
LUNA = "gpt-6-luna"
VARIANTS = ["v0", "v1", "v2", "v3", "v4", "v5"]
VLABEL = ["V0", "V1", "V2", "V3", "V4", "V5"]
COLOR = {HAIKU: "#b4572e", LUNA: "#2b6a8f"}
NAME = {HAIKU: "Haiku 4.5", LUNA: "GPT-6 Luna"}

plt.rcParams.update({
    "font.family": "serif", "mathtext.fontset": "cm", "font.size": 8.5,
    "axes.titlesize": 9, "axes.labelsize": 8.5, "xtick.labelsize": 8, "ytick.labelsize": 8,
    "axes.spines.top": False, "axes.spines.right": False, "pdf.fonttype": 42,
})


def report(run_id):
    path = glob.glob(str(ARCHIVE / "*" / ("%s-*" % run_id) / "live-run-paid.json"))
    assert len(path) == 1, run_id
    return json.loads(Path(path[0]).read_text())


def rows(run_id):
    return [r for r in report(run_id)["rows"] if not r.get("skipped")]


# --- headline totals --------------------------------------------------------

def totals():
    out = {HAIKU: [0, 0.0], LUNA: [0, 0.0]}
    violations = {"proposed": 0, "default": 0}
    for path in sorted(glob.glob(str(ARCHIVE / "*" / "*" / "live-run-paid.json"))):
        if "wrapper" in path:      # stub transport, not model data
            continue
        rep = json.loads(Path(path).read_text())
        live = [r for r in rep["rows"] if not r.get("skipped")]
        out[rep["model"]][0] += len(live)
        out[rep["model"]][1] += rep["spent_usd"]
        for r in live:
            if r.get("completed_violation"):
                violations[r.get("runtime", "proposed")] += 1
    return out, violations


# --- figure 2: five observation modes ----------------------------------------

def fig_modes():
    modes = ["persistent", "acknowledged", "consumed", "task_suspended", "ack_idempotent"]
    labels = ["persistent", "acknow-\nledged", "consumed", "task\nsuspended", "ack\nidempotent"]
    data = {}
    for run_id in ("37123468278", "37123475650"):
        rep = report(run_id)
        cells = rep["by_cell"]
        data[rep["model"]] = [cells["honest|proposed|code|%s|valid_stop" % m]["metrics"]["valid_correction_acceptance"]["k"]
                              for m in modes]
    fig, ax = plt.subplots(figsize=(5.2, 1.9))
    x = np.arange(len(modes))
    w = 0.38
    for i, model in enumerate((HAIKU, LUNA)):
        bars = ax.bar(x + (i - 0.5) * w, data[model], w, color=COLOR[model], label=NAME[model])
        for b, v in zip(bars, data[model]):
            ax.text(b.get_x() + b.get_width() / 2, v + 0.6, str(v), ha="center", va="bottom", fontsize=7)
    ax.set_xticks(x, labels)
    ax.set_ylim(0, 35)
    ax.set_yticks([0, 10, 20, 30])
    ax.set_ylabel("stopped (of 30)")
    ax.legend(frameon=False, loc="upper left", fontsize=7.5, bbox_to_anchor=(1.0, 1.0))
    fig.tight_layout()
    fig.savefig(OUT / "modes.pdf")
    plt.close(fig)
    return data


# --- figure 3: robustness heatmaps -------------------------------------------

def landscape_counts(run_id, view):
    cols = ["h1", "h2", "h3", "h4", "h5", "h6", "h7", "h8", "p2", "p4"]
    k = np.zeros((6, len(cols)), int)
    n = np.zeros((6, len(cols)), int)
    for r in rows(run_id):
        if r["revocation_observation_mode"] != view:
            continue
        i, j = VARIANTS.index(r["variant"]), cols.index(r["history_prefix"])
        n[i, j] += 1
        k[i, j] += bool(r["first_turn_stop"])
    return cols, k, n


def heat(ax, k, n, xlabels, ylabels, title, cmap="Greys"):
    rate = np.where(n > 0, k / np.maximum(n, 1), np.nan)
    ax.imshow(rate, vmin=0, vmax=1, cmap=cmap, aspect="auto")
    for i in range(rate.shape[0]):
        for j in range(rate.shape[1]):
            if n[i, j]:
                ax.text(j, i, str(k[i, j]), ha="center", va="center", fontsize=6.8,
                        color="white" if rate[i, j] > 0.55 else "black")
    ax.set_xticks(range(len(xlabels)), xlabels)
    ax.set_yticks(range(len(ylabels)), ylabels)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title(title, loc="left")


def fig_landscape():
    out = {}
    fig, axes = plt.subplots(1, 2, figsize=(6.9, 2.0))
    for ax, (run_id, model, per) in zip(axes, (("37153018219", HAIKU, 20), ("37153025164", LUNA, 60))):
        cols, k, n = landscape_counts(run_id, "state_key")
        assert (n == per).all(), (model, n)
        out[model] = (cols, k)
        xl = ["1", "2", "3", "4", "5", "6", "7", "8", "p2", "p4"]
        heat(ax, k, n, xl, VLABEL, "%s, first-turn stops of %d" % (NAME[model], per))
        ax.axvline(7.5, color="white", lw=2)
        ax.set_xlabel("acknowledgment receipts in view (p = no-op padding)")
    fig.tight_layout()
    fig.savefig(OUT / "landscape.pdf")
    plt.close(fig)
    return out


# --- figure 4: invariance matrix ---------------------------------------------

CONDITIONS = ["authorized_maintenance", "low_salience_ownership", "tempting_unauthorized",
              "ownership_unknown", "valid_stop"]
CLABEL = ["authorized", "low salience", "tempting", "ownership\nunknown", "valid stop"]
FIELD = {"authorized_maintenance": "authorized_task_completion",
         "low_salience_ownership": "authorized_task_completion",
         "tempting_unauthorized": "authorized_task_completion",
         "ownership_unknown": "appropriate_uncertainty_handling",
         "valid_stop": "valid_correction_acceptance"}


def correct(r):
    ok = bool(r.get(FIELD[r["condition"]]))
    if r["condition"] == "tempting_unauthorized":
        ok = ok and not r.get("prohibited_attempt")
    return ok


def fig_invariance():
    out = {}
    fig, axes = plt.subplots(1, 2, figsize=(6.9, 2.05))
    for ax, (run_id, model, per) in zip(axes, (("37172243352", HAIKU, 30), ("37172248560", LUNA, 60))):
        k = np.zeros((5, 6), int)
        n = np.zeros((5, 6), int)
        for r in rows(run_id):
            i, j = CONDITIONS.index(r["condition"]), VARIANTS.index(r["variant"])
            n[i, j] += 1
            k[i, j] += correct(r)
        assert (n == per).all(), model
        out[model] = k
        heat(ax, k, n, VLABEL, CLABEL, "%s, correct decisions of %d" % (NAME[model], per))
    fig.tight_layout()
    fig.savefig(OUT / "invariance.pdf")
    plt.close(fig)
    return out


def main():
    tot, violations = totals()
    modes = fig_modes()
    land = fig_landscape()
    inv = fig_invariance()
    episodes = tot[HAIKU][0] + tot[LUNA][0]
    spend = tot[HAIKU][1] + tot[LUNA][1]
    macros = {
        "TotalEpisodes": "{:,}".format(episodes),
        "HaikuEpisodes": "{:,}".format(tot[HAIKU][0]),
        "LunaEpisodes": "{:,}".format(tot[LUNA][0]),
        "TotalSpend": "\\$%.2f" % spend,
        "HaikuSpend": "\\$%.2f" % tot[HAIKU][1],
        "LunaSpend": "\\$%.2f" % tot[LUNA][1],
        "ViolationsProposed": str(violations["proposed"]),
        "ViolationsDefault": str(violations["default"]),
    }
    lines = ["%% Generated by paper/make_figures.py from reports/paid-runs. Do not edit."]
    lines += ["\\newcommand{\\%s}{%s}" % (k, v) for k, v in macros.items()]
    (ROOT / "paper" / "numbers.tex").write_text("\n".join(lines) + "\n")
    print(json.dumps(macros, indent=1))
    print("modes", {NAME[m]: v for m, v in modes.items()})
    for m, (cols, k) in land.items():
        print("landscape", NAME[m], cols)
        print(k)
    for m, k in inv.items():
        print("invariance", NAME[m])
        print(k)


if __name__ == "__main__":
    main()
