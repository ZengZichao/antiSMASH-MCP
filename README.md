# antiSMASH MCP 服务器

[![版本](https://img.shields.io/badge/version-0.1.0-blue.svg)](https://github.com/ZengZichao/antiSMASH-MCP)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![许可证](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> **⚠️ 非官方项目声明**：这是一个社区开发的非官方 MCP 服务器，与 antiSMASH 官方团队无关。antiSMASH 是 [antiSMASH 团队](https://antismash.secondarymetabolites.org/) 的产品，本项目仅通过其公开 Web API 进行交互。

> **antiSMASH MCP 服务器** 是一个基于 [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) 的服务器，用于与 [antiSMASH](https://antismash.secondarymetabolites.org/) 数据库进行交互，实现次级代谢产物生物合成基因簇的自动化分析。

[English Documentation](README_EN.md) | 中文文档

---

## 目录

- [概述](#概述)
- [功能特性](#功能特性)
- [安装](#安装)
- [配置](#配置)
- [使用方法](#使用方法)
- [可用工具](#可用工具)
- [MCP 客户端配置](#mcp客户端配置)
- [项目结构](#项目结构)
- [开发指南](#开发指南)
- [常见问题](#常见问题)
- [许可证](#许可证)

---

## 概述

[antiSMASH](https://antismash.secondarymetabolites.org/)（antibiotics & Secondary Metabolites Analysis Shell）是一个广泛使用的生物信息学工具，用于在基因组序列中识别次级代谢产物生物合成基因簇（BGCs）。antiSMASH 支持细菌、真菌和植物基因组分析，提供详细的基因簇类型、功能注释和比较分析结果。

本项目实现了一个 MCP 服务器，使 AI 助手（如 Claude）能够直接与 antiSMASH 数据库交互，实现以下功能：

- 📤 **提交分析任务**：上传序列文件或使用 NCBI 登录号提交分析
- 📊 **查询任务状态**：检查任务是否在运行、排队或已完成
- 📋 **获取分析结果**：解析检测到的生物合成基因簇和区域信息
- 📥 **下载结果文件**：下载完整的分析结果 ZIP 压缩包
- 🖥️ **服务器状态查询**：检查 antiSMASH 服务器运行状态

## 功能特性

### 支持的 antiSMASH 服务器

| 服务器类型 | 描述 | URL |
|-----------|------|-----|
| `bacteria` | 细菌版本（默认） | https://antismash.secondarymetabolites.org/ |
| `fungi` | 真菌版本 | https://fungismash.secondarymetabolites.org/ |
| `plant` | 植物版本 | http://plantismash.secondarymetabolites.org/ |

### 检测严格度

| 严格度 | 描述 |
|-------|------|
| `strict` | 严格模式：检测包含所有必需部分的完整基因簇 |
| `relaxed` | 宽松模式（默认）：检测缺少一个或多个功能部分的部分基因簇 |
| `loose` | 松散模式：使用更宽松的标准，可能包含更多假阳性结果 |

### 额外功能

| 功能名称 | 描述 |
|---------|------|
| `knownclusterblast` | KnownClusterBlast - 与 MIBiG 数据库中已知基因簇进行比对 |
| `clusterblast` | ClusterBlast - 与数据库中的基因簇进行比对 |
| `subclusterblast` | SubClusterBlast - 与已知亚簇进行比对 |
| `mibig` | MIBiG 基因簇比较 |
| `active_site_finder` | ActiveSiteFinder - 活性位点分析 |
| `rrefinder` | RREFinder - 检测 RRE（RiPP 识别元件）结构域 |
| `pfam2go` | 基于 Pfam 的 GO 术语注释 |
| `tigrfam` | TIGRFam 分析 |
| `tfbs` | TFBS 分析 - 转录因子结合位点分析 |
| `ncbi_context` | NCBI 基因组上下文链接 |

## 安装

### 前置条件

- Python 3.10 或更高版本
- pip 包管理器

### 从源码安装

```bash
# 克隆仓库
git clone https://github.com/ZengZichao/antiSMASH-MCP.git
cd antiSMASH-MCP

# 安装包（推荐使用虚拟环境）
pip install -e .
```

### 依赖项

以下依赖项会在安装时自动安装：

- `mcp>=1.0.0` - Model Context Protocol SDK
- `httpx>=0.25.0` - 异步 HTTP 客户端
- `pydantic>=2.0.0` - 数据验证

## 配置

### 环境变量

| 环境变量 | 默认值 | 描述 |
|---------|--------|------|
| `ANTISMASH_MCP_LOG_LEVEL` | `INFO` | 日志级别（DEBUG/INFO/WARNING/ERROR） |
| `ANTISMASH_MCP_SERVER` | `bacteria` | 默认 antiSMASH 服务器类型 |

### 配置示例

```bash
# 设置日志级别为 DEBUG
export ANTISMASH_MCP_LOG_LEVEL=DEBUG

# 使用真菌版本的 antiSMASH
export ANTISMASH_MCP_SERVER=fungi
```

## 使用方法

### 直接运行

```bash
# 使用默认配置运行
python -m antismash_mcp.server

# 或者使用安装的命令行工具
antismash-mcp
```

### 在 MCP 客户端中配置

#### Claude Desktop 配置

在 Claude Desktop 的配置文件中添加以下内容：

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

如果使用了虚拟环境，请指定完整路径：

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

#### Cursor / VS Code 配置

在 MCP 配置文件中添加：

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

## 可用工具

本 MCP 服务器提供以下 10 个工具：

### 1. `submit_sequence`

提交序列文件到 antiSMASH 进行分析。

**参数：**

| 参数名 | 类型 | 必填 | 默认值 | 描述 |
|-------|------|------|--------|------|
| `sequence_file` | string | 否* | - | 序列文件路径（GenBank/EMBL/FASTA 格式） |
| `email` | string | 否 | "" | 电子邮件地址（可选，用于通知） |
| `strictness` | string | 否 | `relaxed` | 检测严格度（strict/relaxed/loose） |
| `extra_features` | array | 否 | 见说明 | 额外功能列表 |
| `gff3_file` | string | 否 | - | GFF3 注释文件路径 |
| `sideload_file` | string | 否 | - | antiSMASH 注释旁加载 JSON 文件路径 |
| `server_type` | string | 否 | `bacteria` | 服务器类型（bacteria/fungi/plant） |

> *\*`sequence_file` 和 `ncbi_accession` 至少需要提供一个。*

**示例返回：**
```json
{
  "job_id": "ABC12345",
  "message": "Job submitted successfully. Job ID: ABC12345",
  "results_url": "https://antismash.secondarymetabolites.org/ABC12345",
  "server_type": "bacteria"
}
```

### 2. `submit_ncbi`

使用 NCBI 登录号提交分析任务。

**参数：**

| 参数名 | 类型 | 必填 | 默认值 | 描述 |
|-------|------|------|--------|------|
| `ncbi_accession` | string | 是 | - | NCBI 登录号（如 NC_003888.3） |
| `email` | string | 否 | "" | 电子邮件地址 |
| `strictness` | string | 否 | `relaxed` | 检测严格度 |
| `extra_features` | array | 否 | - | 额外功能列表 |
| `server_type` | string | 否 | `bacteria` | 服务器类型 |

### 3. `check_job_status`

检查任务状态。

**参数：**

| 参数名 | 类型 | 必填 | 默认值 | 描述 |
|-------|------|------|--------|------|
| `job_id` | string | 是 | - | antiSMASH 任务 ID |
| `server_type` | string | 否 | `bacteria` | 服务器类型 |

**返回状态值：**

| 状态 | 描述 |
|------|------|
| `queued` | 任务已排队，等待处理 |
| `running` | 任务正在运行 |
| `done` | 任务已完成，结果可用 |
| `error` | 任务遇到错误 |
| `pending` | 任务状态未知/等待中 |

### 4. `wait_for_job`

等待任务完成（阻塞操作）。

**参数：**

| 参数名 | 类型 | 必填 | 默认值 | 描述 |
|-------|------|------|--------|------|
| `job_id` | string | 是 | - | antiSMASH 任务 ID |
| `poll_interval` | integer | 否 | 30 | 状态检查间隔（秒） |
| `max_wait` | integer | 否 | 3600 | 最大等待时间（秒） |
| `server_type` | string | 否 | `bacteria` | 服务器类型 |

### 5. `get_job_results`

获取已完成任务的分析结果摘要。

**参数：**

| 参数名 | 类型 | 必填 | 默认值 | 描述 |
|-------|------|------|--------|------|
| `job_id` | string | 是 | - | antiSMASH 任务 ID |
| `server_type` | string | 否 | `bacteria` | 服务器类型 |

**返回内容：**
- 检测到的区域/基因簇列表
- 每个区域的类型、起始和终止位置
- 统计摘要信息

### 6. `get_job_details`

获取任务的详细信息（包括运行中和已完成的任务）。

**参数：**

| 参数名 | 类型 | 必填 | 默认值 | 描述 |
|-------|------|------|--------|------|
| `job_id` | string | 是 | - | antiSMASH 任务 ID |
| `server_type` | string | 否 | `bacteria` | 服务器类型 |

### 7. `download_results`

下载结果压缩包（ZIP 文件）到本地路径。

**参数：**

| 参数名 | 类型 | 必填 | 默认值 | 描述 |
|-------|------|------|--------|------|
| `job_id` | string | 是 | - | antiSMASH 任务 ID |
| `output_path` | string | 是 | - | 保存路径（文件或目录） |
| `server_type` | string | 否 | `bacteria` | 服务器类型 |

### 8. `get_server_status`

获取 antiSMASH 服务器状态。

**参数：**

| 参数名 | 类型 | 必填 | 默认值 | 描述 |
|-------|------|------|--------|------|
| `server_type` | string | 否 | `bacteria` | 服务器类型 |

**返回内容：**
- 服务器状态（working/maintenance）
- 当前运行中的任务数
- 排队中的任务数
- 已处理的总任务数

### 9. `list_extra_features`

列出所有可用的额外功能及其描述。

**参数：** 无

### 10. `get_example_url`

获取 antiSMASH 示例输出页面的 URL。

**参数：**

| 参数名 | 类型 | 必填 | 默认值 | 描述 |
|-------|------|------|--------|------|
| `server_type` | string | 否 | `bacteria` | 服务器类型 |

## MCP客户端配置

### 完整配置示例

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

### 使用场景示例

以下是在 AI 助手中使用本 MCP 服务器的典型对话示例：

#### 场景 1：提交并分析基因组序列

```
用户：帮我提交 NC_003888.3 到 antiSMASH 进行分析
AI：好的，我正在使用 submit_ncbi 工具提交 NCBI 登录号 NC_003888.3 到 antiSMASH...
    [调用 submit_ncbi 工具]
    任务已提交！任务 ID: ABC12345
    你可以在以下网址查看结果: https://antismash.secondarymetabolites.org/ABC12345

用户：检查一下任务状态
AI：[调用 check_job_status 工具]
    任务目前正在运行中...
```

#### 场景 2：获取分析结果

```
用户：任务完成了吗？帮我看看结果
AI：[调用 check_job_status 工具]
    任务已完成！让我获取分析结果...
    [调用 get_job_results 工具]
    
    antiSMASH 分析结果：
    - 检测到 12 个生物合成区域
    - 基因簇类型：NRPS, PKS Type I, Terpene, Siderophore 等
    - 详见结果页面: https://antismash.secondarymetabolites.org/ABC12345
```

#### 场景 3：下载结果

```
用户：把结果下载到 /home/user/results 目录
AI：[调用 download_results 工具]
    结果已成功下载到 /home/user/results/ABC12345.zip
    文件大小: 15.3 MB
```

## 项目结构

```
antiSMASH-MCP/
├── src/
│   └── antismash_mcp/
│       ├── __init__.py          # 包初始化
│       ├── config.py            # 配置模块
│       ├── antismash_client.py  # antiSMASH API 客户端
│       └── server.py            # MCP 服务器实现
├── tests/
│   ├── __init__.py              # 测试包初始化
│   └── test_server.py           # 测试文件
├── .gitignore                   # Git 忽略配置
├── pyproject.toml               # 项目配置
├── LICENSE                      # 许可证
├── README.md                    # 中文说明（本文件）
└── README_EN.md                 # 英文说明
```

## 开发指南

### 开发环境搭建

```bash
# 克隆仓库
git clone https://github.com/ZengZichao/antiSMASH-MCP.git
cd antiSMASH-MCP

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# 或 .venv\Scripts\activate  # Windows

# 安装开发依赖
pip install -e ".[dev]"
```

### 代码风格

本项目使用以下工具保持代码质量：

- **ruff** - 代码格式化和 linting
- **mypy** - 类型检查
- **pytest** - 单元测试

```bash
# 运行 linting
ruff check src/

# 运行类型检查
mypy src/

# 运行测试
pytest
```

### 运行测试

```bash
# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/test_server.py

# 显示详细输出
pytest -v
```

### 添加新工具

要添加新的 MCP 工具，需要：

1. 在 `server.py` 的 `handle_list_tools` 函数中添加工具定义
2. 在 `handle_call_tool` 函数中添加处理逻辑
3. 在 `antismash_client.py` 中实现 API 交互逻辑
4. 编写对应的测试

## 常见问题

### 1. 提交任务时遇到 403 错误

**问题**：提交序列文件时返回 403 Forbidden 错误。

**解决方案**：
- antiSMASH 服务器有并发任务限制（建议最多 5 个并发任务）
- 等待之前的任务完成后再提交新任务
- 使用 NCBI 登录号方式提交（`submit_ncbi` 工具）
- 检查 antiSMASH 服务器状态（使用 `get_server_status` 工具）

### 2. 任务运行时间过长

**问题**：antiSMASH 分析可能需要 10 分钟到数小时不等。

**解决方案**：
- 使用 `wait_for_job` 工具时设置合理的 `max_wait` 参数
- 提供电子邮箱地址，antiSMASH 会在任务完成时发送通知
- 定期使用 `check_job_status` 工具检查状态

### 3. 无法获取详细结果

**问题**：`get_job_results` 返回的结果信息不完整。

**解决方案**：
- 确保任务已完成（状态为 `done`）
- 使用 `get_job_details` 获取更详细的信息
- 直接访问结果页面 URL 获取完整 HTML 报告
- 使用 `download_results` 下载完整的 ZIP 压缩包

### 4. 连接超时

**问题**：连接 antiSMASH 服务器超时。

**解决方案**：
- 检查网络连接
- antiSMASH 服务器可能因高负载而响应缓慢
- 在配置中增加超时时间

### 5. Windows 路径问题

**问题**：在 Windows 上使用反斜杠路径导致错误。

**解决方案**：
- 使用正斜杠 `/` 作为路径分隔符
- 或使用原始字符串（raw string）指定路径

## 许可证

本项目使用 [MIT 许可证](LICENSE)。

## 致谢

- [antiSMASH](https://antismash.secondarymetabolites.org/) 团队提供的优秀生物信息学工具
- [Model Context Protocol](https://modelcontextprotocol.io/) 提供的协议规范

---

## 引用

如果您在研究中使用了基于本工具的 antiSMASH 分析结果，请引用 antiSMASH：

> Blin, K., Shaw, S., Augustijn, H.E. et al. antiSMASH 7.0: new and improved predictions for detection, regulation, chemical structures and visualisation. Nucleic Acids Res. 51, W46–W50 (2023).
