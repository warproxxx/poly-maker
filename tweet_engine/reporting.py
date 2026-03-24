def build_leaderboard(results):
    return sorted(
        results,
        key=lambda entry: (
            entry.get("realized_pnl", 0),
            entry.get("fill_rate", 0),
        ),
        reverse=True,
    )

