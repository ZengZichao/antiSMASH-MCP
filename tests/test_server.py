"""Tests for the antiSMASH MCP server."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from antismash_mcp.antismash_client import (
    AntiSmashClient,
    AntiSmashError,
    AntiSmashSubmissionError,
    JobStatus,
)
from antismash_mcp.config import (
    ALL_EXTRA_FEATURES,
    EXTRA_FEATURES,
    AntiSmashConfig,
    ServerType,
    Strictness,
)
from antismash_mcp.server import (
    __version__,
    create_server,
    handle_call_tool,
    handle_list_tools,
)

# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

class TestConfig:
    """Tests for the configuration module."""

    def test_strictness_values(self):
        """Test that strictness enum has correct values."""
        assert Strictness.STRICT.value == "strict"
        assert Strictness.RELAXED.value == "relaxed"
        assert Strictness.LOOSE.value == "loose"

    def test_strictness_from_string(self):
        """Test creating Strictness from string."""
        assert Strictness.from_string("strict") == Strictness.STRICT
        assert Strictness.from_string("RELAXED") == Strictness.RELAXED
        assert Strictness.from_string("loose") == Strictness.LOOSE

    def test_strictness_from_string_invalid(self):
        """Test invalid strictness string raises error."""
        with pytest.raises(ValueError, match="Invalid strictness"):
            Strictness.from_string("invalid")

    def test_server_type_values(self):
        """Test that server type enum has correct values."""
        assert ServerType.BACTERIA.value == "bacteria"
        assert ServerType.FUNGI.value == "fungi"
        assert ServerType.PLANT.value == "plant"

    def test_server_type_from_string(self):
        """Test creating ServerType from string."""
        assert ServerType.from_string("bacteria") == ServerType.BACTERIA
        assert ServerType.from_string("FUNGI") == ServerType.FUNGI
        assert ServerType.from_string("plant") == ServerType.PLANT

    def test_antismash_config_default(self):
        """Test default configuration."""
        config = AntiSmashConfig()
        assert config.server_type == ServerType.BACTERIA
        assert config.base_url == "https://antismash.secondarymetabolites.org"
        assert config.timeout == 30
        assert config.poll_interval == 30

    def test_antismash_config_for_server(self):
        """Test creating config for different server types."""
        bacteria_config = AntiSmashConfig.for_server("bacteria")
        assert bacteria_config.base_url == "https://antismash.secondarymetabolites.org"

        fungi_config = AntiSmashConfig.for_server("fungi")
        assert fungi_config.base_url == "https://fungismash.secondarymetabolites.org"

        plant_config = AntiSmashConfig.for_server("plant")
        assert plant_config.base_url == "http://plantismash.secondarymetabolites.org"

    def test_get_job_url(self):
        """Test job URL generation."""
        config = AntiSmashConfig()
        assert config.get_job_url("ABC123") == "https://antismash.secondarymetabolites.org/ABC123"

    def test_get_job_download_url(self):
        """Test download URL generation."""
        config = AntiSmashConfig()
        assert config.get_job_download_url("ABC123") == "https://antismash.secondarymetabolites.org/ABC123.zip"
        assert config.get_job_download_url("ABC123", "file.gbk") == "https://antismash.secondarymetabolites.org/ABC123/file.gbk"

    def test_extra_features_list(self):
        """Test that all expected extra features are defined."""
        expected = {
            "knownclusterblast", "clusterblast", "subclusterblast",
            "mibig", "active_site_finder", "rrefinder",
            "pfam2go", "tigrfam", "tfbs", "ncbi_context",
        }
        assert set(EXTRA_FEATURES) == expected
        assert set(ALL_EXTRA_FEATURES.keys()) == expected


# ---------------------------------------------------------------------------
# Client tests
# ---------------------------------------------------------------------------

class TestAntiSmashClient:
    """Tests for the antiSMASH client."""

    def test_client_creation(self):
        """Test client creation."""
        client = AntiSmashClient()
        assert client.config.base_url == "https://antismash.secondarymetabolites.org"
        assert client._client is None

    def test_client_creation_custom_config(self):
        """Test client with custom config."""
        config = AntiSmashConfig.for_server("fungi")
        client = AntiSmashClient(config)
        assert client.config.base_url == "https://fungismash.secondarymetabolites.org"

    def test_client_submit_no_input(self):
        """Test that submission without input raises error."""
        client = AntiSmashClient()
        with pytest.raises(AntiSmashSubmissionError, match="must be provided"):
            asyncio.run(client.submit_job())

    def test_parse_status_from_html_done(self):
        """Test parsing HTML status when job is done."""
        client = AntiSmashClient()
        html = '<html><body>Download results. Region 1 detected.</body></html>'
        status = client._parse_status_from_html(html, "test_job")
        assert status == JobStatus.DONE

    def test_parse_status_from_html_running(self):
        """Test parsing HTML status when job is running."""
        client = AntiSmashClient()
        html = '<html><body>Your job is still being processed</body></html>'
        status = client._parse_status_from_html(html, "test_job")
        assert status == JobStatus.RUNNING

    def test_parse_status_from_html_queued(self):
        """Test parsing HTML status when job is queued."""
        client = AntiSmashClient()
        html = '<html><body>Job is still being processed and queued</body></html>'
        status = client._parse_status_from_html(html, "test_job")
        assert status == JobStatus.QUEUED

    def test_extract_job_id_from_location_header(self):
        """Test extracting job ID from Location header."""
        client = AntiSmashClient()
        response = MagicMock()
        response.headers = {"location": "https://antismash.secondarymetabolites.org/ABC12345"}
        response.text = ""
        job_id = client._extract_job_id_from_response(response)
        assert job_id == "ABC12345"

    def test_extract_job_id_from_response_body(self):
        """Test extracting job ID from response body."""
        client = AntiSmashClient()
        response = MagicMock()
        response.headers = {}
        response.text = '<a href="/XYZ78901">Results</a>'
        job_id = client._extract_job_id_from_response(response)
        assert job_id == "XYZ78901"

    def test_extract_job_id_not_found(self):
        """Test when job ID cannot be extracted."""
        client = AntiSmashClient()
        response = MagicMock()
        response.headers = {}
        response.text = "no job id here"
        job_id = client._extract_job_id_from_response(response)
        assert job_id is None

    def test_submit_job_invalid_extra_feature(self):
        """Test that invalid extra features raise an error."""
        client = AntiSmashClient()
        with pytest.raises(AntiSmashSubmissionError, match="Invalid extra feature"):
            asyncio.run(
                client.submit_job(
                    ncbi_accession="NC_003888.3",
                    extra_features=["invalid_feature"],
                )
            )

    @pytest.mark.asyncio
    async def test_download_and_extract_path_traversal_protection(self):
        """Test that path traversal in ZIP archives is blocked."""
        import tempfile
        import zipfile
        from io import BytesIO

        client = AntiSmashClient()

        # Create a malicious ZIP with path traversal
        malicious_zip = BytesIO()
        with zipfile.ZipFile(malicious_zip, "w") as zf:
            zf.writestr("../../evil.txt", "malicious content")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = malicious_zip.getvalue()

        with tempfile.TemporaryDirectory() as tmpdir, patch.object(
            client, "_make_request", new_callable=AsyncMock, return_value=mock_response
        ), pytest.raises(AntiSmashError, match="Unsafe file path"):
            await client.download_and_extract_results("TEST123", tmpdir)


# ---------------------------------------------------------------------------
# Server tests
# ---------------------------------------------------------------------------

class TestServer:
    """Tests for the MCP server."""

    def test_server_creation(self):
        """Test server creation."""
        server = create_server()
        assert server.name == "antismash-mcp"
        assert server.version == __version__
        assert server.title == "antiSMASH MCP Server"

    def test_version(self):
        """Test version is set correctly."""
        assert __version__ == "0.1.0"

    @pytest.mark.asyncio
    async def test_list_tools(self):
        """Test that list_tools returns all expected tools."""
        ctx = MagicMock()
        result = await handle_list_tools(ctx, None)

        tool_names = [tool.name for tool in result.tools]
        expected_tools = [
            "submit_sequence",
            "submit_ncbi",
            "check_job_status",
            "wait_for_job",
            "get_job_results",
            "get_job_details",
            "download_results",
            "get_server_status",
            "list_extra_features",
            "get_example_url",
        ]
        assert set(tool_names) == set(expected_tools)
        assert len(result.tools) == 10

    @pytest.mark.asyncio
    async def test_list_extra_features_tool(self):
        """Test the list_extra_features tool."""
        from mcp.types import CallToolRequestParams
        ctx = MagicMock()
        params = CallToolRequestParams(name="list_extra_features", arguments={})
        result = await handle_call_tool(ctx, params)

        assert not result.is_error
        assert len(result.content) == 1
        text = result.content[0].text
        assert "knownclusterblast" in text
        assert "clusterblast" in text
        assert "rrefinder" in text

    @pytest.mark.asyncio
    async def test_unknown_tool(self):
        """Test calling an unknown tool returns error."""
        from mcp.types import CallToolRequestParams
        ctx = MagicMock()
        params = CallToolRequestParams(name="nonexistent_tool", arguments={})
        result = await handle_call_tool(ctx, params)

        assert result.is_error
        assert "Unknown tool" in result.content[0].text

    @pytest.mark.asyncio
    async def test_check_job_status_missing_id(self):
        """Test check_job_status with missing job_id."""
        from mcp.types import CallToolRequestParams
        ctx = MagicMock()
        params = CallToolRequestParams(name="check_job_status", arguments={})
        result = await handle_call_tool(ctx, params)

        assert result.is_error
        assert "job_id is required" in result.content[0].text

    @pytest.mark.asyncio
    async def test_submit_ncbi_missing_accession(self):
        """Test submit_ncbi with missing ncbi_accession."""
        from mcp.types import CallToolRequestParams
        ctx = MagicMock()
        params = CallToolRequestParams(name="submit_ncbi", arguments={})
        result = await handle_call_tool(ctx, params)

        assert result.is_error
        assert "ncbi_accession is required" in result.content[0].text

    @pytest.mark.asyncio
    async def test_download_results_missing_params(self):
        """Test download_results with missing parameters."""
        from mcp.types import CallToolRequestParams
        ctx = MagicMock()
        params = CallToolRequestParams(name="download_results", arguments={})
        result = await handle_call_tool(ctx, params)

        assert result.is_error

    @pytest.mark.asyncio
    async def test_get_example_url(self):
        """Test get_example_url tool."""
        from mcp.types import CallToolRequestParams
        ctx = MagicMock()
        params = CallToolRequestParams(name="get_example_url", arguments={})
        result = await handle_call_tool(ctx, params)

        # This may fail if there's no network, so we just check the structure
        if not result.is_error:
            text = result.content[0].text
            data = json.loads(text)
            assert "example_url" in data

    @pytest.mark.asyncio
    async def test_tool_input_schemas(self):
        """Test that all tools have valid input schemas."""
        ctx = MagicMock()
        result = await handle_list_tools(ctx, None)

        for tool in result.tools:
            assert tool.input_schema is not None
            assert tool.input_schema.get("type") == "object"
            assert "properties" in tool.input_schema


# ---------------------------------------------------------------------------
# Integration tests (mocked)
# ---------------------------------------------------------------------------

class TestIntegration:
    """Integration tests with mocked HTTP responses."""

    @pytest.mark.asyncio
    async def test_submit_ncbi_mocked(self):
        """Test submit_ncbi with mocked client."""
        from mcp.types import CallToolRequestParams

        ctx = MagicMock()
        params = CallToolRequestParams(
            name="submit_ncbi",
            arguments={"ncbi_accession": "NC_003888.3"},
        )

        # Mock the AntiSmashClient
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.submit_job = AsyncMock(return_value="MOCK_JOB_ID")
        mock_client.config = AntiSmashConfig()

        with patch("antismash_mcp.server._get_client", return_value=mock_client):
            result = await handle_call_tool(ctx, params)

        assert not result.is_error
        text = result.content[0].text
        data = json.loads(text)
        assert data["job_id"] == "MOCK_JOB_ID"
        assert "NC_003888.3" in data["message"]

    @pytest.mark.asyncio
    async def test_check_job_status_mocked(self):
        """Test check_job_status with mocked client."""
        from mcp.types import CallToolRequestParams

        ctx = MagicMock()
        params = CallToolRequestParams(
            name="check_job_status",
            arguments={"job_id": "TEST123"},
        )

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get_job_status = AsyncMock(
            return_value={"job_id": "TEST123", "status": "running"}
        )

        with patch("antismash_mcp.server._get_client", return_value=mock_client):
            result = await handle_call_tool(ctx, params)

        assert not result.is_error
        text = result.content[0].text
        data = json.loads(text)
        assert data["status"] == "running"
        assert "currently running" in data["message"]
