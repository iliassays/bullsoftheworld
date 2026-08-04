"""Research-only statistical models.

Nothing in this package is imported by Atlas execution or serving code.  A model remains an
offline diagnostic until its data lineage, temporal holdout and forward shadow book pass the
separate promotion process.
"""

from research.modeling.cross_sectional_rank import (
    FEATURE_COLUMNS,
    CrossSectionalSpec,
    RidgeModel,
)

__all__ = ["FEATURE_COLUMNS", "CrossSectionalSpec", "RidgeModel"]
