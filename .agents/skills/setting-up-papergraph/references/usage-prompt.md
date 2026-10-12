# Reusable PaperGraph prompt

Present this prompt before asking for installation permission:

```text
请使用 PaperGraph MCP 分析我提供的论文，并建立一个多论文工作区。

工作区数据库保存在 Git 仓库外的合适数据目录，不要放进 Git 仓库。依次导入我提供的论文，然后：

开始分析前，请先调用 `get_environment_diagnostics` 或运行 `papergraph-mcp doctor`，并在回答里说明 PaperGraph 版本。

若使用未发布的本地修复，请同时记录实际启动解释器、`doctor.build_identity` 的基准提交、修改状态和源码摘要；版本仍为 1.2.0 不代表已包含修复，也不要把本地行为归于 PyPI 发布包。保持现有 MCP 客户端配置不变，安装、配置和重启分别需要批准。

本地 LaTeX 输入应是主 `.tex` 文件，不是目录；MCP starter 输入使用 `kind: local_tex`。先核对运行中工具与 schema，再规划工作区。修复后的 plan 只读预检、不创建目录或数据库，`ready` 不代表正文已解析或导入；bootstrap 会写入并实际导入。旧构建的副作用应按实测说明。执行后续命令前替换占位符，使用当前 shell 的引用方式和 `命令 --workspace ... --paper-id/--result-id ...` 语法。checkpoint 使用 `target_kind: result_id`。结果列表按运行中 schema 分页；修复版 `limit` 为 1..100，`offset` 非负，不把单页当作完整列表。

如果我提供的是已发表论文的 DOI，请先区分论文身份元数据和可导入正文；不要把 DOI 直接当作 arXiv ID。确认合法可访问的正文来源，或引导我提供本地 PDF。不要绕过付费墙；新发现的外部引用先生成可审阅的导入计划，不自动下载。

若我要求证明依赖，请使用证明局部依赖与阅读路径工具，并区分陈述引用图、证明中可定位的显式证据和未知关系。旧的 `dependency_extraction_basis` 字段只描述陈述引用图，不代表全部证明分析能力。空依赖不代表数学上没有依赖，回答仅依据 PaperGraph 返回的证据。

请核对 result_id、proof_id 和可读取原文件的 spans。跨文件 TeX 正文应保留各文件片段；BibTeX 原文应指向真实条目，不能取注释或字段中的伪条目。普通 citation 只是引用证据，不自动成为数学依赖或下载许可。检查 `order_status`；环阻止局部先后排序，queue 是 exploration 路线。PDF 先核对 `text_coverage`、截断续读定位和 proof 入口，未知或歧义关联保持未知。

如果我给出原始请求、Markdown 链接、arXiv ID and arXiv URL 或混合文本，请优先调用 `load_arxiv_request`，或先调用 `validate_arxiv_request` / `papergraph-mcp validate-arxiv-request` 查看判定。只有当验证结果是 `action: safe_to_load` 时才加载；如果结果是 `action: ask_user_to_choose`，请先问我要分析哪一篇，不要继续加载。只有在我已经给出单一、无歧义的 arXiv ID 后，才直接调用 `load_arxiv_paper`。

1. 列出成功导入的论文；
2. 搜索与“fixed point”相关的定理；
3. 比较这些定理分别来自哪篇论文；
4. 查询论文之间明确存在的引用证据；
5. 区分已解析引用、尚未导入的 arXiv 目标和缺失的 BibTeX 条目；
6. 不要把文本相似性描述成已经证明的数学关系。
```

When translating the prompt, preserve all six numbered requirements, the requirement to keep the workspace database outside Git, and the warning that textual similarity is not a proved mathematical relationship.
