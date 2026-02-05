from __future__ import annotations

import warnings

warnings.filterwarnings(
    "ignore",
    message=r"pkg_resources is deprecated as an API\\..*",
    category=UserWarning,
)
warnings.filterwarnings(
    "ignore",
    message=r'Field name "schema" in "TableMetadataBody" shadows an attribute in parent "DataSourceAuthBody".*',
    category=UserWarning,
)

from datam8.app import app


def main() -> None:
    app()


if __name__ == "__main__":
    main()
