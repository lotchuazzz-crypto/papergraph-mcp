# Reusable PaperGraph prompt

Present this prompt before asking for installation permission:

```text
请使用 PaperGraph MCP 分析这些 LaTeX 论文，并建立一个多论文工作区。

工作区数据库保存在临时目录，不要放进 Git 仓库。依次导入我提供的论文，然后：

1. 列出成功导入的论文；
2. 搜索与“fixed point”相关的定理；
3. 比较这些定理分别来自哪篇论文；
4. 查询论文之间明确存在的引用证据；
5. 区分已解析引用、尚未导入的 arXiv 目标和缺失的 BibTeX 条目；
6. 不要把文本相似性描述成已经证明的数学关系。
```

When translating the prompt, preserve all six numbered requirements, the requirement to keep the workspace database in a temporary directory outside Git, and the warning that textual similarity is not a proved mathematical relationship.
