# Reference Expansion

Run: `expansion:fixture`

State: completed (within approved policy)

Policy: depth 3; new papers 2/10; searches 0/100; edges 5/500.

This report follows extracted citation evidence within the approved limits. It does not verify proofs or establish complete mathematical dependencies.

## Reference tree

- `arxiv:2401.10001` (done)
  - `expansion-edge:17f9c47e5a77d731722a47e4`: imported; policy_selected; exact\_identifier
    - Evidence: \\cite{c} (source: main.tex)
    - Source status: arxiv\_importable; reason: exact\_identifier
    - `arxiv:2401.10003` (done)
      - `expansion-edge:dc6423f3e317501b6c77aaee`: linked_existing; policy_selected; exact\_identifier
        - Evidence: \\cite{a} (source: main.tex)
        - Source status: arxiv\_importable; reason: exact\_identifier
        - `arxiv:2401.10001` (cycle)
  - `expansion-edge:c8805ea19e6885be73e3528e`: imported; policy_selected; exact\_identifier
    - Evidence: \\cite{b} (source: main.tex)
    - Source status: arxiv\_importable; reason: exact\_identifier
    - `arxiv:2401.10002` (done)
      - `expansion-edge:13674414681912ab6606b76e`: linked_existing; policy_selected; exact\_identifier
        - Evidence: \\cite{c} (source: main.tex)
        - Source status: arxiv\_importable; reason: exact\_identifier
        - `arxiv:2401.10003` (shared target; see earlier entry)
      - `expansion-edge:c2d611171732a566a0bfbc19`: linked_existing; policy_selected; exact\_identifier
        - Evidence: \\cite{a} (source: main.tex)
        - Source status: arxiv\_importable; reason: exact\_identifier
        - `arxiv:2401.10001` (cycle)

## Next actions


## Attempts

- `expansion-edge:17f9c47e5a77d731722a47e4`: import / completed;
- `expansion-edge:c8805ea19e6885be73e3528e`: import / completed;
- `expansion-edge:13674414681912ab6606b76e`: import / completed;
- `expansion-edge:c2d611171732a566a0bfbc19`: import / completed;
- `expansion-edge:dc6423f3e317501b6c77aaee`: import / completed;
