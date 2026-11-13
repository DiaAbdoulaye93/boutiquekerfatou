"""(Re)create the fictional shop in the database of backend/.env.

uv run python scripts/seed.py            # only if the database is empty
uv run python scripts/seed.py --reset    # wipe and regenerate
"""

import argparse
import logging

from app.db import get_engine, init_db
from app.seed.generate import DEFAULT_DAYS, DEFAULT_SEED, clear_database, is_empty, seed_database


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="delete the current data first")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()
    logging.basicConfig(level="INFO", format="%(levelname)s %(name)s: %(message)s")

    engine = get_engine()
    init_db(engine)
    if args.reset:
        clear_database(engine)
    elif not is_empty(engine):
        print("La base contient déjà des données : relancez avec --reset pour les remplacer.")
        return
    shop = seed_database(engine, days=args.days, seed=args.seed)
    print(
        f"Boutique fictive créée : {len(shop.products)} produits, {len(shop.customers)} clients, "
        f"{len(shop.sales)} factures, {len(shop.payments)} remboursements."
    )


if __name__ == "__main__":
    main()
