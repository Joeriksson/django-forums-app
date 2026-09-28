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
	@docker compose -f docker-compose-prod.yml down && docker compose -f docker-compose-prod.yml up -d

prod_down:
	@docker compose -f docker-compose-prod.yml down
# Known vulnerabilities that can't be fixed yet. Remove each line with the upgrade that fixes it.
# Django 4.2 is past end of support; fixed only in 5.2 (Django 5.2 LTS upgrade)
AUDIT_IGNORE += --ignore-vuln PYSEC-2026-198 --ignore-vuln PYSEC-2026-199 --ignore-vuln PYSEC-2026-201
AUDIT_IGNORE += --ignore-vuln PYSEC-2026-2090 --ignore-vuln PYSEC-2026-2091 --ignore-vuln PYSEC-2026-2092
AUDIT_IGNORE += --ignore-vuln PYSEC-2026-3717
# django-allauth: fixed in 65.x (allauth upgrade)
AUDIT_IGNORE += --ignore-vuln PYSEC-2025-110 --ignore-vuln PYSEC-2025-111 --ignore-vuln PYSEC-2026-56
# markdown: fixed in 3.8.1, held back by martor 1.6 (allauth upgrade PR checks martor)
AUDIT_IGNORE += --ignore-vuln PYSEC-2026-89

# Check the locked dependencies (incl. dev) for known vulnerabilities; runs on the host with uv
audit:
	@uv export --frozen --no-emit-project --format requirements-txt \
		| uvx pip-audit==2.10.1 --requirement /dev/stdin --require-hashes --disable-pip --strict $(AUDIT_IGNORE)
