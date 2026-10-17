# Local LaTeX extraction

The parser recognizes standard theorem environments and aliases declared with
`\newtheorem{alias}{Display}`, `\newtheorem{alias}[counter]{Display}`, and
`\newtheorem{alias}{Display}[section]`, including whitespace and starred
unnumbered declarations. Shared counters can refer through another alias.
Ordinary chapter/section/subsection counters and optional result titles are
retained. Local result IDs remain label based, with the existing per-environment
fallback IDs for unlabelled results. Comments and literal examples are inert.

This is lexical extraction, not execution of TeX. Custom numbering definitions,
counter mutations, unsupported reset counters and cyclic/missing shared counters
leave visible numbers unknown. Mutations include `stepcounter`, `refstepcounter`,
`setcounter`, `addtocounter`, `counterwithin`, `counterwithout`, `numberwithin`
and `usecounter`; these commands are not executed. Uncertainty follows shared
aliases and section-number prefixes. A dynamic/malformed target makes numbering
uncertain across the document. A numeric proof title cannot establish an owner
when a compatible result has an unknown number. Numeric proof-body references
of an uncertain kind remain unknown too; a unique explicit label can still
establish ownership or a local reference. Macro-generated declarations and environments
are outside its coverage. Section-based visible numbers do not imply that the
Paper Map has a section outline: that outline is still unimplemented.

Direct counter-display targets in `renewcommand` (plain/starred, braced/bare,
with whitespace or comment gaps) and the primitive `def`/`gdef`/`edef`/`xdef`
forms are recognized without executing their replacement bodies. An affected
display remains unknown, including aliases that depend on that display and
the applicable chapter/section/subsection/subsubsection prefixes. Unrelated
display targets and literal/comment examples do not taint a result's number.

A complete proof title such as `[Proof of Theorem~\ref{main}]` or
`[Proof of Theorem 2.1]` must identify one unique compatible result. Explicit
goals are considered before unnamed adjacency. Unknown, conflicting, compound
or unsupported titles remain unowned and cannot fall back to a nearby result.
An unnamed proof can use adjacency only when the intervening source is whitespace
or comments. Unrecognized environments, headings, prose, or another proof block
break adjacency. A proof title is not a proof-body dependency reference.
PDF ownership and historical stored evidence are unaffected.

TeX citation commands remain evidence even when a bibliography key is missing.
Plain bracket citations in TeX require an existing bibliography key or an
explicit result locator such as `[12, Theorem 3.5]`, and must
occur outside recognized math delimiters/environments and command options.
Balanced `\ensuremath{...}` bodies are mathematical regions too. Consecutive
optional groups after a control word (including whitespace/comment gaps and
nested groups) are command options; a mandatory argument or prose ends that
sequence. Explicit `\cite` commands remain evidence even inside mathematics
or options. Unsupported custom argument grammars remain outside this lexer.
PDF bracket citation extraction keeps its existing behavior. No citation alone
establishes a mathematical dependency or authorizes downloading a reference.

Inline `thebibliography`/`bibitem` entries retain original source text and offsets,
including entries in an included `.tex` file. Explicit arXiv/DOI/URL identifiers
are read; arbitrary prose is not guessed into title/author/year metadata.
Duplicate keys across sources, malformed keys and entries spanning source files
fail explicitly. Plain rendered numeric/author labels that differ from a bibitem
key are not resolved as aliases; explicit `\cite{key}` is preferred evidence.

Existing workspaces and reading state are not automatically rewritten. Review
an import in a new database before choosing whether to reimport an old paper.
Unresolved formula/section labels remain unknown result references; an empty or
acyclic extracted graph never proves complete mathematical coverage.

For independent acceptance, build a wheel, install it in a fresh environment,
and run its interpreter outside the checkout:

```powershell
& '<ISOLATED_PYTHON>' '<CHECKOUT>\scripts\accept_latex_structure.py' --output '<NEW_OUTPUT_OUTSIDE_GIT>'
```

The default synthetic fixture asserts shared section numbering, delayed proof
ownership, math-bracket rejection and a three-edge dependency chain through
both actual CLI and stdio MCP. It saves commands, diagnostics, schemas, responses,
source-span checks and a summary. A local project can be inspected with
`--tex '<MAIN_TEX>' --paper-id local:example --target '<RESULT_LABEL>'`; this
records observations without applying synthetic expected counts to that project.
The output directory must be new and outside the checkout. The script never
downloads references, changes client configuration or modifies the TeX input.

For semantic counter/context counterexamples through actual CLI and stdio:

```powershell
& '<ISOLATED_PYTHON>' '<CHECKOUT>\scripts\accept_latex_counter_context.py' --output '<ANOTHER_NEW_OUTPUT_OUTSIDE_GIT>'
```

It asserts that unsupported counter mutations cannot create a numeric proof
owner, math/option brackets cannot create external targets, and explicit cites
inside mathematics survive. The general `accept_latex_structure.py --tex`
mode records transport and extraction observations for arbitrary supplied input;
it does not by itself assert the mathematical or semantic expectations of that
input. Use the explicit counter/context suite for those regression expectations.
