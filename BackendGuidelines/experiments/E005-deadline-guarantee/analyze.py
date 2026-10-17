"""E005 analysis."""
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
d = pd.read_csv(HERE / "results" / "runs.csv")
d["truth_opt"] = d.truth_status == "OPTIMAL"
# zero late is known possible if CP-SAT proved 0, or any method produced a valid zero-late plan (a certificate)
cert = (d.construct_late == 0) | (d.repair_late == 0) | (d.repair_cpsat_late == 0) | \
       ((d.walls_late == 0) & (d.walls_violations == 0))
d["zero_possible"] = (d.truth_opt & (d.truth_late == 0)) | cert
d["zero_impossible"] = d.truth_opt & (d.truth_late > 0)
print("instances", len(d), "zero possible", int(d.zero_possible.sum()), "proven overload", int(d.zero_impossible.sum()),
      "unknown", int((~d.zero_possible & ~d.zero_impossible).sum()))
z = d[d.zero_possible]
print("\non instances where zero late is possible:")
for col in ("construct_late", "repair_late", "repair_cpsat_late", "walls_late", "penalty_late"):
    print(f"  {col:20s} zero-late rate {np.mean(z[col] == 0):.3f}  ({int((z[col] == 0).sum())}/{len(z)})")
print("  cpsat-15s truth zero  ", f"{np.mean((z.truth_late == 0)):.3f}")
print("\nby family (zero-possible instances): construct / repair / repair+cp / walls / cpsat-truth")
for fam, x in z.groupby("family"):
    print(f"  {fam:12s} n={len(x):2d} {np.mean(x.construct_late == 0):.2f} {np.mean(x.repair_late == 0):.2f} "
          f"{np.mean(x.repair_cpsat_late == 0):.2f} {np.mean(x.walls_late == 0):.2f} {np.mean(x.truth_late == 0):.2f}")
print("\nEDF vs truth:")
print("  EDF feasible but CP-SAT proved lateness:", int((d.edf_feasible & d.zero_impossible).sum()))
print("  EDF infeasible but zero late possible  :", int((~d.edf_feasible & d.zero_possible).sum()))
print("  EDF feasible, construct late, zero possible:", int((d.edf_feasible & (d.construct_late > 0) & d.zero_possible).sum()))
print("\nwalls vs penalty: lateness rose above the start:", int(d.walls_rose.sum()), "vs", int(d.penalty_rose.sum()),
      "; violations:", int((d.walls_violations > 0).sum()), "vs", int((d.penalty_violations > 0).sum()))
o = d[d.zero_impossible]
if len(o):
    print("\noverload (proven optimum > 0): ratio to optimum, median [max]; time")
    for col, tcol in (("construct_late", "construct_s"), ("repair_late", "repair_s"), ("repair_cpsat_late", "repair_cpsat_s"),
                      ("walls_late", None)):
        r = o[col] / o.truth_late
        print(f"  {col:20s} {np.median(r):.3f} [{r.max():.3f}]  t_med={o[tcol].median() if tcol else float('nan'):.3f}s")
    print(f"  cpsat truth time med {o.truth_s.median():.1f}s")
print("\ntimes (s): construct med", round(d.construct_s.median(), 4), "max", round(d.construct_s.max(), 4),
      "| repair med", round(d.repair_s.median(), 3), "| truth med", round(d.truth_s.median(), 1))
