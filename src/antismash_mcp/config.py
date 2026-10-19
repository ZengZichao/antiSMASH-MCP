"""Configuration module for the antiSMASH MCP server."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Strictness(str, Enum):
    """Detection strictness levels for antiSMASH analysis."""

    STRICT = "strict"
    """Detects well-defined clusters containing all required parts."""

    RELAXED = "relaxed"
    """Detects partial clusters missing one or more functional parts."""

    LOOSE = "loose"
    """Detects clusters with looser criteria, may include more false positives."""

    @classmethod
    def from_string(cls, value: str) -> Strictness:
        """Create a Strictness from a string value (case-insensitive)."""
        try:
            return cls(value.lower())
        except ValueError:
            valid = ", ".join(s.value for s in cls)
            raise ValueError(
                f"Invalid strictness '{value}'. Valid options: {valid}"
            ) from None


class ServerType(str, Enum):
    """Type of antiSMASH server (bacteria / fungi / plant)."""

    BACTERIA = "bacteria"
    """antiSMASH bacterial version (https://antismash.secondarymetabolites.org/)."""

    FUNGI = "fungi"
    """antiSMASH fungal version (https://fungismash.secondarymetabolites.org/)."""

    PLANT = "plant"
    """antiSMASH plant version (http://plantismash.secondarymetabolites.org/)."""

    @classmethod
    def from_string(cls, value: str) -> ServerType:
        """Create a ServerType from a string value (case-insensitive)."""
        try:
            return cls(value.lower())
        except ValueError:
            valid = ", ".join(s.value for s in cls)
            raise ValueError(
                f"Invalid server type '{value}'. Valid options: {valid}"
            ) from None


# Base URLs for each antiSMASH instance
SERVER_URLS: dict[ServerType, str] = {
    ServerType.BACTERIA: "https://antismash.secondarymetabolites.org",
    ServerType.FUNGI: "https://fungismash.secondarymetabolites.org",
    ServerType.PLANT: "http://plantismash.secondarymetabolites.org",
}


@dataclass
class AntiSmashConfig:
    """Configuration for the antiSMASH MCP server.

    Attributes:
        server_type: The type of antiSMASH server to use.
        base_url: Base URL for the antiSMASH server (automatically set from server_type).
        timeout: Request timeout in seconds.
        poll_interval: Job status polling interval in seconds.
        max_poll_time: Maximum time to poll job status before giving up (seconds).
        max_concurrent_jobs: Maximum concurrent jobs the user should run (antiSMASH recommends 5).
        user_agent: User-Agent header for HTTP requests.
    """

    server_type: ServerType = ServerType.BACTERIA
    base_url: str = field(init=False)
    timeout: int = 30
    poll_interval: int = 30
    max_poll_time: int = 3600
    max_concurrent_jobs: int = 5
    user_agent: str = "antiSMASH-MCP/0.1.0"

    def __post_init__(self) -> None:
        self.base_url = SERVER_URLS[self.server_type].rstrip("/")

    @classmethod
    def for_server(cls, server_type: str | ServerType, **kwargs: Any) -> AntiSmashConfig:
        """Create a config for a specific server type."""
        if isinstance(server_type, str):
            server_type = ServerType.from_string(server_type)
        return cls(server_type=server_type, **kwargs)

    @property
    def submit_url(self) -> str:
        """URL for submitting new jobs."""
        return f"{self.base_url}/upload/"

    @property
    def job_url(self) -> str:
        """Base URL for job-related requests."""
        return f"{self.base_url}/upload/"

    def get_job_url(self, job_id: str) -> str:
        """Get the URL for a specific job's results page."""
        return f"{self.base_url}/{job_id}"

    def get_job_status_url(self, job_id: str) -> str:
        """Get the URL for checking job status."""
        return f"{self.base_url}/{job_id}/status"

    def get_job_download_url(self, job_id: str, filename: str = "") -> str:
        """Get the URL for downloading job result files."""
        base = f"{self.base_url}/{job_id}"
        if filename:
            return f"{base}/{filename}"
        return f"{base}.zip"


# Default global config instance
_default_config: AntiSmashConfig | None = None


def get_default_config() -> AntiSmashConfig:
    """Get the default global configuration instance."""
    global _default_config
    if _default_config is None:
        _default_config = AntiSmashConfig()
    return _default_config


def set_default_config(config: AntiSmashConfig) -> None:
    """Set the default global configuration instance."""
    global _default_config
    _default_config = config


# Available extra features for antiSMASH analysis
EXTRA_FEATURES: list[str] = [
    "knownclusterblast",
    "clusterblast",
    "subclusterblast",
    "mibig",
    "active_site_finder",
    "rrefinder",
    "pfam2go",
    "tigrfam",
    "tfbs",
    "ncbi_context",
]

ALL_EXTRA_FEATURES: dict[str, str] = {
    "knownclusterblast": "KnownClusterBlast - Compare against known clusters from MIBiG",
    "clusterblast": "ClusterBlast - Compare gene clusters against a database",
    "subclusterblast": "SubClusterBlast - Compare against known subclusters",
    "mibig": "MIBiG cluster comparison",
    "active_site_finder": "ActiveSiteFinder - Analyze active sites",
    "rrefinder": "RREFinder - Detect RRE (RiPP Recognition Element) domains",
    "pfam2go": "Pfam-based GO term annotation",
    "tigrfam": "TIGRFam analysis",
    "tfbs": "TFBS analysis - Transcription Factor Binding Site analysis",
    "ncbi_context": "NCBI genomic context links",
}
