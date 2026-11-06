# AGENTS.md

Guidance for AI coding agents working on this repository. Human contributors:
see [CONTRIBUTING](CONTRIBUTING.md).

## Project

`innergrid`: an asynchronous Python client for the energy and building data
that the Innergrid energy management platform (IP-Symcon based) publishes for a
customer site over MQTT, and for its REST API, published on PyPI. Its main consumer is the
[Home Assistant integration](https://github.com/robbinjanssen/home-assistant-innergrid)
(same owner), which pins a released version; keep that integration in mind when
changing the public API.

```text
innergrid/
  innergrid.py      Innergrid MQTT client (listen, wait_for_data), topic
                    parsing (topic_kind, parse_message), Update and Removal
  api.py            InnergridApi REST client: login, spaces, charge point
                    sessions
  models.py         dataclasses per kind of topic, parsed with from_dict
  exceptions.py     public exceptions
  const.py          Kind, default port, plausible value ranges
tests/              pytest tests with JSON fixtures of real messages
```

## Commands

The project uses [uv](https://docs.astral.sh/uv/) and
[prek](https://github.com/j178/prek).

```sh
uv sync                        # create .venv with the dev tools
uv run prek install            # git hook running all checks on commit
uv run prek run --all-files    # Ruff, mypy, pylint, pytest, codespell, ...
uv run pytest                  # tests with coverage
uv build --no-sources          # build the wheel and sdist (uv_build)
```

Run all hooks and tests before committing. The hooks refuse commits to `main`;
work on a branch.

## Requirements

- Python 3.11 to 3.14; CI tests every version. Write code that runs on 3.11:
  no PEP 695 generics or `type` statements, and parenthesise multiple
  exceptions in `except`. mypy and Ruff target 3.11.
- The runtime dependencies are `aiomqtt` (MQTT) and `aiohttp` (REST API).

## Conventions

- **Public API**: everything users need is exported from
  `innergrid/__init__.py` and listed in `__all__`.
- **Topics**: the prefix is the slug of the customer site. The platform's
  topics are retained; an empty message means the instance is gone, which
  `parse_message` returns as a `Removal`.
- **REST API**: `InnergridApi` sends every request through `request()`, which
  logs in again once when the API answers HTTP 401. Tests mock it with
  `aresponses`. Only `set_charge_point_session` changes anything.
- **Connection**: `listen()` connects once and raises
  `InnergridConnectionError` (or `InnergridAuthError`) when the
  connection fails or is lost; reconnecting is up to the caller.
- **Models** never raise on unexpected payloads: missing or invalid fields are
  `None`, and the ID falls back to the one in the topic. Climate values outside
  the ranges in `const.py` are `None`.
- **Units**: power in W, energy in kWh, money in euro, memory and disk in MiB,
  Milesight battery voltage in mV, load factors as fractions.
- **Typing**: mypy runs in strict mode from `pyproject.toml`.

## Tests

- Fixtures in `tests/fixtures/` are real messages. The names of the people
  charging are replaced (Alice, Bob); never commit real names. The Home
  Assistant integration copies these fixtures.
- CI requires at least 90% coverage. Add a test for every bug fix that fails
  without the fix.

## Pull requests and releases

- Every pull request needs one of these labels: `breaking-change`, `bugfix`,
  `hotfix`, `documentation`, `enhancement`, `refactor`, `performance`,
  `new-feature`, `maintenance`, `ci`, `dependencies`, `skip-changelog`.
- Release Drafter derives the next version from the labels. Publishing a GitHub
  release runs `release.yaml`, which sets the version from the tag
  (`uv version`), builds the package and publishes it to PyPI. The version in
  `pyproject.toml` stays `0.0.0`.
- Renovate keeps dependencies up to date and automerges minor and patch
  updates.
