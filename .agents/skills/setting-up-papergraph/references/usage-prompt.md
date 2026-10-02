# Reusable PaperGraph prompt

Present this prompt before asking for installation permission:

```text
请使用 PaperGraph MCP 分析我提供的论文，并建立一个多论文工作区。

工作区数据库保存在 Git 仓库外的合适数据目录，不要放进 Git 仓库。依次导入我提供的论文，然后：

开始分析前，请先调用 `get_environment_diagnostics` 或运行 `papergraph-mcp doctor`，并在回答里说明 PaperGraph 版本。

如果我提供的是已发表论文的 DOI，请先区分论文身份元数据和可导入正文；不要把 DOI 直接当作 arXiv ID。确认合法可访问的正文来源，或引导我提供本地 PDF。不要绕过付费墙；新发现的外部引用先生成可审阅的导入计划，不自动下载。

若我要求证明依赖，请使用证明局部依赖与阅读路径工具，并区分陈述引用图、证明中可定位的显式证据和未知关系。旧的 `dependency_extraction_basis` 字段只描述陈述引用图，不代表全部证明分析能力。空依赖不代表数学上没有依赖，回答仅依据 PaperGraph 返回的证据。

如果我给出原始请求、Markdown 链接、arXiv ID and arXiv URL 或混合文本，请优先调用 `load_arxiv_request`，或先调用 `validate_arxiv_request` / `papergraph-mcp validate-arxiv-request` 查看判定。只有当验证结果是 `action: safe_to_load` 时才加载；如果结果是 `action: ask_user_to_choose`，请先问我要分析哪一篇，不要继续加载。只有在我已经给出单一、无歧义的 arXiv ID 后，才直接调用 `load_arxiv_paper`。

1. 列出成功导入的论文；
2. 搜索与“fixed point”相关的定理；
3. 比较这些定理分别来自哪篇论文；
4. 查询论文之间明确存在的引用证据；
5. 区分已解析引用、尚未导入的 arXiv 目标和缺失的 BibTeX 条目；
6. 不要把文本相似性描述成已经证明的数学关系。
```

When translating the prompt, preserve all six numbered requirements, the requirement to keep the workspace database outside Git, and the warning that textual similarity is not a proved mathematical relationship.
