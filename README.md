# Send money to someone in prison – Prisoner Money

Public-facing site for [Prisoner Money suite of apps](https://github.com/ministryofjustice/money-to-prisoners).

How this app fits into the wider service — architecture, data flows, deployment and
support — is documented in [money-to-prisoners-deploy](https://github.com/ministryofjustice/money-to-prisoners-deploy/blob/main/docs/README.md).

Overview of the application [here](./guidelines.md)
## Requirements

- Unix-like platform with Python 3.12 and NodeJS 24 (e.g. via [nvm](https://github.com/nvm-sh/nvm#installing-and-updating) or [fnm](https://github.com/Schniz/fnm#installation))

## Running locally with Docker

This is the quickest way to get started: you only need this repository and
[Docker](https://www.docker.com/products/docker-desktop/). Run

```shell
docker compose up
```

This starts the site from your checkout, together with a database and the
[API](https://github.com/ministryofjustice/money-to-prisoners-api/) (from its published image),
which is loaded with test data the first time it starts. The first start takes a few minutes.

- The site is at [http://localhost:8004/](http://localhost:8004/), or [http://localhost:3004/](http://localhost:3004/)
  to have the browser reload as you change templates, styles and scripts
- The API admin is at [http://localhost:8000/admin/](http://localhost:8000/admin/) – sign in as `admin` / `adminadmin`
- To find a prisoner to send money to, use a prisoner number and date of birth from
  [prisoner locations](http://localhost:8000/admin/prison/prisonerlocation/) in the API admin

Run `docker compose --profile full up` to also start the other Prisoner Money apps, from their published images.
Run `docker compose up --build` after changing Python or Node.js dependencies,
and `docker compose down -v` to start again with fresh test data.

Card payments stop with an error at the payment step because there is no GOV.UK Pay account locally.
The [getting-started guide](https://github.com/ministryofjustice/money-to-prisoners-deploy/blob/main/docs/getting-started.md)
covers test logins, local addresses and what does not work locally.

## Running locally without Docker

It’s recommended that you use a python virtual environment to isolate each application.

The simplest way to do this is using:

```shell
python3 -m venv venv    # creates a virtual environment for dependencies; only needed the first time
. venv/bin/activate     # activates the virtual environment; needed every time you use this app
```

Some build tasks expect the active virtual environment to be at `/venv/`, but should generally work regardless of
its location.

You can copy `mtp_send_money/settings/local.py.sample` to `local.py` to overlay local settings that won’t be committed,
but it’s not required for a standard setup.

In order to run the application locally, it is necessary to have the API running.
Please refer to the [money-to-prisoners-api](https://github.com/ministryofjustice/money-to-prisoners-api/) repository.

Once the API has started locally, run

```shell
./run.py serve
# or
./run.py start
```

This will build everything and run the local server at [http://localhost:8004/](http://localhost:8004/).
The former also starts browser-sync at [http://localhost:3004/](http://localhost:3004/).

All build/development actions can be listed with `./run.py --verbosity 2 help`.

## Developing

[![Build, test and push](https://github.com/ministryofjustice/money-to-prisoners-send-money/actions/workflows/build-test-push.yml/badge.svg)](https://github.com/ministryofjustice/money-to-prisoners-send-money/actions/workflows/build-test-push.yml)

With the `./run.py` command, you can run a browser-sync server, and get the assets
to automatically recompile when changes are made, run `./run.py serve` instead of
`./run.py start`. The server is then available at the URL indicated.

```shell
./run.py test
```

Runs all the application tests.

You can connect a local version of [money-to-prisoners-common](https://github.com/ministryofjustice/money-to-prisoners-common/)
for development by pre-pending the following task to the run script.

```shell
python_dependencies --common-path [path]
```

### Translating

Update translation files with `./run.py make_messages` – you need to do this every time any translatable text is updated.

Requires [transifex cli tool](https://github.com/transifex/cli#installation) for synchronisation:

Pull updates from Transifex with `./run.py translations --pull`.
You’ll need to update translation files afterwards and manually check that the merges occurred correctly.

Push latest English to Transifex with `./run.py translations --push`.
NB: you should pull updates before pushing to merge correctly.

## Deploying

This is handled by [money-to-prisoners-deploy](https://github.com/ministryofjustice/money-to-prisoners-deploy/).

## Additional Bespoke Packages

There are several dependencies of the ``money-to-prisoners-send-money`` python library which are maintained by this team, so they may require code-changes when the dependencies (e.g. Django) of the ``money-to-prisoners-send-money`` python library are incremented.

* django-zendesk-tickets: https://github.com/ministryofjustice/django-zendesk-tickets
* django-moj-irat: https://github.com/ministryofjustice/django-moj-irat
