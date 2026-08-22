# Single source of truth for the application version.
#
# This value is bumped automatically by the release workflow
# (.github/workflows/docker-publish.yml) when a GitHub Release is published:
# the release tag (e.g. "v1.2.3") has its leading "v" stripped and is written
# here. The backend serves it at GET /api/version and the frontend footer
# shows it on every page.
__version__ = "0.3.2"
