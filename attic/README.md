Superseded solvers, kept rather than deleted so a number in an old chat can
still be reproduced.

  solve.py          -> solve2.py (leg pool factored out into board.py)
  fd20to1.py        -> solve2.py --target
  fd20to1_f5.py     -> solve2.py with drop_fam
  build25.py        -> solve2.py
  verify_f5.py      -> verify2.py

Nothing in the live path imports any of these. Slip grading, which several of
them did inline and inconsistently, now lives in slips.py.
