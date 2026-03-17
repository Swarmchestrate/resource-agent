.PHONY: setup setup-system install db run

setup: setup-system install

install:
	pip install -r requirements.txt

setup-system:
	@echo "Installing Puccini..."
	wget -q https://github.com/Swarmchestrate/tosca/releases/download/v0.2.4/go-puccini_0.22.7-SNAPSHOT-3e85b40_linux_amd64.deb
	sudo dpkg -i go-puccini_0.22.7-SNAPSHOT-3e85b40_linux_amd64.deb || sudo apt --fix-broken install -y
	rm -f go-puccini_0.22.7-SNAPSHOT-3e85b40_linux_amd64.deb

	@echo "Installing OpenTofu..."
	curl --proto '=https' --tlsv1.2 -fsSL https://get.opentofu.org/install-opentofu.sh | bash -s -- --install-method standalone

db:
	docker rm -f pg-db 2>/dev/null || true
	docker run --name pg-db \
	 -e POSTGRES_USER=admin \
	 -e POSTGRES_PASSWORD=adminpass \
	 -e POSTGRES_DB=swarmchestrate \
	 -p 5432:5432 -d postgres

run:
	set -a && . .env && set +a && python src/ra.py
