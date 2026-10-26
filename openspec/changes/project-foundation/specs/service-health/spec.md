# Spec Delta

## Purpose

Lets infrastructure and operators determine whether the Lumior backend process is running and whether it is able to serve requests that depend on the database.

## ADDED Requirements

### Requirement: Liveness endpoint
The system SHALL expose `GET /health/live` outside the versioned API path. It SHALL respond with HTTP 200 and a JSON body `{"status": "ok"}` whenever the process is able to handle HTTP requests, without checking any external dependency.

#### Scenario: Process is running
- **WHEN** a client sends `GET /health/live`
- **THEN** the system responds with HTTP 200 and body `{"status": "ok"}`

#### Scenario: Database is unavailable
- **WHEN** the database cannot be reached and a client sends `GET /health/live`
- **THEN** the system still responds with HTTP 200 and body `{"status": "ok"}`

### Requirement: Readiness endpoint
The system SHALL expose `GET /health/ready` outside the versioned API path. It SHALL report readiness only when the database accepts a query, returning a JSON body with an overall `status` and a per-check `checks.database` value of `ok` or `unavailable`.

#### Scenario: Database reachable
- **WHEN** the database accepts connections and a client sends `GET /health/ready`
- **THEN** the system responds with HTTP 200 and body `{"status": "ok", "checks": {"database": "ok"}}`

#### Scenario: Database unreachable
- **WHEN** the database cannot be reached and a client sends `GET /health/ready`
- **THEN** the system responds with HTTP 503 and body `{"status": "unavailable", "checks": {"database": "unavailable"}}`

### Requirement: Readiness check is bounded in time
The readiness check SHALL complete within 2 seconds even when the database does not respond, and SHALL treat a timeout as the database being unavailable.

#### Scenario: Database hangs
- **WHEN** the database accepts the connection but does not answer within 2 seconds
- **THEN** `GET /health/ready` responds within about 2 seconds with HTTP 503 and `checks.database` equal to `unavailable`

### Requirement: Health endpoints are public and non-sensitive
Health endpoints SHALL NOT require authentication and SHALL NOT include connection strings, hostnames, versions of dependencies, or error messages in their responses.

#### Scenario: Unauthenticated probe
- **WHEN** a client without credentials sends `GET /health/ready`
- **THEN** the system responds with a health result rather than an authentication error

#### Scenario: Failure details are not leaked
- **WHEN** the database connection fails with an error message
- **THEN** the readiness response body contains only the status fields and not the error message
