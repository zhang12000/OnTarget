# OnTarget 开源版使用说明

## 🎉 欢迎使用 OnTarget 开源版

这是 OnTarget 的开源版本，采用 AGPL 3.0 许可证发布。

### 📦 包含的功能

✅ **完整功能**
- 多源文献获取（PubMed, bioRxiv, medRxiv, arXiv等）
- 关键词组管理
- 智能评分和筛选
- AI智能分析（需配置您自己的API Key）
- 文献收藏和管理
- 影响因子显示
- 自动更新服务
- 美观的Web界面

❌ **已移除功能（仅在线版提供）**
- 用户注册系统
- 用户登录系统
- 管理员后台
- 托管式服务

### 🌟 在线服务

不想自己部署？欢迎使用我们的在线服务：

👉 **[ontarget.chat](https://ontarget.chat)**

- 无需配置，开箱即用
- 自动更新，实时推送
- 云端存储，多设备同步
- 专业技术支持

## 🚀 快速开始

### 1. 配置环境

```bash
# 复制配置模板
cp .env.example .env

# 编辑配置文件
nano .env
```

**必须配置：**
```
API_KEY=your-api-key-here  # 您的AI API Key
SECRET_KEY=your-random-key  # 随机生成的密钥
PUBMED_EMAIL=your@email.com  # 您的邮箱
```

### 2. 启动服务

```bash
chmod +x run.sh
./run.sh
```

### 3. 访问系统

浏览器访问：http://localhost:5000

## 📖 详细文档

- **安装部署**: [DEPLOYMENT.md](DEPLOYMENT.md)
- **贡献代码**: [CONTRIBUTING.md](CONTRIBUTING.md)
- **发布检查**: [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)
- **许可证**: [LICENSE](LICENSE)

## ⚙️ AI API 配置

支持多种AI服务商：

### DeepSeek（推荐）
```
API_PROVIDER=deepseek
API_KEY=sk-your-deepseek-key
API_BASE_URL=https://api.deepseek.com
MODEL=deepseek-chat
```

### OpenAI
```
API_PROVIDER=openai
API_KEY=sk-your-openai-key
API_BASE_URL=https://api.openai.com/v1
MODEL=gpt-4
```

### Anthropic Claude
```
API_PROVIDER=anthropic
API_KEY=sk-ant-your-anthropic-key
API_BASE_URL=https://api.anthropic.com
MODEL=claude-3-opus-20240229
```

## 💡 使用提示

1. **首次使用**：启动后直接访问主页，无需注册登录
2. **创建关键词组**：在"关键词管理"页面创建您的研究方向
3. **配置API Key**：必须配置AI API Key才能使用分析功能
4. **更新文献**：点击"更新文献"按钮获取最新文献

## 📞 获取帮助

- **在线服务**: [ontarget.chat](https://ontarget.chat)
- **问题反馈**: [GitHub Issues](https://github.com/yourusername/OnTarget-open/issues)
- **功能建议**: [GitHub Discussions](https://github.com/yourusername/OnTarget-open/discussions)

## 🙏 致谢

感谢使用 OnTarget 开源版！

如果这个项目对您有帮助，请给一个 ⭐️ Star！

---

Made with ❤️ by the OnTarget Team
