APPS := api worker_parser worker_sessions

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

run-worker_parser:
	poetry -C apps/worker_parser run python -m apps.worker_parser.src

run-worker_sessions:
	poetry -C apps/worker_sessions run python -m apps.worker_sessions.src
