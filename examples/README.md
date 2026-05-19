# Examples

Minimal scripts demonstrating the two solver classes and the two input modes.

| Script | What it shows |
|---|---|
| [`basic_hgs.py`](basic_hgs.py) | Coordinate input → HGSSolver, 2 PD pairs |
| [`grubhub_matrix.py`](grubhub_matrix.py) | Explicit distance matrix → HGSSolver |

Run with:

```bash
pip install pdtsp
python examples/basic_hgs.py
python examples/grubhub_matrix.py
```

Both scripts cap the search at 2 seconds with a fixed seed, so they finish
quickly and produce identical output on repeated runs.
