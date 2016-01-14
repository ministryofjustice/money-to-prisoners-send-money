# Send Money to Prisoners

[![Dependency Status](https://img.shields.io/david/ministryofjustice/money-to-prisoners-send-money.svg?style=flat-square&label=NPM%20deps)](https://david-dm.org/ministryofjustice/money-to-prisoners-send-money)
[![devDependency Status](https://img.shields.io/david/dev/ministryofjustice/money-to-prisoners-send-money.svg?style=flat-square&label=NPM%20devDeps)](https://david-dm.org/ministryofjustice/money-to-prisoners-send-money#info=devDependencies)

Citizen-facing public site for Money to Prisoners


## Running locally


In order to run the application locally, it is necessary to have the API running.
Please refer to the [money-to-prisoners-api](https://github.com/ministryofjustice/money-to-prisoners-api/) repository.

Once the API is running locally, run

```
./run.sh start
```

This will build everything (which will initially take a while) and run
the local server at [http://localhost:8004/](http://localhost:8004/).

### Alternative: Gulp

The method above is still experimental. The traditional way, which is closer
to how real deployments are done, is:

```
virtualenv -p python3 venv
source venv/bin/activate
pip install -r requirements/dev.txt
gulp
./manage runserver 8004
```

### Alternative: Docker

In order to run a server that's exactly similar to the production machines,
you need to have [Docker](http://docs.docker.com/installation/mac/) and
[Docker Compose](https://docs.docker.com/compose/install/) installed. Run

```
make run
```

and you should eventually be able to connect to the local server.

## Developing

With the `run.sh` command, you can run a browser-sync server, and get the assets
to automatically recompile when changes are made, run `./run.sh serve` instead of
`./run.sh start`. The server is then available at the URL indicated.

If you've used the second method method above, you can use `gulp serve`
but you'll also need to keep the server at port 8000 running.


```
./run.sh test
```

Runs all the application tests.


## Deploying

This is handled by MOJ Digital's CI server. Request access and head there. Consult the dev
runbook if necessary.
