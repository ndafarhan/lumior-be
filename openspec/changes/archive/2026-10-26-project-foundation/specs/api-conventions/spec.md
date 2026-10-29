# Spec Delta

## Purpose

Defines the contract every Lumior backend endpoint follows, so the separately developed frontend can rely on one base path, one error format, request tracing, a CORS policy, and a machine-readable API description.

## ADDED Requirements

### Requirement: Versioned API base path
All business endpoints SHALL be served under the `/api/v1` path prefix. Only health endpoints are served outside this prefix.

#### Scenario: Unknown path under the API prefix
- **WHEN** a client sends a request to `/api/v1/does-not-exist`
- **THEN** the system responds with HTTP 404 using the standard error format with code `not_found`

### Requirement: Uniform error response format
Every non-2xx response SHALL have a JSON body of the form `{"error": {"code", "message", "details", "request_id"}}`, where `code` is a stable machine-readable snake_case string, `message` is human-readable, `details` is a list (possibly empty), and `request_id` matches the response's `X-Request-ID` header.

#### Scenario: Resource not found
- **WHEN** a request targets a route that does not exist
- **THEN** the response body contains `error.code` equal to `not_found`, a non-empty `error.message`, `error.details` as a list, and `error.request_id` equal to the `X-Request-ID` header

#### Scenario: Method not allowed
- **WHEN** a client calls an existing path with an unsupported HTTP method
- **THEN** the system responds with HTTP 405 and `error.code` equal to `method_not_allowed`

### Requirement: Validation errors identify invalid fields
When a request fails input validation, the system SHALL respond with HTTP 422 and `error.code` equal to `validation_error`, with one `error.details` entry per invalid field containing the field location and a reason.

#### Scenario: Malformed request body
- **WHEN** a client sends a body with a missing required field to an endpoint that validates input
- **THEN** the system responds with HTTP 422, `error.code` equal to `validation_error`, and a `details` entry whose location identifies the missing field

### Requirement: Unexpected errors do not leak internals
When an unhandled error occurs, the system SHALL respond with HTTP 500 and `error.code` equal to `internal_error`, and the response SHALL NOT contain stack traces, exception messages, SQL, or configuration values.

#### Scenario: Unhandled exception
- **WHEN** an endpoint raises an unexpected exception
- **THEN** the system responds with HTTP 500, `error.code` equal to `internal_error`, a generic message, and no exception text in the body

### Requirement: Request ID on every response
Every response SHALL include an `X-Request-ID` header. If the request carries an `X-Request-ID` header with a value of 1 to 128 visible ASCII characters, the system SHALL reuse it; otherwise it SHALL generate a new unique ID.

#### Scenario: Client supplies a request ID
- **WHEN** a client sends a request with header `X-Request-ID: abc-123`
- **THEN** the response includes header `X-Request-ID: abc-123`

#### Scenario: Client omits the request ID
- **WHEN** a client sends a request without an `X-Request-ID` header
- **THEN** the response includes an `X-Request-ID` header with a newly generated value that differs between requests

#### Scenario: Client supplies an invalid request ID
- **WHEN** a client sends an `X-Request-ID` header longer than 128 characters
- **THEN** the response includes a newly generated `X-Request-ID` instead of the supplied value

### Requirement: CORS restricted to configured origins
The system SHALL allow cross-origin browser requests, including credentialed requests, only from origins in the configured allow-list, and SHALL NOT respond with a wildcard origin.

#### Scenario: Preflight from an allowed origin
- **WHEN** a browser sends an `OPTIONS` preflight from an origin in the allow-list
- **THEN** the response includes `Access-Control-Allow-Origin` equal to that origin and `Access-Control-Allow-Credentials: true`

#### Scenario: Request from a disallowed origin
- **WHEN** a browser sends a request from an origin not in the allow-list
- **THEN** the response does not include an `Access-Control-Allow-Origin` header

### Requirement: Published OpenAPI document
The system SHALL serve an OpenAPI 3 document describing all `/api/v1` endpoints at `GET /api/v1/openapi.json`, with a unique, stable `operationId` for every operation.

#### Scenario: Fetch the API description
- **WHEN** a client sends `GET /api/v1/openapi.json`
- **THEN** the system responds with HTTP 200 and a valid OpenAPI 3 JSON document

### Requirement: Interactive API docs disabled in production
The interactive API documentation UI SHALL be available in non-production environments and SHALL NOT be served when the environment is production.

#### Scenario: Docs in development
- **WHEN** the service runs with environment `development` and a client requests the docs UI
- **THEN** the system serves the documentation page

#### Scenario: Docs in production
- **WHEN** the service runs with environment `production` and a client requests the docs UI
- **THEN** the system responds with HTTP 404

### Requirement: Monetary amounts serialized as decimal strings
Any monetary amount in a request or response body SHALL be represented as a JSON string containing a decimal number (for example `"12500.00"`), together with an ISO 4217 currency code, and SHALL NOT be represented as a JSON number.

#### Scenario: Amount in a response
- **WHEN** an endpoint returns a monetary amount of twelve thousand five hundred
- **THEN** the JSON contains the amount as the string `"12500.00"` and an accompanying currency code, not the number `12500`

#### Scenario: Amount sent as a number
- **WHEN** a client sends a monetary amount as a JSON number
- **THEN** the system responds with HTTP 422 and `error.code` equal to `validation_error`
