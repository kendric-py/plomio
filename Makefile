APPS := api worker-parser worker-sessions

.PHONY: install-shared install-all $(addprefix install-,$(APPS)) $(addprefix run-,$(APPS)) lock-shared lock-all $(addprefix lock-,$(APPS))

install-shared:
	poetry install

install-all: install-shared $(addprefix install-,$(APPS))

install-%:
	poetry -C apps/$* install

lock-shared:
	poetry lock

lock-all: lock-shared $(addprefix lock-,$(APPS))

lock-%:
	poetry -C apps/$* lock

run-api:
	poetry -C apps/api run python -m apps.api.src

run-worker-parser:
	poetry -C apps/worker-parser run python -m worker_parser

run-worker-sessions:
	poetry -C apps/worker-sessions run python -m worker_sessions
