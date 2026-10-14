<img src="server/static/icon.svg" alt="SuuLess logo — a cigarette with leaf-shaped smoke" width="96" height="96">

# SuuLess · スーレス

[![GitHub CI — tests, security and builds](https://github.com/urcus/suuless/actions/workflows/ci.yml/badge.svg?branch=main&event=push)](https://github.com/urcus/suuless/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![API: OpenAPI](https://img.shields.io/badge/API-OpenAPI-blue.svg)](docs/api/README.md)

SuuLess is a self-hosted cigarette consumption tracker. Its web interface, native Android app and Stream Deck API share the same history, with separate user accounts. The interface supports English, French and Japanese. Data stays in a SQLite database on your server.

## Features

- Quick +1, grouped or backdated entries, and deletion of mistakes.
- Quantities, historical costs, charts, averages and period comparisons.
- Per-account pack price, currency, language and time zone.
- Separate administration, email invitations, account activation and password recovery via SMTP.
- Android home-screen widget and authenticated background synchronization.
- Revocable personal API keys, Stream Deck integration and CSV exports.
- Observation, reduction or quit plans, craving pauses, daily confirmations and optional reminders.

Statistics describe recorded entries: a day without an entry is not necessarily a smoke-free day. Historical costs retain their original currency without automatic conversion.

## Quick start

Install Docker with Compose, then run from the repository root:

```sh
cp .env.example .env
docker compose up -d --build
```

Open <http://localhost:8080>, create an account and set your language, pack price and time zone. No predefined credentials are shipped. For a fresh installation with `ALLOW_REGISTRATION=false`, set `ADMIN_USERNAME` and `ADMIN_PASSWORD` in `.env` before starting; see [initial account configuration](docs/deployment/docker.md#start-with-docker).

The port is bound to localhost by default. Use an HTTPS reverse proxy for remote access. Data persists in the Docker volume; **`docker compose down -v` deletes it**.

See the [installation guide](docs/deployment/docker.md) for network access, registration settings, backups and restoration.

![SuuLess web dashboard with synthetic demonstration data](docs/assets/screenshots/web-today.png)

Configure administrator access and mail delivery using the [administration guide](docs/deployment/administration.md).

## Android and Stream Deck

The native app requires Android 8.0 or later. The [Android guide](docs/user-guide/android.md) covers building, installing, connecting and using the widget. CI produces an installable debug APK and an unsigned release APK; the latter requires signing before installation. No Play Store publication is configured.

See the [dashboard](docs/assets/screenshots/android-today.png) and [analysis](docs/assets/screenshots/android-analysis.png) screenshots, captured with the French interface on a demo account. Stream Deck uses an HTTP action described in the [API guide](docs/api/README.md#stream-deck).

## Documentation

| Topic | Guide |
|---|---|
| Installation and backups | [Docker Compose](docs/deployment/docker.md) · [Kubernetes](docs/deployment/kubernetes.md) |
| Statistics and preferences | [Usage](docs/user-guide/usage.md) |
| Goals, cravings and reminders | [Coaching](docs/user-guide/coaching.md) |
| API and automation | [API guide](docs/api/README.md) · [OpenAPI specification](docs/api/openapi.yaml) |
| Code and tests | [Development](docs/development/README.md) |
| Components and storage | [Architecture](docs/development/architecture.md) |

The [documentation index](docs/README.md) links all guides and diagrams.

## Repositories and contributions

GitLab is the primary development repository. The [public GitHub repository](https://github.com/urcus/suuless) is intended as its mirror. Changes proposed on GitHub must be integrated in GitLab before synchronization.

Both platforms have independent CI: GitLab publishes to Harbor and GitHub to GHCR. Secrets and platform settings are configured separately.

## License

Distributed under the [MIT License](LICENSE).


