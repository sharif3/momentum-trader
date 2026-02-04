import argparse


def load_tickers(path: str) -> list[str]:
    tickers: list[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            sym = line.strip()
            if not sym or sym.startswith("#"):
                continue
            tickers.append(sym)
    return tickers


def to_eodhd_symbol(raw: str) -> str:
    sym = raw.strip().upper()
    if "." in sym:
        sym = sym.replace(".", "-")
    if not sym.endswith(".US"):
        sym = f"{sym}.US"
    return sym


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--symbols-file",
        default="data/halal_universe_2022_2023.txt",
        help="Path to ticker list (one per line)",
    )
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--end", default="2023-12-31")
    parser.add_argument("--max-symbols", type=int, default=0, help="Limit tickers for testing")
    args = parser.parse_args()

    tickers = load_tickers(args.symbols_file)
    if args.max_symbols > 0:
        tickers = tickers[: args.max_symbols]

    mapped = [to_eodhd_symbol(t) for t in tickers]

    print(f"loaded tickers: {len(tickers)}")
    if tickers:
        print("sample mapping:")
        for raw, sym in list(zip(tickers, mapped))[:5]:
            print(f"  {raw} -> {sym}")
    print(f"date range: {args.start} to {args.end}")


if __name__ == "__main__":
    main()
