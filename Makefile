dev:
	@docker-compose \
		-f docker-compose-dev.yml \
		down && \
		docker-compose \
			-f docker-compose-dev.yml \
			up -d

dev_build:
	@docker-compose \
		-f docker-compose-dev.yml \
		down && \
		docker-compose \
			-f docker-compose-dev.yml \
			up -d --build

dev_logs:
	@docker-compose -f docker-compose-dev.yml logs

dev_down:
	@docker-compose -f docker-compose-dev.yml down

dev_export_data:
	@docker-compose -f docker-compose-dev.yml exec web python manage.py dumpdata -a --format json -o forumsdata.json --exclude=auth --exclude=contenttypes  --exclude=sessions --natural-primary --settings=project.settings.development

dev_web_exec:
	@docker-compose -f docker-compose-dev.yml exec web $(cmd)

dev_test:
	@docker-compose -f docker-compose-dev.yml exec web python manage.py test --settings=project.settings.test --parallel

dev_pytest:
	@docker-compose -f docker-compose-dev.yml exec web pytest tests/ -v

prod:
	@docker-compose -f docker-compose-prod.yml down && docker-compose -f docker-compose-prod.yml up -d

prod_down:
	@docker-compose -f docker-compose-prod.yml down