# Contributing to PaperGraph

Thanks for helping PaperGraph understand more mathematical LaTeX projects.

## Development setup

Install [uv](https://docs.astral.sh/uv/), clone the repository, and run:

```powershell
uv sync
uv run pytest -q -p no:cacheprovider
```

To focus on arXiv importing and safe extraction, run:

```powershell
uv run pytest tests/test_arxiv.py -q -p no:cacheprovider
```

## Making a change

Create a focused branch and keep commits small enough to review. Add a focused
regression test for every behavior change or bug fix, then run the complete
suite before opening a pull request.

Automated tests must be deterministic. Do not contact the live arXiv service
from pytest; live arXiv checks belong only in isolated manual acceptance.

## Pull requests

Explain the problem, the chosen behavior, compatibility impact, tests run, and
documentation changes. Keep unrelated refactors out of the same pull request.

Never commit private manuscripts, cache data, credentials, generated
distributions, access tokens, or secrets. Use small synthetic LaTeX fixtures
when a reproduction needs paper content.
