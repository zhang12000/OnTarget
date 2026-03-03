# 贡献指南

感谢您考虑为 OnTarget 做出贡献！

## 🤝 如何贡献

### 报告问题

如果您发现了 bug 或有功能建议：

1. 在 [GitHub Issues](https://github.com/operoncao123/OnTarget/issues) 中搜索，确保问题尚未被报告
2. 创建新的 Issue，包含：
   - 清晰的标题和描述
   - 复现步骤（如果是 bug）
   - 预期行为和实际行为
   - 截图（如果适用）
   - 环境信息（Python 版本、操作系统等）

### 提交代码

1. **Fork 本仓库**

2. **克隆您的 Fork**
   ```bash
   git clone https://github.com/your-username/OnTarget.git
   cd OnTarget
   ```

3. **创建特性分支**
   ```bash
   git checkout -b feature/amazing-feature
   ```

4. **进行修改**
   - 遵循现有的代码风格
   - 添加必要的注释
   - 更新相关文档

5. **测试您的修改**
   ```bash
   pytest tests/
   ```

6. **提交更改**
   ```bash
   git add .
   git commit -m "Add: 某个很棒的功能"
   ```

7. **推送到 GitHub**
   ```bash
   git push origin feature/amazing-feature
   ```

8. **创建 Pull Request**
   - 清楚描述您的修改
   - 关联相关的 Issue
   - 等待代码审查

## 📝 代码规范

### Python 代码

- 遵循 PEP 8 规范
- 使用有意义的变量名和函数名
- 添加必要的文档字符串
- 保持函数简洁，单一职责

### 提交信息

使用清晰的提交信息：

- `Add: 新功能`
- `Fix: 修复bug`
- `Update: 更新功能`
- `Refactor: 重构代码`
- `Docs: 文档更新`
- `Test: 测试相关`

## 🧪 测试

运行测试：

```bash
# 运行所有测试
pytest tests/

# 运行特定测试
pytest tests/test_impact_factor.py

# 带覆盖率报告
pytest tests/ --cov=.
```

## 📚 文档

- 更新 README.md（如果添加新功能）
- 添加代码注释
- 更新 CHANGELOG.md

## ❓ 问题？

如有任何问题，欢迎：

- 在 [GitHub Discussions](https://github.com/operoncao123/OnTarget/discussions) 讨论
- 提交 [Issue](https://github.com/operoncao123/OnTarget/issues)
- 发送邮件至：support@ontarget.chat

## 📄 许可证

通过贡献代码，您同意您的代码将按照 AGPL 3.0 许可证发布。

---

再次感谢您的贡献！🙏
