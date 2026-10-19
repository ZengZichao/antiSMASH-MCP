"""antiSMASH API client for interacting with antiSMASH web servers.

This module provides a Python client that wraps the antiSMASH web interface,
supporting job submission, status polling, and results retrieval.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx

from .config import (
    EXTRA_FEATURES,
    AntiSmashConfig,
    Strictness,
    get_default_config,
)

logger = logging.getLogger(__name__)


class AntiSmashError(Exception):
    """Base exception for antiSMASH API errors."""


class AntiSmashSubmissionError(AntiSmashError):
    """Error when submitting a job to antiSMASH."""


class AntiSmashJobNotFoundError(AntiSmashError):
    """Error when a job is not found."""


class AntiSmashTimeoutError(AntiSmashError):
    """Error when job polling times out."""


class AntiSmashConnectionError(AntiSmashError):
    """Error when connecting to antiSMASH server."""


class JobStatus:
    """Constants for job status values."""

    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    PENDING = "pending"


class AntiSmashClient:
    """Async client for the antiSMASH web API.

    This client wraps the antiSMASH web interface, which is a single-page
    application (SPA) that communicates with the backend via HTTP.

    The main operations are:
    - Submitting jobs (file upload or NCBI accession)
    - Checking job status
    - Retrieving and parsing results

    Args:
        config: Configuration for the antiSMASH client. Uses default config if not provided.
    """

    def __init__(self, config: AntiSmashConfig | None = None) -> None:
        self.config = config or get_default_config()
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> AntiSmashClient:
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure the HTTP client is created."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.timeout),
                headers={
                    "User-Agent": self.config.user_agent,
                    "Accept": "text/html,application/json,*/*",
                },
                follow_redirects=True,
            )
        return self._client

    async def _make_request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make an HTTP request and handle errors.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: URL to request.
            **kwargs: Additional arguments passed to httpx.

        Returns:
            httpx.Response: The response object.

        Raises:
            AntiSmashConnectionError: If the request fails.
        """
        client = await self._ensure_client()
        try:
            response = await client.request(method, url, **kwargs)
            return response
        except httpx.ConnectError as e:
            raise AntiSmashConnectionError(
                f"Failed to connect to antiSMASH server: {e}"
            ) from e
        except httpx.TimeoutException as e:
            raise AntiSmashConnectionError(
                f"Request timed out connecting to antiSMASH server: {e}"
            ) from e
        except httpx.RequestError as e:
            raise AntiSmashConnectionError(
                f"Request error connecting to antiSMASH server: {e}"
            ) from e

    async def submit_job(
        self,
        sequence_file: str | Path | None = None,
        ncbi_accession: str | None = None,
        email: str = "",
        strictness: Strictness | str = Strictness.RELAXED,
        extra_features: list[str] | None = None,
        gff3_file: str | Path | None = None,
        sideload_file: str | Path | None = None,
    ) -> str:
        """Submit a new job to antiSMASH.

        Args:
            sequence_file: Path to a sequence file (GenBank/EMBL/FASTA format).
            ncbi_accession: NCBI accession number for the desired sequence.
            email: Optional email address for notifications.
            strictness: Detection strictness level (strict/relaxed/loose).
            extra_features: List of extra features to enable. Valid options:
                knownclusterblast, clusterblast, subclusterblast, mibig,
                active_site_finder, rrefinder, pfam2go, tigrfam, tfbs, ncbi_context.
            gff3_file: Optional path to a GFF3 feature annotation file.
            sideload_file: Optional path to an antiSMASH annotations sideload JSON file.

        Returns:
            str: The job ID of the submitted job.

        Raises:
            AntiSmashSubmissionError: If submission fails or neither
                sequence_file nor ncbi_accession is provided.
        """
        if isinstance(strictness, str):
            strictness = Strictness.from_string(strictness)

        if sequence_file is None and ncbi_accession is None:
            raise AntiSmashSubmissionError(
                "Either sequence_file or ncbi_accession must be provided"
            )

        # Build multipart form data
        data: dict[str, Any] = {
            "strictness": strictness.value,
        }

        if email:
            data["email"] = email

        # Add extra features as individual form fields
        if extra_features:
            # Validate that all requested features are known
            invalid = [f for f in extra_features if f not in EXTRA_FEATURES]
            if invalid:
                valid = ", ".join(EXTRA_FEATURES)
                raise AntiSmashSubmissionError(
                    f"Invalid extra feature(s): {', '.join(invalid)}. "
                    f"Valid options: {valid}"
                )
            for feature in extra_features:
                data[f"extra_features:{feature}"] = "on"
        else:
            # Default: enable common features
            data["extra_features:knownclusterblast"] = "on"
            data["extra_features:clusterblast"] = "on"
            data["extra_features:subclusterblast"] = "on"
            data["extra_features:mibig"] = "on"

        files: dict[str, Any] = {}

        if sequence_file is not None:
            seq_path = Path(sequence_file)
            if not seq_path.exists():
                raise AntiSmashSubmissionError(
                    f"Sequence file not found: {seq_path}"
                )
            files["seqfile"] = (seq_path.name, seq_path.read_bytes(),
                                "application/octet-stream")

        if gff3_file is not None:
            gff_path = Path(gff3_file)
            if not gff_path.exists():
                raise AntiSmashSubmissionError(
                    f"GFF3 file not found: {gff_path}"
                )
            files["gff3file"] = (gff_path.name, gff_path.read_bytes(),
                                 "application/octet-stream")

        if sideload_file is not None:
            sideload_path = Path(sideload_file)
            if not sideload_path.exists():
                raise AntiSmashSubmissionError(
                    f"Sideload file not found: {sideload_path}"
                )
            files["asjsonfile"] = (sideload_path.name,
                                   sideload_path.read_bytes(),
                                   "application/json")

        if ncbi_accession is not None:
            data["ncbi"] = ncbi_accession

        logger.info("Submitting job to antiSMASH (server: %s)",
                     self.config.server_type.value)

        response = await self._make_request(
            "POST",
            self.config.submit_url,
            data=data,
            files=files,
        )

        # antiSMASH returns 403 for the upload endpoint, but the job ID
        # is in the response. Let's try to extract it.
        # The actual antiSMASH web API uses a POST to /upload/ and returns
        # a redirect to the job page.
        if response.status_code == 403:
            # This is expected behavior for the web form - try to extract job ID
            # from the response or follow redirects
            logger.warning(
                "Got 403 from upload endpoint. Trying alternative submission method."
            )
            job_id = self._extract_job_id_from_response(response)
            if job_id:
                return job_id
            raise AntiSmashSubmissionError(
                "Server returned 403 Forbidden. The antiSMASH web server "
                "may have rate limiting or require a different submission method. "
                "Please try again later or use the NCBI accession method."
            )

        if response.status_code not in (200, 201, 302):
            raise AntiSmashSubmissionError(
                f"Job submission failed with status {response.status_code}: "
                f"{response.text[:500]}"
            )

        # Try to extract job ID from response
        job_id = self._extract_job_id_from_response(response)
        if not job_id:
            raise AntiSmashSubmissionError(
                "Could not extract job ID from server response"
            )

        logger.info("Job submitted successfully: %s", job_id)
        return job_id

    def _extract_job_id_from_response(self, response: httpx.Response) -> str | None:
        """Extract the job ID from a server response.

        antiSMASH typically returns a redirect URL like:
        https://antismash.secondarymetabolites.org/{job_id}
        or the job ID in the response body.

        Args:
            response: HTTP response from antiSMASH.

        Returns:
            str | None: The extracted job ID, or None if not found.
        """
        # Check for Location header (redirect)
        location = response.headers.get("location", "")
        if location:
            # Extract job ID from URL
            # Format: https://antismash.secondarymetabolites.org/{job_id}
            match = re.search(r"/([A-Za-z0-9_-]{6,})/?$", location)
            if match:
                return match.group(1)

        # Check response text for job ID
        text = response.text
        # Look for job ID patterns in the response
        # Job IDs are typically like "BGC0001234" or alphanumeric strings
        patterns = [
            r'(?:job[_-]?id|task[_-]?id)["\s:=]+([A-Za-z0-9_-]{6,})',
            r'/([A-Za-z0-9_-]{8,})/?["\s]',
            r'data-job-id="([A-Za-z0-9_-]+)"',
            r'id="job-id"[^>]*>([A-Za-z0-9_-]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)

        return None

    async def get_job_status(self, job_id: str) -> dict[str, Any]:
        """Get the status of a submitted job.

        Args:
            job_id: The job ID to check.

        Returns:
            dict: Job status information including:
                - status: Job status (queued/running/done/error/pending)
                - url: URL to results page
                - details: Additional status details

        Raises:
            AntiSmashJobNotFoundError: If the job is not found.
            AntiSmashConnectionError: If the request fails.
        """
        # Try the status endpoint first
        try:
            status_url = self.config.get_job_status_url(job_id)
            response = await self._make_request("GET", status_url)

            if response.status_code == 200:
                try:
                    json_data = response.json()
                    if isinstance(json_data, dict):
                        return json_data
                except json.JSONDecodeError:
                    pass
        except AntiSmashConnectionError:
            pass

        # Fall back to checking the job page directly
        job_url = self.config.get_job_url(job_id)
        response = await self._make_request("GET", job_url)

        if response.status_code == 404:
            raise AntiSmashJobNotFoundError(
                f"Job not found: {job_id}"
            )

        if response.status_code != 200:
            raise AntiSmashConnectionError(
                f"Failed to check job status: HTTP {response.status_code}"
            )

        # Parse the HTML to determine status
        status = self._parse_status_from_html(response.text, job_id)

        return {
            "job_id": job_id,
            "status": status,
            "url": job_url,
        }

    def _parse_status_from_html(self, html: str, job_id: str) -> str:
        """Parse the job status from the HTML response.

        Args:
            html: HTML response from the job page.
            job_id: The job ID being checked.

        Returns:
            str: Job status (queued/running/done/error).
        """
        html_lower = html.lower()

        # Check for status indicators in the HTML
        if "still being processed" in html_lower or "running" in html_lower:
            if "queued" in html_lower:
                return JobStatus.QUEUED
            return JobStatus.RUNNING

        if "error" in html_lower and "cluster" not in html_lower:
            return JobStatus.ERROR

        if "region" in html_lower and "download" in html_lower:
            return JobStatus.DONE

        # Check for job-specific status text
        status_patterns = [
            (r"job\s+(?:status|state)[^a-z]*([a-z]+)", "status"),
            (r'class="[^"]*status[^"]*"[^>]*>([a-z]+)', "status"),
        ]

        for pattern, _ in status_patterns:
            match = re.search(pattern, html_lower)
            if match:
                status_text = match.group(1)
                if status_text in (JobStatus.QUEUED, JobStatus.RUNNING,
                                   JobStatus.DONE, JobStatus.ERROR,
                                   JobStatus.PENDING):
                    return status_text

        # Default to pending if we can't determine
        return JobStatus.PENDING

    async def wait_for_job(
        self,
        job_id: str,
        poll_interval: int | None = None,
        max_wait: int | None = None,
    ) -> dict[str, Any]:
        """Wait for a job to complete by polling its status.

        Args:
            job_id: The job ID to wait for.
            poll_interval: Seconds between status checks. Defaults to config value.
            max_wait: Maximum seconds to wait. Defaults to config value.

        Returns:
            dict: Final job status information.

        Raises:
            AntiSmashTimeoutError: If the job doesn't complete within max_wait.
            AntiSmashJobNotFoundError: If the job is not found.
        """
        interval = poll_interval or self.config.poll_interval
        max_time = max_wait or self.config.max_poll_time

        elapsed = 0
        while elapsed < max_time:
            status_info = await self.get_job_status(job_id)
            status = status_info.get("status", JobStatus.PENDING)

            logger.debug(
                "Job %s status: %s (elapsed: %ds)",
                job_id, status, elapsed,
            )

            if status == JobStatus.DONE:
                return status_info

            if status == JobStatus.ERROR:
                raise AntiSmashError(
                    f"Job {job_id} failed with error: "
                    f"{status_info.get('details', 'Unknown error')}"
                )

            await asyncio.sleep(interval)
            elapsed += interval

        raise AntiSmashTimeoutError(
            f"Job {job_id} did not complete within {max_time} seconds"
        )

    async def get_job_results(self, job_id: str) -> dict[str, Any]:
        """Get the results of a completed job.

        Args:
            job_id: The job ID.

        Returns:
            dict: Results summary including:
                - job_id: The job ID
                - url: URL to the results page
                - status: Job status
                - regions: List of detected regions/clusters
                - summary: Summary of results

        Raises:
            AntiSmashJobNotFoundError: If the job is not found.
            AntiSmashError: If the job hasn't completed or results can't be retrieved.
        """
        # First check if the job is done
        status_info = await self.get_job_status(job_id)
        status = status_info.get("status", "")

        if status != JobStatus.DONE:
            # Try to get results anyway - the status check might not be accurate
            logger.warning(
                "Job %s status is '%s', attempting to retrieve results anyway",
                job_id, status,
            )

        # Get the results page
        job_url = self.config.get_job_url(job_id)
        response = await self._make_request("GET", job_url)

        if response.status_code == 404:
            raise AntiSmashJobNotFoundError(f"Job not found: {job_id}")

        if response.status_code != 200:
            raise AntiSmashError(
                f"Failed to retrieve results: HTTP {response.status_code}"
            )

        # Parse results from the HTML
        results = self._parse_results_from_html(response.text, job_id)
        results["url"] = job_url

        return results

    def _parse_results_from_html(self, html: str, job_id: str) -> dict[str, Any]:
        """Parse results summary from the antiSMASH results HTML page.

        Args:
            html: HTML content of the results page.
            job_id: The job ID.

        Returns:
            dict: Parsed results summary.
        """
        results: dict[str, Any] = {
            "job_id": job_id,
            "status": JobStatus.DONE,
            "regions": [],
            "summary": {},
        }

        # Extract region information
        # antiSMASH results pages contain region entries with cluster information
        region_pattern = re.compile(
            r'region\s*[\d.]+|Cluster\s*[-]?\d+|BGC\d+',
            re.IGNORECASE,
        )
        regions = region_pattern.findall(html)

        # Extract region details
        region_details_pattern = re.compile(
            r'<div[^>]*class="[^"]*region[^"]*"[^>]*>'
            r'.*?(?:cluster|region)\s*(\d+)'
            r'.*?type["\s:]+([A-Za-z_]+)'
            r'.*?(?:from|start)["\s:]+(\d+)'
            r'.*?(?:to|end)["\s:]+(\d+)',
            re.IGNORECASE | re.DOTALL,
        )

        for match in region_details_pattern.finditer(html):
            results["regions"].append({
                "region_number": int(match.group(1)),
                "cluster_type": match.group(2),
                "start": int(match.group(3)),
                "end": int(match.group(4)),
            })

        # If we couldn't parse detailed regions, at least count them
        if not results["regions"] and regions:
            results["summary"]["total_regions_detected"] = len(set(regions))
        elif results["regions"]:
            results["summary"]["total_regions_detected"] = len(results["regions"])

        # Extract summary statistics
        stats_patterns = {
            "total_genes": r'(?:total\s+)?genes["\s:]*(\d+)',
            "total_regions": r'regions?["\s:]*(\d+)',
            "total_clusters": r'clusters?["\s:]*(\d+)',
        }

        for key, pattern in stats_patterns.items():
            stats_match = re.search(pattern, html, re.IGNORECASE)
            if stats_match:
                results["summary"][key] = int(stats_match.group(1))

        # Extract cluster types found
        cluster_types = set()
        type_pattern = re.compile(
            r'(?:cluster[_-]?type|bgc[_-]?type|product)["\s:]+([A-Za-z_,\s]+)',
            re.IGNORECASE,
        )
        for type_match in type_pattern.finditer(html):
            types = type_match.group(1).strip().split(",")
            for t in types:
                t = t.strip()
                if t and len(t) > 2:
                    cluster_types.add(t)

        if cluster_types:
            results["summary"]["cluster_types"] = sorted(cluster_types)

        return results

    async def download_results(
        self,
        job_id: str,
        output_path: str | Path,
    ) -> Path:
        """Download the results archive (ZIP file) for a completed job.

        Args:
            job_id: The job ID.
            output_path: Path to save the ZIP file (or directory to save in).

        Returns:
            Path: The path to the downloaded ZIP file.

        Raises:
            AntiSmashError: If download fails.
        """
        download_url = self.config.get_job_download_url(job_id)
        response = await self._make_request("GET", download_url)

        if response.status_code != 200:
            raise AntiSmashError(
                f"Failed to download results: HTTP {response.status_code}"
            )

        output = Path(output_path)
        if output.is_dir():
            output = output / f"{job_id}.zip"

        output.write_bytes(response.content)
        logger.info("Downloaded results to %s", output)
        return output

    async def download_and_extract_results(
        self,
        job_id: str,
        output_dir: str | Path,
    ) -> Path:
        """Download and extract the results archive for a completed job.

        Args:
            job_id: The job ID.
            output_dir: Directory to extract the results to.

        Returns:
            Path: The path to the extracted results directory.

        Raises:
            AntiSmashError: If download or extraction fails.
        """
        # Download the ZIP
        download_url = self.config.get_job_download_url(job_id)
        response = await self._make_request("GET", download_url)

        if response.status_code != 200:
            raise AntiSmashError(
                f"Failed to download results: HTTP {response.status_code}"
            )

        out_dir = Path(output_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        # Extract the ZIP with path traversal protection
        try:
            with zipfile.ZipFile(BytesIO(response.content)) as zf:
                for member in zf.infolist():
                    member_path = (out_dir / member.filename).resolve()
                    # Security: prevent path traversal (Zip Slip vulnerability)
                    if not str(member_path).startswith(str(out_dir)):
                        raise AntiSmashError(
                            f"Unsafe file path in archive: {member.filename}"
                        )
                zf.extractall(out_dir)
        except zipfile.BadZipFile as e:
            raise AntiSmashError(
                f"Failed to extract results archive: {e}"
            ) from e

        logger.info("Extracted results to %s", out_dir)
        return out_dir

    async def get_job_details(self, job_id: str) -> dict[str, Any]:
        """Get detailed information about a job.

        This retrieves the full job page HTML and extracts structured
        information including detected regions, gene clusters, and links.

        Args:
            job_id: The job ID.

        Returns:
            dict: Detailed job information including:
                - job_id: The job ID
                - url: URL to the job page
                - status: Job status
                - regions: List of detected regions with details
                - links: Relevant links (download, etc.)

        Raises:
            AntiSmashJobNotFoundError: If the job is not found.
        """
        job_url = self.config.get_job_url(job_id)
        response = await self._make_request("GET", job_url)

        if response.status_code == 404:
            raise AntiSmashJobNotFoundError(f"Job not found: {job_id}")

        if response.status_code != 200:
            raise AntiSmashError(
                f"Failed to get job details: HTTP {response.status_code}"
            )

        html = response.text
        status = self._parse_status_from_html(html, job_id)
        results = self._parse_results_from_html(html, job_id)

        details: dict[str, Any] = {
            "job_id": job_id,
            "url": job_url,
            "status": status,
            "regions": results.get("regions", []),
            "summary": results.get("summary", {}),
            "download_url": self.config.get_job_download_url(job_id),
        }

        # Extract links from HTML
        link_pattern = re.compile(
            r'<a[^>]+href="([^"]*)"[^>]*>([^<]*)</a>',
            re.IGNORECASE,
        )
        links: dict[str, str] = {}
        for match in link_pattern.finditer(html):
            href = match.group(1)
            text = match.group(2).strip()
            if href and text and any(
                kw in text.lower()
                for kw in ["download", "genbank", "gbk", "fasta", "zip", "json"]
            ):
                if href.startswith("/"):
                    href = f"{self.config.base_url}{href}"
                links[text] = href

        if links:
            details["links"] = links

        return details

    async def get_server_status(self) -> dict[str, Any]:
        """Get the status of the antiSMASH server.

        Returns:
            dict: Server status information including:
                - status: Server status (working/maintenance)
                - running_jobs: Number of currently running jobs
                - queued_jobs: Number of queued jobs
                - jobs_processed: Total number of jobs processed

        Raises:
            AntiSmashConnectionError: If the request fails.
        """
        response = await self._make_request("GET", self.config.base_url)

        if response.status_code != 200:
            raise AntiSmashConnectionError(
                f"Failed to get server status: HTTP {response.status_code}"
            )

        html = response.text
        status_info: dict[str, Any] = {}

        # Parse server status from HTML
        status_patterns = {
            "status": r"Server status:\s*(\w+)",
            "running_jobs": r"Running jobs:\s*(\d+)",
            "queued_jobs": r"Queued jobs:\s*(\d+)",
            "jobs_processed": r"Jobs processed:\s*([\d,]+)",
        }

        for key, pattern in status_patterns.items():
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                value = match.group(1).replace(",", "")
                if key == "jobs_processed":
                    status_info[key] = int(value)
                elif key == "status":
                    status_info[key] = value.lower()
                else:
                    status_info[key] = int(value)

        return status_info

    async def get_example_output_url(self) -> str:
        """Get the URL for the example antiSMASH output.

        Returns:
            str: URL to the example output page.
        """
        return f"{self.config.base_url}/example"
