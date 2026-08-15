"""Copy the committed sample restaurants into the live data directory.

`sample_data/` is committed so a clean clone has something to serve; `data/` is
gitignored because it holds real menus and pricing. This script bridges the two.

Usage:
    python -m scripts.seed_data                 # seed restaurants that are missing
    python -m scripts.seed_data --force         # overwrite existing folders
    python -m scripts.seed_data restaurant_1    # seed only the named restaurants
"""

import argparse
import logging
import shutil
import sys
from pathlib import Path
from typing import List, Optional

# Allow `python scripts/seed_data.py` as well as `python -m scripts.seed_data`.
_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from config import DATA_DIR, PROJECT_ROOT  # noqa: E402

logger = logging.getLogger(__name__)

SAMPLE_DATA_DIR = PROJECT_ROOT / "sample_data"
REQUIRED_FILES = ("menu.json", "hours.json", "info.json", "specials.json")


def available_samples() -> List[str]:
    """Restaurant ids that have a complete set of files under sample_data/."""
    if not SAMPLE_DATA_DIR.is_dir():
        return []
    ids = []
    for path in sorted(SAMPLE_DATA_DIR.iterdir()):
        if path.is_dir() and all((path / f).is_file() for f in REQUIRED_FILES):
            ids.append(path.name)
    return ids


def seed_sample_data(
    restaurant_ids: Optional[List[str]] = None, force: bool = False
) -> List[str]:
    """Copy sample restaurants into DATA_DIR. Returns the ids actually written."""
    wanted = restaurant_ids or available_samples()
    if not wanted:
        logger.warning("No complete restaurants under %s; nothing to seed", SAMPLE_DATA_DIR)
        return []

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for rid in wanted:
        src = SAMPLE_DATA_DIR / rid
        if not src.is_dir():
            logger.warning("No sample data for %r at %s", rid, src)
            continue
        dest = DATA_DIR / rid
        if dest.exists():
            if not force:
                logger.info("Skipping %r: %s already exists", rid, dest)
                continue
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        written.append(rid)
        logger.info("Seeded %r into %s", rid, dest)
    return written


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("restaurant_ids", nargs="*", help="Defaults to every sample restaurant")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace a restaurant folder that already exists in the data directory",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    written = seed_sample_data(args.restaurant_ids or None, force=args.force)
    if written:
        print(f"Seeded {len(written)} restaurant(s) into {DATA_DIR}: {', '.join(written)}")
    else:
        print(
            f"Nothing seeded. Existing folders are left alone; re-run with --force "
            f"to overwrite. Data directory: {DATA_DIR}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
