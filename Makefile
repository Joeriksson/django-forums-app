dev:
	@docker compose \
		-f docker-compose-dev.yml \
		down && \
		docker compose \
			-f docker-compose-dev.yml \
			up -d

dev_build:
	@docker compose \
		-f docker-compose-dev.yml \
		down && \
		docker compose \
			-f docker-compose-dev.yml \
			up -d --build

dev_logs:
	@docker compose -f docker-compose-dev.yml logs

dev_down:
	@docker compose -f docker-compose-dev.yml down

dev_export_data:
	@docker compose -f docker-compose-dev.yml exec web python manage.py dumpdata -a --format json -o forumsdata.json --exclude=auth --exclude=contenttypes  --exclude=sessions --natural-primary --settings=project.settings.development

dev_web_exec:
	@docker compose -f docker-compose-dev.yml exec web $(cmd)

dev_redis_exec:
	@docker compose -f docker-compose-dev.yml exec redis $(cmd)

dev_pytest:
	@docker compose -f docker-compose-dev.yml exec web pytest -v --disable-warnings

prod:
	@docker compose -f docker-compose-prod.yml up -d --force-recreate

prod_down:
	@docker compose -f docker-compose-prod.yml down
# Known vulnerabilities that can't be fixed yet. Remove each line with the upgrade that fixes it.
# Add them as: AUDIT_IGNORE += --ignore-vuln <ID>   (with a comment on which upgrade fixes it)
AUDIT_IGNORE =

# Check the locked dependencies (incl. dev) for known vulnerabilities; runs on the host with uv
audit:
	@uv export --frozen --no-emit-project --format requirements-txt \
		| uvx pip-audit==2.10.1 --requirement /dev/stdin --require-hashes --disable-pip --strict $(AUDIT_IGNORE)
