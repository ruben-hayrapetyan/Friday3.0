"""Concatenate report/sections/*.md into REPORT.md."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parts = sorted((ROOT / "report" / "sections").glob("*.md"))
head = """# Friday v3 engine: research report

A research program on rebuilding Friday's scheduling engine around an energy-based (Boltzmann) model with a logical supervisor,
tested against a faithful build of the v2 CP-SAT engine on one shared evaluator. Everything here traces to an experiment folder
(`experiments/E###-*/`, index in section 13); figures are in `report/figures/`; the code is in `src/fr/`.

"""
(ROOT / "REPORT.md").write_text(head + "\n\n".join(p.read_text().strip() for p in parts) + "\n")
print("REPORT.md:", sum(1 for _ in (ROOT / "REPORT.md").open()), "lines from", [p.name for p in parts])
