up:
	docker-compose up

down:
	docker-compose down

test:
	docker-compose run backend pytest

migrate:
	docker-compose run backend python scripts/migrate.py

shell:
	docker-compose run backend bash
