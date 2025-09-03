.PHONY: parse install

parse:
	@success=0; \
	fail=0; \
	for file in $(shell find templates -name "*.yaml"); do \
		echo "Processing $$file"; \
		if /usr/bin/puccini-tosca parse $$file -x data_types.string.permissive > /dev/null 2>&1; then \
			echo "✔️  Success: $$file"; \
			success=$$((success + 1)); \
		else \
			echo "❌ Failed: $$file"; \
			fail=$$((fail + 1)); \
			echo "---- Error Output ----"; \
			/usr/bin/puccini-tosca parse $$file -x data_types.string.permissive; \
			echo "----------------------"; \
		fi; \
	done; \
	echo "----------------------------"; \
	echo "✅ Total Successful: $$success"; \
	echo "❌ Total Failed: $$fail"; \
	echo "----------------------------"; \
	if [ $$fail -gt 0 ]; then \
		exit 1; \
	fi

install:
	wget https://github.com/tliron/puccini/releases/download/v0.22.6/puccini_0.22.6_linux_amd64.deb && \
	sudo dpkg -i puccini_0.22.6_linux_amd64.deb || sudo apt --fix-broken install -y && \
	rm -f puccini_0.22.6_linux_amd64.deb