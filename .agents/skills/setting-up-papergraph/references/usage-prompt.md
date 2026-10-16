# Reusable PaperGraph prompt

Present this prompt before asking for installation permission:

```text
请使用 PaperGraph MCP 分析我提供的论文，并建立一个多论文工作区。

工作区数据库保存在 Git 仓库外的合适数据目录，不要放进 Git 仓库。依次导入我提供的论文，然后：

开始分析前，请先调用 `get_environment_diagnostics` 或运行 `papergraph-mcp doctor`，并在回答里说明 PaperGraph 版本。

若使用未发布的本地修复，请同时记录实际启动解释器、`doctor.build_identity` 的基准提交、修改状态和源码摘要；版本显示 1.2.2 也不代表已发布；请核对官方索引验收，不把本地行为归于未经验证的 PyPI 包。保持现有 MCP 客户端配置不变，安装、配置和重启分别需要批准。

当前检出准备 1.2.2，尚未发布或独立验收，`publication_verified=false`；普通 PyPI 及版本标签安装命令须等待各自发布证据，不用历史 1.2.1 验收替代。源码审阅和本地制品通过也不代表官方入口已发布。

Git 固定提交能安装不等于版本标签已发布。checker 的 `--install-source git` 默认只做本地前置条件检查，不应显示 publication verified；需要明确联网验证时，再用 `--verify-git-release --expected-source-commit SHA`，其中 SHA 必须来自审阅过的打包源码记录。只有实时标签目标与该 SHA 相符才允许继续标签 launch；标签缺失、网络不可用或不匹配都保持未验证。

本地 LaTeX 输入应是主 `.tex` 文件，不是目录；MCP starter 输入使用 `kind: local_tex`。先核对运行中工具与 schema，再规划工作区。1.2.2 的 plan 只读预检、不创建目录或数据库，`ready` 不代表正文已解析或导入；bootstrap 会写入并实际导入。旧构建的副作用应按实测说明。执行后续命令前替换占位符，使用当前 shell 的引用方式，并查看该命令的 `--help`：map、source slice、starter 等使用 `--workspace` 和 ID flags；`get-dependency-reading WORKSPACE PAPER_ID`、`discover-doi DOI`、`add-doi-paper WORKSPACE DOI`、`import-doi-candidate WORKSPACE DOI CANDIDATE_ID --confirm` 使用位置参数，不套用前述 flags。checkpoint 使用 `target_kind: result_id`。结果列表按运行中 schema 分页；当前 `limit` 为 1..100，`offset` 非负，不把单页当作完整列表。

如果我提供的是已发表论文的 DOI，请先区分论文身份元数据和可导入正文；不要把 DOI 直接当作 arXiv ID。确认合法可访问的正文来源，或引导我提供本地 PDF。不要绕过付费墙；新发现的外部引用先生成可审阅的导入计划，不自动下载。

若我要求证明依赖，请使用证明局部依赖与阅读路径工具，并区分陈述引用图、证明中可定位的显式证据和未知关系。旧的 `dependency_extraction_basis` 字段只描述陈述引用图，不代表全部证明分析能力。空依赖不代表数学上没有依赖，回答仅依据 PaperGraph 返回的证据。

请核对 result_id、proof_id 和可读取原文件的 spans。跨文件 TeX 正文应保留各文件片段；BibTeX 原文应指向真实条目，不能取注释或字段中的伪条目。普通 citation 只是引用证据，不自动成为数学依赖或下载许可。检查 `order_status`；环阻止局部先后排序，queue 是 exploration 路线。PDF 先核对 `text_coverage`、截断续读定位和 proof 入口，未知或歧义关联保持未知。

PDF 长文从 `source_reading` 调用 `workspace_read_source_blocks`，按 `next` 续读，每页 1..50 块；source slice 的 `context` 为 0..5。raw blocks 不自动成为 proof evidence。新 PDF 导入的自动证据只取明确 Proof 开头所在的首个原始文本行，并在该行首个终止位置裁剪；歧义 QED 提及只停止片段、不借用后续 QED。后续行或块不自动关联，长证明晚段引用保持未知。泛 Proof heading 只在 result 原始 span 直接相邻时关联 owner；中间未归属正文使 owner 保持未知。完整 heading 必须仅含一个明确且唯一的目标才可关联；and/or、slash、括号备选及省略重复 kind 等多目标或不支持语法保持 owner 未知，不按邻近回退。heading 中的目标不作为正文依赖引用。书目派生 entry 保留原 evidence ID，raw 分页只返回原始块一次。按 automatic_ownership_policy 区分新策略和未重导入的历史片段；精确 offsets 相对原始块，bbox 只标容器。旧数据不自动改写，重导入必须明确选择。单目标依赖查询可显式选择 `detail: compact`，再按返回 handle 获取完整证据。展示外部阻塞时使用 `blocked_groups` 和 unique target 计数，保留原始 blocker IDs；未解析内部引用与外部文献计划分开，不能要求为内部引用补 arXiv ID。

如果我给出原始请求、Markdown 链接、arXiv ID and arXiv URL 或混合文本，请优先调用 `load_arxiv_request`，或先调用 `validate_arxiv_request` / `papergraph-mcp validate-arxiv-request` 查看判定。只有当验证结果是 `action: safe_to_load` 时才加载；如果结果是 `action: ask_user_to_choose`，请先问我要分析哪一篇，不要继续加载。只有在我已经给出单一、无歧义的 arXiv ID 后，才直接调用 `load_arxiv_paper`。

1. 列出成功导入的论文；
2. 搜索与“fixed point”相关的定理；
3. 比较这些定理分别来自哪篇论文；
4. 查询论文之间明确存在的引用证据；
5. 区分已解析引用、尚未导入的 arXiv 目标和缺失的 BibTeX 条目；
6. 不要把文本相似性描述成已经证明的数学关系。
```

When translating the prompt, preserve all six numbered requirements, the requirement to keep the workspace database outside Git, and the warning that textual similarity is not a proved mathematical relationship.
