# antiSMASH MCP Server

[![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)](https://github.com/ZengZichao/antiSMASH-MCP)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> **⚠️ Unofficial Project Notice**: This is a community-developed, unofficial MCP server and is not affiliated with the antiSMASH team. antiSMASH is a product of the [antiSMASH team](https://antismash.secondarymetabolites.org/); this project only interacts with its public Web API.

> **antiSMASH MCP Server** is a Model Context Protocol (MCP) server for interacting with the [antiSMASH](https://antismash.secondarymetabolites.org/) database, enabling automated secondary metabolite biosynthetic gene cluster analysis.

中文文档 | [English Documentation](README.md)

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Available Tools](#available-tools)
- [MCP Client Configuration](#mcp-client-configuration)
- [Project Structure](#project-structure)
- [Development Guide](#development-guide)
- [FAQ](#faq)
- [License](#license)

---

## Overview

[antiSMASH](https://antismash.secondarymetabolites.org/) (antibiotics & Secondary Metabolites Analysis Shell) is a widely-used bioinformatics tool for identifying secondary metabolite biosynthetic gene clusters (BGCs) in genomic sequences. antiSMASH supports bacterial, fungal, and plant genome analysis, providing detailed cluster types, functional annotations, and comparative analysis results.

This project implements an MCP server that allows AI assistants (such as Claude) to interact directly with the antiSMASH database, enabling the following capabilities:

- 📤 **Submit Analysis Jobs**: Upload sequence files or use NCBI accession numbers
- 📊 **Check Job Status**: Monitor whether jobs are running, queued, or completed
- 📋 **Retrieve Analysis Results**: Parse detected biosynthetic gene clusters and region information
- 📥 **Download Result Files**: Download complete analysis results as ZIP archives
- 🖥️ **Server Status Query**: Check antiSMASH server availability and load

## Features

### Supported antiSMASH Servers

| Server Type | Description | URL |
|-------------|-------------|-----|
| `bacteria` | Bacterial version (default) | https://antismash.secondarymetabolites.org/ |
| `fungi` | Fungal version | https://fungismash.secondarymetabolites.org/ |
| `plant` | Plant version | http://plantismash.secondarymetabolites.org/ |

### Detection Strictness

| Strictness | Description |
|------------|-------------|
| `strict` | Strict mode: Detects well-defined clusters containing all required parts |
| `relaxed` | Relaxed mode (default): Detects partial clusters missing one or more functional parts |
| `loose` | Loose mode: Uses looser criteria, may include more false positives |

### Extra Features

| Feature Name | Description |
|--------------|-------------|
| `knownclusterblast` | KnownClusterBlast - Compare against known clusters from MIBiG |
| `clusterblast` | ClusterBlast - Compare gene clusters against a database |
| `subclusterblast` | SubClusterBlast - Compare against known subclusters |
| `mibig` | MIBiG cluster comparison |
| `active_site_finder` | ActiveSiteFinder - Analyze active sites |
| `rrefinder` | RREFinder - Detect RRE (RiPP Recognition Element) domains |
| `pfam2go` | Pfam-based GO term annotation |
| `tigrfam` | TIGRFam analysis |
| `tfbs` | TFBS analysis - Transcription Factor Binding Site analysis |
| `ncbi_context` | NCBI genomic context links |

## Installation

### Prerequisites

- Python 3.10 or higher
- pip package manager

### Install from Source

```bash
# Clone the repository
git clone https://github.com/ZengZichao/antiSMASH-MCP.git
cd antiSMASH-MCP

# Install the package (virtual environment recommended)
pip install -e .
```

### Dependencies

The following dependencies are installed automatically:

- `mcp>=1.0.0` - Model Context Protocol SDK
- `httpx>=0.25.0` - Async HTTP client
- `pydantic>=2.0.0` - Data validation

## Configuration

### Environment Variables

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `ANTISMASH_MCP_LOG_LEVEL` | `INFO` | Log level (DEBUG/INFO/WARNING/ERROR) |
| `ANTISMASH_MCP_SERVER` | `bacteria` | Default antiSMASH server type |

### Configuration Examples

```bash
# Set log level to DEBUG
export ANTISMASH_MCP_LOG_LEVEL=DEBUG

# Use the fungal version of antiSMASH
export ANTISMASH_MCP_SERVER=fungi
```

## Usage

### Direct Execution

```bash
# Run with default configuration
python -m antismash_mcp.server

# Or use the installed command-line tool
antismash-mcp
```

### Configure in MCP Clients

#### Claude Desktop Configuration

Add the following to your Claude Desktop configuration file:

**macOS/Linux**: `~/.config/claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "antismash": {
      "command": "python",
      "args": ["-m", "antismash_mcp.server"],
      "env": {
        "ANTISMASH_MCP_LOG_LEVEL": "INFO"
      }
    }
  }
}
```

If using a virtual environment, specify the full path:

```json
{
  "mcpServers": {
    "antismash": {
      "command": "/path/to/venv/bin/python",
      "args": ["-m", "antismash_mcp.server"]
    }
  }
}
```

#### Cursor / VS Code Configuration

Add to your MCP configuration file:

```json
{
  "servers": {
    "antismash": {
      "command": "python",
      "args": ["-m", "antismash_mcp.server"]
    }
  }
}
```

## Available Tools

This MCP server provides the following 10 tools:

### 1. `submit_sequence`

Submit a sequence file to antiSMASH for analysis.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `sequence_file` | string | No* | - | Path to sequence file (GenBank/EMBL/FASTA format) |
| `email` | string | No | "" | Email address for notifications (optional) |
| `strictness` | string | No | `relaxed` | Detection strictness (strict/relaxed/loose) |
| `extra_features` | array | No | See notes | List of extra features to enable |
| `gff3_file` | string | No | - | Path to GFF3 annotation file |
| `sideload_file` | string | No | - | Path to antiSMASH annotations sideload JSON file |
| `server_type` | string | No | `bacteria` | Server type (bacteria/fungi/plant) |

> *\*Either `sequence_file` or `ncbi_accession` (in `submit_ncbi`) must be provided.*

**Example Response:**
```json
{
  "job_id": "ABC12345",
  "message": "Job submitted successfully. Job ID: ABC12345",
  "results_url": "https://antismash.secondarymetabolites.org/ABC12345",
  "server_type": "bacteria"
}
```

### 2. `submit_ncbi`

Submit an NCBI accession number for analysis.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `ncbi_accession` | string | Yes | - | NCBI accession number (e.g., NC_003888.3) |
| `email` | string | No | "" | Email address |
| `strictness` | string | No | `relaxed` | Detection strictness |
| `extra_features` | array | No | - | Extra features list |
| `server_type` | string | No | `bacteria` | Server type |

### 3. `check_job_status`

Check the status of a submitted job.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `job_id` | string | Yes | - | antiSMASH job ID |
| `server_type` | string | No | `bacteria` | Server type |

**Status Values:**

| Status | Description |
|--------|-------------|
| `queued` | Job is queued and waiting to be processed |
| `running` | Job is currently running |
| `done` | Job is complete, results are available |
| `error` | Job encountered an error |
| `pending` | Job status is unknown/pending |

### 4. `wait_for_job`

Wait for a job to complete (blocking operation).

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `job_id` | string | Yes | - | antiSMASH job ID |
| `poll_interval` | integer | No | 30 | Status check interval (seconds) |
| `max_wait` | integer | No | 3600 | Maximum wait time (seconds) |
| `server_type` | string | No | `bacteria` | Server type |

### 5. `get_job_results`

Get the analysis results summary for a completed job.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `job_id` | string | Yes | - | antiSMASH job ID |
| `server_type` | string | No | `bacteria` | Server type |

**Returns:**
- List of detected regions/gene clusters
- Each region's type, start, and end positions
- Summary statistics

### 6. `get_job_details`

Get detailed information about a job (works for both running and completed jobs).

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `job_id` | string | Yes | - | antiSMASH job ID |
| `server_type` | string | No | `bacteria` | Server type |

### 7. `download_results`

Download the results archive (ZIP file) to a local path.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `job_id` | string | Yes | - | antiSMASH job ID |
| `output_path` | string | Yes | - | Save path (file or directory) |
| `server_type` | string | No | `bacteria` | Server type |

### 8. `get_server_status`

Get the current status of the antiSMASH server.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `server_type` | string | No | `bacteria` | Server type |

**Returns:**
- Server status (working/maintenance)
- Number of currently running jobs
- Number of queued jobs
- Total number of jobs processed

### 9. `list_extra_features`

List all available extra features with their descriptions.

**Parameters:** None

### 10. `get_example_url`

Get the URL for the example antiSMASH output page.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `server_type` | string | No | `bacteria` | Server type |

## MCP Client Configuration

### Complete Configuration Example

```json
{
  "mcpServers": {
    "antismash-bacteria": {
      "command": "python",
      "args": ["-m", "antismash_mcp.server"],
      "env": {
        "ANTISMASH_MCP_SERVER": "bacteria",
        "ANTISMASH_MCP_LOG_LEVEL": "INFO"
      }
    },
    "antismash-fungi": {
      "command": "python",
      "args": ["-m", "antismash_mcp.server"],
      "env": {
        "ANTISMASH_MCP_SERVER": "fungi"
      }
    }
  }
}
```

### Usage Examples

The following are typical conversation examples of using this MCP server with an AI assistant:

#### Scenario 1: Submit and Analyze a Genome Sequence

```
User: Please submit NC_003888.3 to antiSMASH for analysis
AI: I'm submitting NCBI accession NC_003888.3 to antiSMASH using the submit_ncbi tool...
    [Calls submit_ncbi tool]
    Job submitted successfully! Job ID: ABC12345
    You can view the results at: https://antismash.secondarymetabolites.org/ABC12345

User: Check the job status
AI: [Calls check_job_status tool]
    The job is currently running...
```

#### Scenario 2: Retrieve Analysis Results

```
User: Is the job done? Show me the results
AI: [Calls check_job_status tool]
    The job is complete! Let me retrieve the analysis results...
    [Calls get_job_results tool]
    
    antiSMASH Analysis Results:
    - 12 biosynthetic regions detected
    - Cluster types: NRPS, PKS Type I, Terpene, Siderophore, etc.
    - See full results at: https://antismash.secondarymetabolites.org/ABC12345
```

#### Scenario 3: Download Results

```
User: Download the results to /home/user/results
AI: [Calls download_results tool]
    Results downloaded successfully to /home/user/results/ABC12345.zip
    File size: 15.3 MB
```

## Project Structure

```
antiSMASH-MCP/
├── src/
│   └── antismash_mcp/
│       ├── __init__.py          # Package initialization
│       ├── config.py            # Configuration module
│       ├── antismash_client.py  # antiSMASH API client
│       └── server.py            # MCP server implementation
├── tests/
│   ├── __init__.py              # Tests package initialization
│   └── test_server.py           # Test files
├── .gitignore                   # Git ignore configuration
├── pyproject.toml               # Project configuration
├── LICENSE                      # License file
├── README.md                    # Chinese documentation
└── README_EN.md                 # English documentation (this file)
```

## Development Guide

### Development Setup

```bash
# Clone the repository
git clone https://github.com/ZengZichao/antiSMASH-MCP.git
cd antiSMASH-MCP

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# or .venv\Scripts\activate  # Windows

# Install development dependencies
pip install -e ".[dev]"
```

### Code Style

This project uses the following tools to maintain code quality:

- **ruff** - Code formatting and linting
- **mypy** - Type checking
- **pytest** - Unit testing

```bash
# Run linting
ruff check src/

# Run type checking
mypy src/

# Run tests
pytest
```

### Running Tests

```bash
# Run all tests
pytest

# Run a specific test file
pytest tests/test_server.py

# Show verbose output
pytest -v
```

### Adding New Tools

To add a new MCP tool:

1. Add the tool definition in the `handle_list_tools` function in `server.py`
2. Add the handling logic in the `handle_call_tool` function
3. Implement the API interaction logic in `antismash_client.py`
4. Write corresponding tests

## FAQ

### 1. Encountering 403 Error When Submitting Jobs

**Issue**: Submitting a sequence file returns a 403 Forbidden error.

**Solution**:
- The antiSMASH server has a concurrent job limit (recommended maximum of 5 concurrent jobs)
- Wait for previous jobs to complete before submitting new ones
- Try using the NCBI accession method (`submit_ncbi` tool)
- Check the antiSMASH server status (use the `get_server_status` tool)

### 2. Job Takes Too Long

**Issue**: antiSMASH analysis can take anywhere from 10 minutes to several hours.

**Solution**:
- Set a reasonable `max_wait` parameter when using the `wait_for_job` tool
- Provide an email address; antiSMASH will send notifications when the job is complete
- Periodically check the status using the `check_job_status` tool

### 3. Unable to Get Detailed Results

**Issue**: The `get_job_results` tool returns incomplete information.

**Solution**:
- Ensure the job is completed (status is `done`)
- Use `get_job_details` for more detailed information
- Visit the results page URL directly for the full HTML report
- Use `download_results` to download the complete ZIP archive

### 4. Connection Timeout

**Issue**: Connection to the antiSMASH server times out.

**Solution**:
- Check your network connection
- The antiSMASH server may be slow to respond due to high load
- Increase the timeout in the configuration

### 5. Windows Path Issues

**Issue**: Using backslash paths on Windows causes errors.

**Solution**:
- Use forward slashes `/` as path separators
- Or use raw strings for paths

## License

This project is licensed under the [MIT License](LICENSE).

## Acknowledgments

- The [antiSMASH](https://antismash.secondarymetabolites.org/) team for their excellent bioinformatics tool
- [Model Context Protocol](https://modelcontextprotocol.io/) for the protocol specification

---

## Citation

If you use antiSMASH analysis results obtained through this tool in your research, please cite antiSMASH:

> Blin, K., Shaw, S., Augustijn, H.E. et al. antiSMASH 7.0: new and improved predictions for detection, regulation, chemical structures and visualisation. Nucleic Acids Res. 51, W46–W50 (2023).
