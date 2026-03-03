# OnTarget - 智能文献推送系统

<div align="center">

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![GitHub stars](https://img.shields.io/github/stars/operoncao123/OnTarget.svg?style=social)](https://github.com/operoncao123/OnTarget)

**智能个性化文献推送平台 - 让学术文献主动找到你**

[在线体验](https://ontarget.chat) · [功能特性](#功能特性) · [快速开始](#快速开始) · [配置说明](#配置说明)

</div>

---

## 🌟 在线服务

不想自己部署？欢迎使用在线服务：

👉 **[ontarget.chat](https://ontarget.chat)**

- ✅ 无需配置，开箱即用
- ✅ 自动更新，实时推送
- ✅ 云端存储，多设备同步
- ✅ 技术支持

---

## 📖 简介

OnTarget 是一个智能的个性化文献推送系统，帮助你自动跟踪和筛选最新的学术文献。

**🎯 开源版特点：**
- ✅ **无需登录** - 打开即用，无需注册账户
- ✅ **本地部署** - 数据存储在本地，保护隐私
- ✅ **功能完整** - 保留核心的文献推送和 AI 分析功能

**核心功能：**
- 🔍 **多源文献获取** - 支持 PubMed、bioRxiv、medRxiv、arXiv 等多个学术数据库
- 🎯 **智能关键词匹配** - 基于你的研究方向，精准筛选相关文献
- 📊 **个性化评分** - 根据关键词匹配度自动评分，优先展示最相关的文献
- 💡 **AI 智能分析** - 使用大语言模型分析文献，提取主要发现、创新点和局限性
- 🔖 **智能收藏** - 按主题分组管理，快速收藏和检索
- 📈 **影响因子显示** - 自动匹配期刊影响因子
- 🔄 **自动更新** - 定时自动获取最新文献

---

## ✨ 功能特性

### 📚 文献获取

| 来源 | 类型 | 更新频率 |
|------|------|---------|
| PubMed | 期刊论文 | 按需 |
| bioRxiv | 生物学预印本 | 按需 |
| medRxiv | 医学预印本 | 按需 |
| arXiv | 多学科预印本 | 按需 |

### 🎯 智能筛选

- **关键词组管理** - 创建多个关键词组，针对不同研究方向
- **多模式匹配** - 支持精确匹配和模糊匹配
- **自动评分** - 根据标题、摘要中的关键词匹配度评分
- **影响因子** - 显示期刊影响因子，帮助判断文献质量

### 💡 AI 分析（需配置 API Key）

- **主要发现** - 提取文献的核心贡献
- **创新点** - 识别研究的创新之处
- **局限性** - 分析研究的不足之处
- **未来方向** - 展望后续研究方向
- **中文翻译** - 自动翻译摘要为中文

---

## 🚀 快速开始

### 环境要求

- Python 3.9 或更高版本
- SQLite 3
- 现代浏览器（Chrome、Firefox、Safari、Edge）

### 安装步骤

#### 1. 克隆项目

```bash
git clone https://github.com/operoncao123/OnTarget.git
cd OnTarget
```

#### 2. 创建虚拟环境

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows
```

#### 3. 安装依赖

```bash
pip install -r requirements.txt
```

#### 4. 配置环境变量

```bash
# 复制配置模板
cp .env.example .env

# 编辑配置文件
nano .env  # 或使用你喜欢的编辑器
```

**必须配置的项：**
- `API_KEY` - 你的 AI API Key（用于文献分析）
- `SECRET_KEY` - 随机生成的密钥（用于 session 加密）
- `PUBMED_EMAIL` - 你的邮箱（PubMed API 要求）

#### 5. 启动服务

**前台运行（推荐用于调试）：**
```bash
chmod +x run.sh
./run.sh
```

**后台运行（推荐用于生产环境）：**
```bash
chmod +x start_daemon.sh stop.sh status.sh
./start_daemon.sh   # 启动后台服务
./status.sh         # 查看状态
./stop.sh           # 停止服务
```

#### 6. 访问系统

打开浏览器访问：http://localhost:5500

---

## ⚙️ 配置说明

### AI API 配置

OnTarget 支持多种 AI 服务商：

#### DeepSeek（推荐）

```env
API_PROVIDER=deepseek
API_KEY=sk-your-deepseek-key
API_BASE_URL=https://api.deepseek.com
MODEL=deepseek-chat
```

获取 API Key: https://platform.deepseek.com

#### OpenAI

```env
API_PROVIDER=openai
API_KEY=sk-your-openai-key
API_BASE_URL=https://api.openai.com/v1
MODEL=gpt-4
```

获取 API Key: https://platform.openai.com

#### Anthropic Claude

```env
API_PROVIDER=anthropic
API_KEY=sk-ant-your-anthropic-key
API_BASE_URL=https://api.anthropic.com
MODEL=claude-3-opus-20240229
```

获取 API Key: https://www.anthropic.com

### 关键词配置示例

在系统界面中创建关键词组，例如：

```
蛋白质降解研究：
- PROTAC
- molecular glue
- targeted protein degradation
- ubiquitin
- E3 ligase

肿瘤免疫：
- immunotherapy
- checkpoint inhibitor
- CAR-T
- tumor microenvironment
```

---

## 📖 使用指南

### 基本流程

1. **创建关键词组** - 在"关键词管理"页面创建你的研究方向
2. **更新文献** - 点击"更新文献"按钮获取最新文献
3. **浏览筛选** - 在主页浏览文献，使用筛选功能过滤
4. **AI 分析** - 点击"AI分析"按钮深入分析感兴趣的文献
5. **收藏管理** - 收藏重要文献，按关键词组分类

### 高级功能

- **多关键词组** - 为不同研究方向创建独立的组
- **评分筛选** - 根据匹配分数筛选最相关的文献
- **来源筛选** - 只看特定来源的文献
- **自动更新** - 配置定时任务自动更新

---

## 🔧 高级配置

### 定时自动更新

使用 cron 设置定时任务：

```bash
# 编辑 crontab
crontab -e

# 每天早上8点更新
0 8 * * * cd /path/to/OnTarget && /path/to/venv/bin/python -c "from core.system import LiteraturePushSystemV2; LiteraturePushSystemV2().run_for_user('default_user')"
```

### 反向代理配置

使用 Nginx：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

### 性能优化

1. **增加 Workers**

编辑 `run.sh`：

```bash
WORKERS=8  # 根据 CPU 核心数调整
```

2. **调整缓存大小**

编辑 `core/memory_cache.py` 中的缓存配置。

---

## 🤝 贡献指南

欢迎贡献代码、报告问题或提出建议！

### 贡献方式

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

### 报告问题

- 使用 [GitHub Issues](https://github.com/operoncao123/OnTarget/issues)
- 描述清楚问题的复现步骤
- 附上错误日志和截图

---

## 📄 许可证

本项目采用 GNU Affero General Public License v3.0 (AGPL 3.0) 许可证。

- ✅ 你可以自由使用、修改和分发本软件
- ✅ 如果修改了本软件并提供网络服务，必须公开修改后的源代码
- ✅ 必须保留原始版权声明

详见 [LICENSE](LICENSE) 文件。

---

## 🙏 致谢

感谢以下开源项目和服务：

- [Flask](https://flask.palletsprojects.com/) - Web 框架
- [SQLAlchemy](https://www.sqlalchemy.org/) - ORM
- [Entrez](https://www.ncbi.nlm.nih.gov/books/NBK25501/) - PubMed API
- [bioRxiv API](https://api.biorxiv.org/) - 预印本服务

---

## 📧 联系方式

- **在线服务**: [ontarget.chat](https://ontarget.chat)
- **问题反馈**: [GitHub Issues](https://github.com/operoncao123/OnTarget/issues)
- **功能建议**: [GitHub Discussions](https://github.com/operoncao123/OnTarget/discussions)

---

<div align="center">

**如果这个项目对你有帮助，请给一个 ⭐️ Star！**

Made with ❤️ by the OnTarget Team

</div>
