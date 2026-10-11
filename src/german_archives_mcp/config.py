"""Configuration from environment variables.

====================================  ==========================================
``GERMAN_ARCHIVES_CACHE_DIR``         Directory for the on-disk response cache.
``GERMAN_ARCHIVES_TIMEOUT``           HTTP timeout in seconds for one request.
``GERMAN_ARCHIVES_MIN_INTERVAL``      Least seconds between two requests to one
                                      host. Never below 2; the Archive in NRW
                                      portal's searches wait 10 whatever this
                                      says.
``GERMAN_ARCHIVES_CONTACT``           An email address or URL appended to the
                                      User-Agent, so an archive can reach
                                      whoever runs this server.
``GERMAN_ARCHIVES_DOWNLOAD_DIR``      When set, the folder every image
                                      tool's destination must lie inside.
``GERMAN_ARCHIVES_PDF_CACHE_DAYS``    Days a downloaded APERTUS volume PDF is
                                      kept for reading further pages. Default
                                      3.
``GERMAN_ARCHIVES_PDF_CACHE_MB``      Most megabytes of volume PDFs kept; the
                                      least recently read go first. Default
                                      1000.
====================================  ==========================================

None is required: the DDB's version 2 API, the Landesarchiv
Baden-Württemberg's online finding aids, the Archive in NRW portal, APERTUS,
LAGIS and Arcinsys Hessen need no key and no account. A ``.env`` file in the working
directory supplies any of these that the environment does not. The download
folder is the operator's to set, never a model's: it narrows where a tool
writes.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

#: Least seconds between requests to one host, unless configured otherwise.
DEFAULT_MIN_INTERVAL = 2.0

#: The floor on GERMAN_ARCHIVES_MIN_INTERVAL: no host is asked more often.
MIN_INTERVAL_FLOOR = 2.0

#: Days a volume PDF is kept, unless configured otherwise, and the longest allowed.
DEFAULT_PDF_CACHE_DAYS = 3.0
MAX_PDF_CACHE_DAYS = 30.0

#: Megabytes of volume PDFs kept, unless configured otherwise, and the least
#: allowed: a cap smaller than one volume would make every page a download.
DEFAULT_PDF_CACHE_MB = 1000.0
MIN_PDF_CACHE_MB = 100.0


class ConfigError(RuntimeError):
    """Raised when a setting is present but unusable."""


@dataclass
class Config:
    """Resolved server configuration.

    Attributes
    ----------
    cache_dir : Path
        Directory holding cached responses.
    timeout : float
        HTTP timeout in seconds for one request. Image downloads get longer.
    min_interval : float
        Least seconds between the start of one request to a host and the next.
    contact : str
        Appended to the User-Agent when set. Empty by default.
    download_dir : Path or None
        When set, the image tools write only inside this folder.
    pdf_cache_days : float
        Days a downloaded volume PDF is kept for further pages.
    pdf_cache_mb : float
        Most megabytes of volume PDFs kept on disk.
    """

    cache_dir: Path = field(default_factory=lambda: Path.home() / ".cache" / "german-archives-mcp")
    timeout: float = 30.0
    min_interval: float = DEFAULT_MIN_INTERVAL
    contact: str = ""
    download_dir: Path | None = None
    pdf_cache_days: float = DEFAULT_PDF_CACHE_DAYS
    pdf_cache_mb: float = DEFAULT_PDF_CACHE_MB


def load_config() -> Config:
    """Load configuration from the environment.

    A ``.env`` file in the working directory is read if present; real
    environment variables win. Only the working directory is consulted.
    ``load_dotenv()`` with no path searches upward from the *calling
    module's* location instead, which for an installed package is
    ``site-packages``.

    Raises
    ------
    ConfigError
        If a number is unusable or a contact string could break the header.
        The server loads its configuration on the first tool call, so this
        surfaces there as a ``not_configured`` result rather than as a crash.
    """
    load_dotenv(Path.cwd() / ".env")

    cfg = Config()
    if raw := os.environ.get("GERMAN_ARCHIVES_CACHE_DIR"):
        cfg.cache_dir = Path(raw).expanduser()
    if raw := os.environ.get("GERMAN_ARCHIVES_TIMEOUT"):
        cfg.timeout = _positive("GERMAN_ARCHIVES_TIMEOUT", raw)
    if raw := os.environ.get("GERMAN_ARCHIVES_MIN_INTERVAL"):
        value = _positive("GERMAN_ARCHIVES_MIN_INTERVAL", raw)
        if value < MIN_INTERVAL_FLOOR:
            raise ConfigError(
                f"GERMAN_ARCHIVES_MIN_INTERVAL must be at least {MIN_INTERVAL_FLOOR}; got {raw!r}."
            )
        cfg.min_interval = value
    if raw := os.environ.get("GERMAN_ARCHIVES_CONTACT"):
        cfg.contact = _contact(raw)
    if raw := os.environ.get("GERMAN_ARCHIVES_DOWNLOAD_DIR"):
        cfg.download_dir = _download_dir(raw)
    if raw := os.environ.get("GERMAN_ARCHIVES_PDF_CACHE_DAYS"):
        value = _positive("GERMAN_ARCHIVES_PDF_CACHE_DAYS", raw)
        if value > MAX_PDF_CACHE_DAYS:
            raise ConfigError(
                "GERMAN_ARCHIVES_PDF_CACHE_DAYS may be at most "
                f"{MAX_PDF_CACHE_DAYS:g}; got {raw!r}."
            )
        cfg.pdf_cache_days = value
    if raw := os.environ.get("GERMAN_ARCHIVES_PDF_CACHE_MB"):
        value = _positive("GERMAN_ARCHIVES_PDF_CACHE_MB", raw)
        if value < MIN_PDF_CACHE_MB:
            raise ConfigError(
                f"GERMAN_ARCHIVES_PDF_CACHE_MB must be at least {MIN_PDF_CACHE_MB:g}; got {raw!r}."
            )
        cfg.pdf_cache_mb = value
    return cfg


def _positive(name: str, raw: str) -> float:
    """Parse one numeric setting, naming the variable if it is unusable."""
    try:
        value = float(raw.strip())
    except ValueError:
        raise ConfigError(f"{name} must be a number; got {raw!r}.") from None
    if not math.isfinite(value) or value <= 0:
        raise ConfigError(f"{name} must be greater than zero; got {raw!r}.")
    return value


def _contact(raw: str) -> str:
    """Keep a contact string safe to place inside a User-Agent header.

    A newline would let the value inject a second header, and parentheses
    would close the comment it sits in.
    """
    text = raw.strip()
    if any(ch in text for ch in "\r\n()") or not text.isprintable():
        raise ConfigError(
            "GERMAN_ARCHIVES_CONTACT must be one line with no parentheses, such as an "
            f"email address or a URL; got {raw!r}."
        )
    return text


def _download_dir(raw: str) -> Path:
    """The folder the image tools are confined to: absolute, and already there.

    A folder that does not exist yet is refused rather than created, so a
    typing slip cannot confine downloads to somewhere unintended.
    """
    path = Path(raw.strip()).expanduser()
    if not path.is_absolute():
        raise ConfigError(f"GERMAN_ARCHIVES_DOWNLOAD_DIR must be an absolute path; got {raw!r}.")
    if not path.is_dir():
        raise ConfigError(
            f"GERMAN_ARCHIVES_DOWNLOAD_DIR must be a folder that exists; got {raw!r}."
        )
    return path
