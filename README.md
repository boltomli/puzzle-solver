# 🔍 Puzzle Solver — 剧本杀推理助手

一款专为剧本杀（谋杀之谜）游戏设计的智能推理辅助工具。通过构建人物×地点×时间的三维推理矩阵，结合 AI 推断和消元法，帮助玩家系统化地梳理线索、推理真相。

## ✨ 功能概览

### 📜 剧本管理
- 录入和管理游戏中的各角色剧本文本
- 支持标题、备注等元数据
- 🤖 AI 剧本分析：自动提取人物、地点、时间引用和直接事实
- 支持 Ctrl+Enter 快捷保存

### 📊 推理矩阵
- 人物×时间 的交叉矩阵表格，直观显示每个角色在每个时间段的位置
- 绿色标记已确认事实，黄色标记待审查推断
- 点击空白格可快速录入事实
- 矩阵统计：总格数、已确认、待审查、完成度百分比

### 🤖 AI 推断
- 基于 OpenAI 兼容 API 的智能推理引擎
- 分析所有剧本、已知事实、游戏规则，推断未知的人物位置
- 支持多种置信度级别：确定、高、中、低
- 自动检测矛盾并提示
- 自动发现新人物和新地点

### 🔄 消元推断
- 本地消元法推理，无需 AI API
- 当某个人物在某时间段只剩一个可能地点时，自动推断
- 当某个地点在某时间段只剩一个可能人物时，自动推断
- 接受推断后自动触发消元连锁反应

### ✅ 推断审查
- 审查 AI 和消元法产生的推断候选
- 按置信度排序：确定 → 高 → 中 → 低
- 接受推断自动创建事实，拒绝推断记录原因
- 接受后自动运行消元推断，产生连锁效应
- 推断历史记录：查看所有已接受和已拒绝的推断

### 🏗️ 实体管理
- 人物管理：姓名、别名、描述、状态（已确认/疑似/未知）
- 地点管理：名称、别名、描述
- 时间段管理：HH:MM 格式
- 游戏规则/提示/约束
- 手动事实录入和管理

### ⚙️ 设置
- OpenAI 兼容 API 配置（Base URL、API Key、模型）
- 自定义系统提示词
- API 连接测试
- 项目删除（需输入项目名确认）

### 🎨 界面特性
- 深色/浅色模式切换
- 5 个功能标签页：剧本、矩阵、管理、审查、设置
- 多项目支持，项目间快速切换
- 空白状态引导提示
- 操作过程加载动画

## 📦 安装

### 前置要求

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) 包管理器（推荐）

### 安装步骤

```bash
# 克隆项目
git clone <仓库地址>
cd puzzle-solver

# 使用 uv 创建虚拟环境并安装依赖
uv sync

# 或使用 pip
python -m venv .venv
.venv/Scripts/activate  # Windows
# source .venv/bin/activate  # Linux/macOS
pip install -e .
```

## 🚀 运行

### 桌面模式（默认）

```bash
# 使用 uv
uv run python main.py

# 或直接运行
.venv/Scripts/python main.py
```

将以原生桌面窗口形式启动（1400×900）。

### Web 模式

```bash
# 通过环境变量
set PUZZLE_SOLVER_WEB=1  # Windows
export PUZZLE_SOLVER_WEB=1  # Linux/macOS
uv run python main.py

# 或使用命令行参数
uv run python main.py --web
```

将在 http://localhost:8080 启动 Web 服务。

## 🔧 配置

### API 配置

在应用的「设置」页面中配置 OpenAI 兼容 API：

| 配置项 | 说明 | 示例 |
|--------|------|------|
| API Base URL | API 服务地址 | `https://api.openai.com/v1` |
| API Key | API 密钥 | `sk-...` |
| 模型名称 | 使用的模型 | `gpt-4`、`gpt-4o` |
| 自定义提示词 | 覆盖内置的系统提示词（可选） | - |

支持任何 OpenAI 兼容的 API 服务，包括：
- OpenAI API
- Azure OpenAI
- 本地部署的兼容模型（如 Ollama、vLLM）
- 其他第三方兼容服务

配置保存在项目根目录的 `config.json` 文件中。

## 📁 项目结构

```
puzzle-solver/
├── main.py              # 应用入口
├── pyproject.toml       # 项目配置
├── config.json          # API 配置（运行时生成）
├── data/                # 项目数据存储
├── src/
│   ├── models/
│   │   └── puzzle.py    # 数据模型（Pydantic v2）
│   ├── services/
│   │   ├── config.py    # 配置管理
│   │   ├── deduction.py # 推断服务（AI + 消元）
│   │   ├── llm_service.py  # LLM API 客户端
│   │   └── prompt_engine.py # 提示词构建
│   ├── storage/
│   │   └── json_store.py    # JSON 文件持久化
│   └── ui/
│       ├── state.py     # 应用状态管理
│       ├── theme.py     # 布局和主题
│       └── pages/
│           ├── scripts.py   # 剧本管理页
│           ├── matrix.py    # 推理矩阵页
│           ├── manage.py    # 实体管理页
│           ├── review.py    # 推断审查页
│           └── settings.py  # 设置页
└── tests/               # 测试用例
```

## 🧪 测试

```bash
# 运行所有测试
.venv/Scripts/python -m pytest tests/ -v

# 或使用 uv
uv run pytest tests/ -v
```

## 📖 使用流程

1. **创建项目** — 在首页点击「创建新项目」
2. **设置基础数据**（管理页）：
   - 添加时间段（如 14:00, 15:00, 16:00）
   - 添加人物（游戏角色）
   - 添加地点（故事发生地）
   - 录入游戏规则
3. **录入剧本**（剧本页）— 粘贴各角色的剧本文本
4. **查看矩阵**（矩阵页）— 观察当前推理进度
5. **手动录入事实**（管理页）— 录入已确认的人物位置
6. **运行 AI 推断**（矩阵页）— 让 AI 分析所有线索
7. **审查推断**（审查页）— 逐条接受或拒绝 AI 的推断
8. **重复 5-7**，直到矩阵完全填满

## 📝 技术栈

- **Python 3.13** — 核心语言
- **NiceGUI** — Web/桌面 UI 框架
- **Pydantic v2** — 数据模型和验证
- **OpenAI SDK** — LLM API 调用
- **pytest** — 测试框架

## 📄 许可证

本项目采用 [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) 许可协议。

你可以自由地共享和改编本作品，但须注明出处，且不得用于商业目的。详见 [LICENSE](LICENSE) 文件。
