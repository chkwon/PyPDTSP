"""PyPDTSP with an explicit distance matrix (the `--grubhub` input format).

Pickup/delivery pairs are implicit in matrix mode: odd-indexed nodes are
pickups, paired with the next even-indexed delivery. Node 0 is the depot.
The matrix must therefore be of dimension `1 + 2k` for `k` pairs.
"""
from pdtsp import HGSParameters, HGSSolver


def main() -> None:
    # 1 depot + 4 customers => 2 implicit pairs: (1,2) and (3,4).
    # Distances are arbitrary integers; upstream rounds non-integers anyway.
    distance_matrix = [
        [0, 10, 12, 15, 18],
        [10, 0,  5,  7, 11],
        [12, 5,  0,  6,  8],
        [15, 7,  6,  0,  4],
        [18, 11, 8,  4,  0],
    ]
    data = {
        "distance_matrix": distance_matrix,
        "name": "demo-grubhub",
    }

    result = HGSSolver(HGSParameters(time_limit=2, seed=42, it=10_000)).solve(data)

    print(f"Cost:    {result.cost}")
    print(f"Time:    {result.time:.3f}s (solver-reported)")
    print(f"Route:   {result.route}")


if __name__ == "__main__":
    main()
