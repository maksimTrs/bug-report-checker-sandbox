# bug-report-checker sandbox

A test repository for [bug-report-checker](https://github.com/maksimTrs/bug-report-checker): open a bug here and the bot comments with what the report is missing. All issues are made up.

- Workflow: `.github/workflows/bug-checker.yml`
- Settings: `.github/bug-checker.yml`
- Bug form: `.github/ISSUE_TEMPLATE/bug.yml`

Statuses are labels: `Submitted`, `Open`, `In Progress`. An open bug without one counts as `Submitted`.

## End-to-end tests

`tests/` files real bugs here, waits for the bot's comment and closes each bug afterwards; the issues carry the `e2e` label. Each scenario in `tests/test_scenarios.py` is a made-up report with the findings the bot must give under `strict: true`: complete, or exactly which blockers are missing, plus the suggestions and the environment it must name. In CI the run's Job Summary lists every scenario with its issue, the expected and the actual findings. Run them with `uv run pytest` after `gh auth login`, or with a token in `E2E_TOKEN`; `uv run pytest -m "not e2e"` runs only the offline tests of the client.

CI (`.github/workflows/e2e.yml`) runs on demand, weekly and on changes to the tests or the bot's setup. The `E2E_TOKEN` secret is a fine-grained PAT for this repository with Issues read and write: issues opened with the workflow's own `GITHUB_TOKEN` start no workflows, so the bot would never see them.

Data: The Public Jira Dataset — Montgomery L., Lüders C., Maalej W. *An Alternative Issue Tracking Dataset of Public Jira Repositories.* MSR 2022. DOI: [10.1145/3524842.3528486](https://doi.org/10.1145/3524842.3528486). Dataset: https://doi.org/10.5281/zenodo.5882881. License: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
