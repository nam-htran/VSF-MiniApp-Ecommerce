-- Every database in this container, in one place.
--
-- Separate databases rather than schemas inside one: Postgres cannot join
-- across databases, so V-Market physically cannot read V-App's tables.
-- That is the boundary the real system has, enforced by the engine
-- instead of by discipline.
--
-- Tables are not created here. Each app runs create_all at startup, so the
-- schema has a single source: the models.
--
-- Runs only when the data volume is empty. To re-run: docker compose down -v
CREATE DATABASE vmarket OWNER vmarket;
CREATE DATABASE vapp_mock OWNER vmarket;
