# Docs

One folder per project. Each holds what someone joining that project needs:
what it is, how its models are trained and served, and what has gone wrong before.

| Project | What | Pages |
|---|---|---|
| [pbbi/](pbbi/README.md) | Perjanjian Baku Bank Indonesia — clause extraction and analysis of payment providers' standard-form agreements | [overview](pbbi/README.md) · [training](pbbi/training.md) · [serving](pbbi/serving.md) · [evaluation](pbbi/evaluation.md) · [troubleshooting](pbbi/troubleshooting.md) |

`reports/` is not a project: dated write-ups (deployment trials, incidents,
benchmarks), named `YYYY-MM-DD-<topic>.md`, kept as history.

**Adding a project:** create `docs/<project>/README.md` (what it is, its tasks, where
its pieces live in the repo), add pages as the project grows, and add a row above.
Name the folder like the project's charts and configs (`runpod/<project>-*`,
`training/configs/<project>-*`), so everything for one project is findable by prefix.
