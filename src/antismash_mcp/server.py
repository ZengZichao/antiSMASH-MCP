"""MCP server for the antiSMASH database.

This module implements a Model Context Protocol (MCP) server that provides
tools for interacting with the antiSMASH web service for secondary metabolite
biosynthetic gene cluster analysis.

The server exposes the following tools:
- submit_sequence: Submit a sequence file for analysis
- submit_ncbi: Submit an NCBI accession for analysis
- check_job_status: Check the status of a submitted job
- wait_for_job: Wait for a job to complete
- get_job_results: Get results of a completed job
- get_job_details: Get detailed information about a job
- download_results: Download results archive
- get_server_status: Check antiSMASH server status
- list_extra_features: List available extra features
- get_example_url: Get example output URL
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any

from mcp.server import Server
from mcp.server.context import ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ContentBlock,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)

from .antismash_client import (
    AntiSmashClient,
    AntiSmashConnectionError,
    AntiSmashError,
    AntiSmashJobNotFoundError,
    AntiSmashSubmissionError,
    AntiSmashTimeoutError,
    JobStatus,
)
from .config import (
    ALL_EXTRA_FEATURES,
    AntiSmashConfig,
    set_default_config,
)

__version__ = "0.1.0"

logger = logging.getLogger(__name__)


def _format_error(message: str) -> list[ContentBlock]:
    """Format an error message as tool result content."""
    return [TextContent(type="text", text=f"Error: {message}")]


def _format_success(data: Any) -> list[ContentBlock]:
    """Format a successful result as tool result content."""
    if isinstance(data, str):
        return [TextContent(type="text", text=data)]
    return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]


def _get_client(server_type: str = "bacteria") -> AntiSmashClient:
    """Get an antiSMASH client for the specified server type.

    Args:
        server_type: The type of antiSMASH server (bacteria/fungi/plant).

    Returns:
        AntiSmashClient: Configured client instance.
    """
    config = AntiSmashConfig.for_server(server_type)
    return AntiSmashClient(config)


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

async def handle_list_tools(
    ctx: ServerRequestContext[Any],
    params: PaginatedRequestParams | None = None,
) -> ListToolsResult:
    """List all available tools."""
    tools = [
        Tool(
            name="submit_sequence",
            description=(
                "Submit a nucleotide sequence file to antiSMASH for "
                "secondary metabolite biosynthetic gene cluster analysis. "
                "The sequence file should be in GenBank, EMBL, or FASTA format. "
                "Returns a job ID that can be used to check status and "
                "retrieve results."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "sequence_file": {
                        "type": "string",
                        "description": (
                            "Path to the sequence file (GenBank/EMBL/FASTA format). "
                            "Required if ncbi_accession is not provided."
                        ),
                    },
                    "email": {
                        "type": "string",
                        "description": "Optional email address for notifications.",
                        "default": "",
                    },
                    "strictness": {
                        "type": "string",
                        "enum": ["strict", "relaxed", "loose"],
                        "description": (
                            "Detection strictness level. "
                            "'strict': Detects well-defined clusters "
                            "containing all required parts. "
                            "'relaxed': Detects partial clusters missing "
                            "one or more functional parts. "
                            "'loose': Loose criteria, may include more "
                            "false positives."
                        ),
                        "default": "relaxed",
                    },
                    "extra_features": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Extra features to enable. Options: "
                            "knownclusterblast, clusterblast, subclusterblast, "
                            "mibig, active_site_finder, rrefinder, pfam2go, "
                            "tigrfam, tfbs, ncbi_context. "
                            "If not provided, defaults to knownclusterblast, "
                            "clusterblast, subclusterblast, mibig."
                        ),
                    },
                    "gff3_file": {
                        "type": "string",
                        "description": "Optional path to a GFF3 feature annotation file.",
                    },
                    "sideload_file": {
                        "type": "string",
                        "description": (
                            "Optional path to an antiSMASH annotations "
                            "sideload JSON file."
                        ),
                    },
                    "server_type": {
                        "type": "string",
                        "enum": ["bacteria", "fungi", "plant"],
                        "description": "Type of antiSMASH server to use.",
                        "default": "bacteria",
                    },
                },
            },
        ),
        Tool(
            name="submit_ncbi",
            description=(
                "Submit an NCBI accession number to antiSMASH for "
                "secondary metabolite biosynthetic gene cluster analysis. "
                "antiSMASH will retrieve the sequence from NCBI automatically. "
                "Returns a job ID that can be used to check status and "
                "retrieve results."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "ncbi_accession": {
                        "type": "string",
                        "description": (
                            "NCBI accession number of the desired sequence "
                            "(e.g., NC_003888.3, GCF_000005845.2)."
                        ),
                    },
                    "email": {
                        "type": "string",
                        "description": "Optional email address for notifications.",
                        "default": "",
                    },
                    "strictness": {
                        "type": "string",
                        "enum": ["strict", "relaxed", "loose"],
                        "description": "Detection strictness level.",
                        "default": "relaxed",
                    },
                    "extra_features": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Extra features to enable (see submit_sequence).",
                    },
                    "server_type": {
                        "type": "string",
                        "enum": ["bacteria", "fungi", "plant"],
                        "description": "Type of antiSMASH server to use.",
                        "default": "bacteria",
                    },
                },
                "required": ["ncbi_accession"],
            },
        ),
        Tool(
            name="check_job_status",
            description=(
                "Check the status of a submitted antiSMASH job. "
                "Returns the current status (queued/running/done/error/pending) "
                "and a URL to the results page."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "The antiSMASH job ID to check.",
                    },
                    "server_type": {
                        "type": "string",
                        "enum": ["bacteria", "fungi", "plant"],
                        "description": "Type of antiSMASH server the job was submitted to.",
                        "default": "bacteria",
                    },
                },
                "required": ["job_id"],
            },
        ),
        Tool(
            name="wait_for_job",
            description=(
                "Wait for an antiSMASH job to complete by polling its status. "
                "This is a blocking operation that checks the job status "
                "at regular intervals until the job is done or an error occurs. "
                "Use with caution as antiSMASH analysis can take 10+ minutes."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "The antiSMASH job ID to wait for.",
                    },
                    "poll_interval": {
                        "type": "integer",
                        "description": "Seconds between status checks.",
                        "default": 30,
                    },
                    "max_wait": {
                        "type": "integer",
                        "description": "Maximum seconds to wait before giving up.",
                        "default": 3600,
                    },
                    "server_type": {
                        "type": "string",
                        "enum": ["bacteria", "fungi", "plant"],
                        "description": "Type of antiSMASH server the job was submitted to.",
                        "default": "bacteria",
                    },
                },
                "required": ["job_id"],
            },
        ),
        Tool(
            name="get_job_results",
            description=(
                "Get the results of a completed antiSMASH job. "
                "Returns a summary of detected biosynthetic gene clusters, "
                "regions, and cluster types. The job should be completed "
                "before calling this tool."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "The antiSMASH job ID.",
                    },
                    "server_type": {
                        "type": "string",
                        "enum": ["bacteria", "fungi", "plant"],
                        "description": "Type of antiSMASH server the job was submitted to.",
                        "default": "bacteria",
                    },
                },
                "required": ["job_id"],
            },
        ),
        Tool(
            name="get_job_details",
            description=(
                "Get detailed information about an antiSMASH job, including "
                "detected regions, cluster types, download links, and summary "
                "statistics. Works for both running and completed jobs."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "The antiSMASH job ID.",
                    },
                    "server_type": {
                        "type": "string",
                        "enum": ["bacteria", "fungi", "plant"],
                        "description": "Type of antiSMASH server the job was submitted to.",
                        "default": "bacteria",
                    },
                },
                "required": ["job_id"],
            },
        ),
        Tool(
            name="download_results",
            description=(
                "Download the antiSMASH results archive (ZIP file) for a "
                "completed job and save it to a local path. "
                "The ZIP file contains all analysis results including "
                "GenBank files, HTML reports, and JSON data."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "The antiSMASH job ID.",
                    },
                    "output_path": {
                        "type": "string",
                        "description": (
                            "Path to save the ZIP file. If a directory is "
                            "provided, the file will be named {job_id}.zip."
                        ),
                    },
                    "server_type": {
                        "type": "string",
                        "enum": ["bacteria", "fungi", "plant"],
                        "description": "Type of antiSMASH server the job was submitted to.",
                        "default": "bacteria",
                    },
                },
                "required": ["job_id", "output_path"],
            },
        ),
        Tool(
            name="get_server_status",
            description=(
                "Get the current status of the antiSMASH server, including "
                "the number of running jobs, queued jobs, and total jobs "
                "processed. Useful to check if the server is available before "
                "submitting new jobs."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "server_type": {
                        "type": "string",
                        "enum": ["bacteria", "fungi", "plant"],
                        "description": "Type of antiSMASH server to check.",
                        "default": "bacteria",
                    },
                },
            },
        ),
        Tool(
            name="list_extra_features",
            description=(
                "List all available extra features for antiSMASH analysis "
                "with their descriptions. These features can be specified "
                "when submitting a job."
            ),
            input_schema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="get_example_url",
            description=(
                "Get the URL for the example antiSMASH output, which can be "
                "used to explore the format and content of antiSMASH results "
                "without submitting a job."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "server_type": {
                        "type": "string",
                        "enum": ["bacteria", "fungi", "plant"],
                        "description": "Type of antiSMASH server.",
                        "default": "bacteria",
                    },
                },
            },
        ),
    ]

    return ListToolsResult(tools=tools)


async def handle_call_tool(
    ctx: ServerRequestContext[Any],
    params: CallToolRequestParams,
) -> CallToolResult:
    """Handle a tool call.

    Args:
        ctx: The server request context.
        params: The tool call parameters (name and arguments).

    Returns:
        CallToolResult: The result of the tool call.
    """
    name = params.name
    arguments: dict[str, Any] = params.arguments or {}

    logger.info("Tool called: %s with args: %s", name, arguments)

    try:
        if name == "submit_sequence":
            content = await _handle_submit_sequence(arguments)
        elif name == "submit_ncbi":
            content = await _handle_submit_ncbi(arguments)
        elif name == "check_job_status":
            content = await _handle_check_job_status(arguments)
        elif name == "wait_for_job":
            content = await _handle_wait_for_job(arguments)
        elif name == "get_job_results":
            content = await _handle_get_job_results(arguments)
        elif name == "get_job_details":
            content = await _handle_get_job_details(arguments)
        elif name == "download_results":
            content = await _handle_download_results(arguments)
        elif name == "get_server_status":
            content = await _handle_get_server_status(arguments)
        elif name == "list_extra_features":
            content = await _handle_list_extra_features(arguments)
        elif name == "get_example_url":
            content = await _handle_get_example_url(arguments)
        else:
            return CallToolResult(
                content=_format_error(f"Unknown tool: {name}"),
                is_error=True,
            )

        return CallToolResult(content=content)

    except AntiSmashSubmissionError as e:
        return CallToolResult(content=_format_error(str(e)), is_error=True)
    except AntiSmashJobNotFoundError as e:
        return CallToolResult(content=_format_error(str(e)), is_error=True)
    except AntiSmashTimeoutError as e:
        return CallToolResult(content=_format_error(str(e)), is_error=True)
    except AntiSmashConnectionError as e:
        return CallToolResult(content=_format_error(str(e)), is_error=True)
    except AntiSmashError as e:
        return CallToolResult(content=_format_error(str(e)), is_error=True)
    except Exception as e:
        logger.exception("Unexpected error in tool %s", name)
        return CallToolResult(
            content=_format_error(f"Unexpected error: {e}"),
            is_error=True,
        )


# ---------------------------------------------------------------------------
# Individual tool handlers
# ---------------------------------------------------------------------------

async def _handle_submit_sequence(arguments: dict[str, Any]) -> list[ContentBlock]:
    """Handle the submit_sequence tool call."""
    sequence_file = arguments.get("sequence_file")
    email = arguments.get("email", "")
    strictness = arguments.get("strictness", "relaxed")
    extra_features = arguments.get("extra_features")
    gff3_file = arguments.get("gff3_file")
    sideload_file = arguments.get("sideload_file")
    server_type = arguments.get("server_type", "bacteria")

    async with _get_client(server_type) as client:
        job_id = await client.submit_job(
            sequence_file=sequence_file,
            ncbi_accession=None,
            email=email,
            strictness=strictness,
            extra_features=extra_features,
            gff3_file=gff3_file,
            sideload_file=sideload_file,
        )

    result = {
        "job_id": job_id,
        "message": (
            f"Job submitted successfully. Job ID: {job_id}\n"
            f"You can check the status using the check_job_status tool "
            f"or visit: {client.config.get_job_url(job_id)}"
        ),
        "results_url": client.config.get_job_url(job_id),
        "server_type": server_type,
    }

    return _format_success(result)


async def _handle_submit_ncbi(arguments: dict[str, Any]) -> list[ContentBlock]:
    """Handle the submit_ncbi tool call."""
    ncbi_accession = arguments.get("ncbi_accession")
    if not ncbi_accession:
        raise ValueError("ncbi_accession is required")

    email = arguments.get("email", "")
    strictness = arguments.get("strictness", "relaxed")
    extra_features = arguments.get("extra_features")
    server_type = arguments.get("server_type", "bacteria")

    client_config = AntiSmashConfig.for_server(server_type)

    async with _get_client(server_type) as client:
        job_id = await client.submit_job(
            sequence_file=None,
            ncbi_accession=ncbi_accession,
            email=email,
            strictness=strictness,
            extra_features=extra_features,
        )

    result = {
        "job_id": job_id,
        "message": (
            f"Job submitted successfully for NCBI accession '{ncbi_accession}'. "
            f"Job ID: {job_id}\n"
            f"You can check the status using the check_job_status tool "
            f"or visit: {client_config.get_job_url(job_id)}"
        ),
        "ncbi_accession": ncbi_accession,
        "results_url": client_config.get_job_url(job_id),
        "server_type": server_type,
    }

    return _format_success(result)


async def _handle_check_job_status(arguments: dict[str, Any]) -> list[ContentBlock]:
    """Handle the check_job_status tool call."""
    job_id = arguments.get("job_id")
    if not job_id:
        raise ValueError("job_id is required")

    server_type = arguments.get("server_type", "bacteria")

    async with _get_client(server_type) as client:
        status_info = await client.get_job_status(job_id)

    # Format the status message
    status = status_info.get("status", "unknown")
    status_messages = {
        JobStatus.QUEUED: "Job is queued and waiting to be processed.",
        JobStatus.RUNNING: "Job is currently running.",
        JobStatus.DONE: "Job is complete! Results are available.",
        JobStatus.ERROR: "Job encountered an error.",
        JobStatus.PENDING: "Job status is pending/unknown.",
    }

    status_info["message"] = status_messages.get(status, f"Job status: {status}")

    return _format_success(status_info)


async def _handle_wait_for_job(arguments: dict[str, Any]) -> list[ContentBlock]:
    """Handle the wait_for_job tool call."""
    job_id = arguments.get("job_id")
    if not job_id:
        raise ValueError("job_id is required")

    poll_interval = arguments.get("poll_interval", 30)
    max_wait = arguments.get("max_wait", 3600)
    server_type = arguments.get("server_type", "bacteria")

    async with _get_client(server_type) as client:
        final_status = await client.wait_for_job(
            job_id,
            poll_interval=poll_interval,
            max_wait=max_wait,
        )

    final_status["message"] = (
        f"Job {job_id} has completed successfully! "
        f"Use the get_job_results tool to retrieve the analysis results."
    )

    return _format_success(final_status)


async def _handle_get_job_results(arguments: dict[str, Any]) -> list[ContentBlock]:
    """Handle the get_job_results tool call."""
    job_id = arguments.get("job_id")
    if not job_id:
        raise ValueError("job_id is required")

    server_type = arguments.get("server_type", "bacteria")

    async with _get_client(server_type) as client:
        results = await client.get_job_results(job_id)

    # Format summary
    summary = results.get("summary", {})
    regions = results.get("regions", [])

    summary_text = f"antiSMASH Results for Job {job_id}\n"
    summary_text += f"{'=' * 50}\n\n"
    summary_text += f"Results URL: {results.get('url', 'N/A')}\n\n"

    if summary:
        summary_text += "Summary:\n"
        for key, value in summary.items():
            summary_text += f"  {key}: {value}\n"

    if regions:
        summary_text += f"\nDetected Regions ({len(regions)}):\n"
        for region in regions[:20]:  # Show first 20 regions
            summary_text += (
                f"  Region {region.get('region_number', '?')}: "
                f"Type={region.get('cluster_type', '?')}, "
                f"Start={region.get('start', '?')}, "
                f"End={region.get('end', '?')}\n"
            )
        if len(regions) > 20:
            summary_text += f"  ... and {len(regions) - 20} more regions\n"

    if not regions and not summary:
        summary_text += (
            "No detailed region information could be parsed from the results page.\n"
            "Please visit the results URL for the full HTML report.\n"
        )

    return [TextContent(type="text", text=summary_text)]


async def _handle_get_job_details(arguments: dict[str, Any]) -> list[ContentBlock]:
    """Handle the get_job_details tool call."""
    job_id = arguments.get("job_id")
    if not job_id:
        raise ValueError("job_id is required")

    server_type = arguments.get("server_type", "bacteria")

    async with _get_client(server_type) as client:
        details = await client.get_job_details(job_id)

    return _format_success(details)


async def _handle_download_results(arguments: dict[str, Any]) -> list[ContentBlock]:
    """Handle the download_results tool call."""
    job_id = arguments.get("job_id")
    output_path = arguments.get("output_path")

    if not job_id:
        raise ValueError("job_id is required")
    if not output_path:
        raise ValueError("output_path is required")

    server_type = arguments.get("server_type", "bacteria")

    async with _get_client(server_type) as client:
        saved_path = await client.download_results(job_id, output_path)

    result = {
        "message": f"Results downloaded successfully to: {saved_path}",
        "job_id": job_id,
        "saved_path": str(saved_path),
        "file_size_bytes": saved_path.stat().st_size,
    }

    return _format_success(result)


async def _handle_get_server_status(arguments: dict[str, Any]) -> list[ContentBlock]:
    """Handle the get_server_status tool call."""
    server_type = arguments.get("server_type", "bacteria")

    async with _get_client(server_type) as client:
        status = await client.get_server_status()

    status["server_type"] = server_type
    status["server_url"] = client.config.base_url

    # Add human-readable status
    if status.get("status") == "working":
        status["message"] = (
            "Server is working and accepting new jobs. "
            f"Currently {status.get('running_jobs', 0)} jobs running, "
            f"{status.get('queued_jobs', 0)} jobs queued."
        )
    else:
        status["message"] = (
            f"Server status: {status.get('status', 'unknown')}"
        )

    return _format_success(status)


async def _handle_list_extra_features(arguments: dict[str, Any]) -> list[ContentBlock]:
    """Handle the list_extra_features tool call."""
    features_text = "Available antiSMASH Extra Features:\n"
    features_text += "=" * 50 + "\n\n"

    for feature_id, description in ALL_EXTRA_FEATURES.items():
        features_text += f"  {feature_id}:\n    {description}\n\n"

    features_text += (
        "These features can be specified in the 'extra_features' parameter "
        "when using the submit_sequence or submit_ncbi tools.\n"
    )

    return [TextContent(type="text", text=features_text)]


async def _handle_get_example_url(arguments: dict[str, Any]) -> list[ContentBlock]:
    """Handle the get_example_url tool call."""
    server_type = arguments.get("server_type", "bacteria")

    async with _get_client(server_type) as client:
        url = await client.get_example_output_url()

    result = {
        "message": (
            f"Example antiSMASH output URL: {url}\n"
            "You can visit this URL to explore the format and content of "
            "antiSMASH results without submitting a job."
        ),
        "example_url": url,
        "server_type": server_type,
    }

    return _format_success(result)


# ---------------------------------------------------------------------------
# Server creation and entry point
# ---------------------------------------------------------------------------

def create_server() -> Server:
    """Create and configure the MCP server instance.

    Returns:
        Server: Configured MCP server with all antiSMASH tools registered.
    """
    server: Server = Server(
        "antismash-mcp",
        version=__version__,
        title="antiSMASH MCP Server",
        description=(
            "MCP server for the antiSMASH database - "
            "secondary metabolite biosynthetic gene cluster analysis"
        ),
        instructions=(
            "This server provides tools for interacting with the antiSMASH "
            "web service (https://antismash.secondarymetabolites.org). "
            "You can submit sequences for analysis, check job status, "
            "retrieve results, and download output files."
        ),
        on_list_tools=handle_list_tools,
        on_call_tool=handle_call_tool,
    )
    return server


async def run_server() -> None:
    """Run the MCP server using stdio transport."""
    logger.info("Starting antiSMASH MCP server v%s", __version__)

    server = create_server()

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    """Main entry point for the antiSMASH MCP server."""
    # Configure logging
    log_level = os.environ.get("ANTISMASH_MCP_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )

    # Allow overriding the default server type via environment variable
    default_server = os.environ.get("ANTISMASH_MCP_SERVER", "bacteria")
    if default_server in ("bacteria", "fungi", "plant"):
        set_default_config(AntiSmashConfig.for_server(default_server))

    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error("Server error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
