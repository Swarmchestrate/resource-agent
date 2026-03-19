.PHONY: install test test-build test-down test-logs

install:
	wget https://github.com/Swarmchestrate/tosca/releases/download/v0.2.4/go-puccini_0.22.7-SNAPSHOT-3e85b40_linux_amd64.deb
	sudo dpkg -i go-puccini_0.22.7-SNAPSHOT-3e85b40_linux_amd64.deb || sudo apt --fix-broken install -y
	rm -f go-puccini_0.22.7-SNAPSHOT-3e85b40_linux_amd64.deb

## Run integration tests (build, start RAs, run test client, tear down)
test: test-build
	@docker compose -f docker-compose.test.yaml up --abort-on-container-exit --exit-code-from test-runner; \
	rc=$$?; \
	$(MAKE) -s test-down; \
	echo ""; \
	echo "============================================================"; \
	if [ $$rc -eq 0 ]; then \
		echo "INTEGRATION TEST PASSED"; \
	else \
		echo "INTEGRATION TEST FAILED (exit code $$rc)"; \
	fi; \
	echo "============================================================"; \
	exit $$rc

## Build test images
test-build:
	docker compose -f docker-compose.test.yaml build

## Tear down test containers and network
test-down:
	docker compose -f docker-compose.test.yaml down -v --remove-orphans

## Show logs from all test containers
test-logs:
	docker compose -f docker-compose.test.yaml logs
