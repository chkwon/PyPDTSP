"""Minimal PyPDTSP example: 4 customers, 2 pickup-delivery pairs.

Run with `python examples/basic_hgs.py` after `pip install pdtsp`.
"""
from pdtsp import HGSParameters, HGSSolver


def main() -> None:
    # Index 0 is the depot. Customers 1-4 form two PD pairs:
    #   pickup 1 -> delivery 3
    #   pickup 2 -> delivery 4
    data = {
        "x_coordinates": [0.0, 1.0, 2.0, 1.0, 2.0],
        "y_coordinates": [0.0, 1.0, 0.0, 0.0, 1.0],
        "pickup_delivery_pairs": [(1, 3), (2, 4)],
    }

    solver = HGSSolver(HGSParameters(time_limit=2, seed=42, it=10_000))
    result = solver.solve(data)

    print(f"Cost:    {result.cost}")
    print(f"Time:    {result.time:.3f}s (solver-reported)")
    print(f"Route:   {result.route}")


if __name__ == "__main__":
    main()
