# TOSCA in Swarmchestrate

This repository is home to TOSCA in the [Swarmchestrate](https://www.swarmchestrate.eu/) project, which will use TOSCA v2.0 to describe applications and capacities managed in a Swarmchestrate Universe.

Any `.yaml` files committed to the `templates/` directory will be validated on pushes or pull requests by [Puccini](https://github.com/tliron/puccini), using a GitHub Action.

## Devs

It is recommended that developers open a GitHub Codespace on this repository, which includes dependencies and a Makefile for running Puccini manually. Simply drop a TOSCA service template into the `templates/` directory and run `make parse`. 

## Contact

Contact Jay at Westminster for support with TOSCA and/or this repository.
