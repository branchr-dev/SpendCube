from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

_DEFAULT_YAML_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "reference" / "savings_rates.yaml"

_FALLBACK = {"saving_pct": None, "addressability_pct": 0.70}


class SavingsRates:
    """Lookup savings rates and addressability percentages from savings_rates.yaml."""

    def __init__(self, yaml_path: Optional[Path] = None) -> None:
        path = yaml_path or _DEFAULT_YAML_PATH
        with open(path, "r") as f:
            self._data: dict = yaml.safe_load(f)

    def get(self, lever_type: str, category_l1: Optional[str] = None) -> dict:
        """Return {'saving_pct': float | None, 'addressability_pct': float}.

        Lookup order:
        1. data['categories'][category_l1][lever_type] if both keys exist
        2. data['defaults'][lever_type]
        3. hardcoded fallback {'saving_pct': None, 'addressability_pct': 0.70}
        """
        categories = self._data.get("categories", {})
        if category_l1 is not None and category_l1 in categories:
            cat_entry = categories[category_l1].get(lever_type)
            if cat_entry is not None:
                return self._normalise(cat_entry)

        defaults = self._data.get("defaults", {})
        default_entry = defaults.get(lever_type)
        if default_entry is not None:
            return self._normalise(default_entry)

        return dict(_FALLBACK)

    @staticmethod
    def _normalise(entry: dict) -> dict:
        """Ensure both keys are always present; saving_pct defaults to None."""
        return {
            "saving_pct": entry.get("saving_pct", None),
            "addressability_pct": entry["addressability_pct"],
        }


_default_rates: Optional[SavingsRates] = None


def get_default_rates() -> SavingsRates:
    """Return the module-level singleton SavingsRates instance."""
    global _default_rates
    if _default_rates is None:
        _default_rates = SavingsRates()
    return _default_rates
