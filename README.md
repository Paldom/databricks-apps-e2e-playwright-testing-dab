# databricks-apps-e2e-playwright-testing-dab

E2E monitoring and auto-testing for Databricks Apps: scheduled Playwright test in Lakeflow Jobs, configured and deployed with DABs.

This repo is a minimal **Databricks Asset Bundles (DABs)** project that deploys:

1) A **Databricks App** (FastAPI) with UI (`/`) plus API routes under `/api/*` (including `/api/sample`)
2) A **Lakeflow Job** (Databricks Workflows job) that runs a **Playwright** browser test notebook against an app `/api/*` route
3) A **custom Docker container** (`dpal/playwright-databricks:1.0`) with Playwright + Chromium pre-installed
4) An **E2E wrapper job** that calls the monitor job via `run_job_task`

## Project layout

- `databricks.yml` – bundle root config
- `resources/` – bundle resources (app, cluster, jobs, secret scope)
- `app/` – Databricks App source code (`app.yaml`, `requirements.txt`, `main.py`)
- `src/` – notebooks used by the jobs (`playwright_test.ipynb`)
- `container/` – Dockerfile for the Playwright container image
- `.github/workflows/bundle.yml` – minimal CI/CD

## Local usage

### Prerequisites

- Databricks CLI `v0.252.0` or above (required for `resources.secret_scopes`)
- **Databricks Container Services** must be enabled in the workspace (required for custom Docker images)

#### Enable Databricks Container Services

A workspace admin must enable Container Services before deploying. Use the Databricks CLI:

```bash
databricks workspace-conf set-status --json '{"enableDcs": "true"}'
```

Or enable it in the workspace admin settings UI. See [Databricks Container Services documentation](https://docs.databricks.com/en/compute/custom-containers.html) for details.

#### Docker image

This project uses a pre-built Docker image with Playwright + Chromium:

```
dpal/playwright-databricks:1.0
```

The image is based on `databricksruntime/standard:16.4-LTS` and includes:
- Playwright Python package
- Chromium browser with system dependencies
- databricks-sdk

To use a custom image, override the `docker_image_url` variable or build your own from `container/Dockerfile`.

### 1) Create the service principal and generate OAuth credentials

Set the principal name in `databricks.yml` variable `service_principal_name` (default in this repo is workspace-specific), then create that principal in the UI.

From the Databricks workspace UI (matching the screenshots):

1. Open the profile menu (top-right) and click **Settings**.
2. Go to **Workspace admin** -> **Identity and access**.
3. In **Service principals**, click **Manage**.
4. Click **Add service principal** -> **Add new**.
5. Keep **Databricks managed**, set **Service principal name** to the value of `service_principal_name`, and click **Add**.
6. Open the new service principal, go to the **Secrets** tab, then click **Generate secret**.
7. Copy both values from the dialog:
   - `Client ID`
   - `Secret` (shown once, copy it immediately)

### 2) Authenticate with the Databricks CLI and deploy bundle resources

Use any supported auth method (PAT, OAuth, etc.), then:

```bash
databricks bundle validate -t dev
databricks bundle deploy -t dev
```

### 3) Add OAuth secrets to the deployed secret scope

This bundle follows the same secret-scope pattern as the Databricks `job_read_secret` example.

```bash
SECRET_SCOPE_NAME=$(databricks bundle summary -t dev -o json | jq -r '.resources.secret_scopes.app_oauth_scope.name')

databricks secrets put-secret "${SECRET_SCOPE_NAME}" client_id --string-value "<service-principal-client-id>"
databricks secrets put-secret "${SECRET_SCOPE_NAME}" client_secret --string-value "<service-principal-client-secret>"
```

### 4) Deploy + start the app

```bash
databricks bundle run -t dev hello-world-app
```

### 5) Grant app permissions to the service principal

The bundle defines app usage rights in `resources/app.yml`:

```yaml
permissions:
  - level: CAN_USE
    service_principal_name: "${var.service_principal_name}"
```

Apply it with deploy/redeploy, then verify in the app **Permissions** UI that the configured service principal has `CAN_USE`.

### 6) Run the monitoring job once

```bash
databricks bundle run -t dev monitor_app_job
```

The monitoring job uses a custom Docker container with Playwright pre-installed, so no bootstrap/install step is required. The healthcheck validates both the landing page (`/`) and the API endpoint (`/api/sample`).

### 7) Run the E2E wrapper job (calls monitor job)

```bash
databricks bundle run -t dev e2e_test_job
```

## Important configuration

### App endpoint and API route

The monitoring notebook uses:

- `app_url = ${resources.apps.hello-world-app.name}`
- `api_path = ${var.api_route_path}` (default: `/api/sample`)
- `expected_api_message = ${var.expected_api_message}` (default: `Hello from API sample`)

This reuses the app resource name from `resources/app.yml`, so the composed app name is defined in one place. The notebook resolves the workspace host from `spark.conf.get("spark.databricks.workspaceUrl")` and composes the app URL as `https://<app_name>-<workspace-id>.<shard>.azure.databricksapps.com` for Azure, then appends `api_path`.

Per Databricks local-connect guidance, token-auth connectivity applies only to app routes under `/api/*`, so monitoring intentionally validates `/api/sample` instead of `/`.

Full website/UI access (for example `/`) requires an authenticated browser session cookie such as `__Host-databricksapps`, or an equivalent Playwright storage state (for example `context.storage_state(path="state.json")`). For security reasons, storing/reusing that cookie or storage state in automation is not recommended.

Reference: [Databricks Apps local connect](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/connect-local)

### Cluster node type (`node_type_id`)

`databricks.yml` currently defaults `node_type_id` to Azure value `Standard_DS3_v2`.

If you deploy on AWS or GCP, override this variable for your target/environment:

```bash
databricks bundle deploy -t dev --var="node_type_id=<your-node-type>"
```

Examples:

- AWS: `--var="node_type_id=t3.medium"`
- GCP: `--var="node_type_id=n2-standard-4"`

### Test artifact storage (PDF reports)

The monitoring job saves PDF screenshots and a JSON summary to a Unity Catalog volume using the Databricks SDK Files API (`workspace.files`).

**Configuration:**

- `artifacts_volume_path` - UC volume path for test artifacts (default: `/Volumes/data/playwright/results`)
- Set to empty string to disable artifact storage

**Output structure:**

```
/Volumes/data/playwright/results/
  2025-02-23_14-30-00-run-12345/
    landing-page.pdf
    api-endpoint.pdf
    summary.json
```

Each test run creates a timestamped folder containing:
- `landing-page.pdf` - PDF screenshot of the landing page
- `api-endpoint.pdf` - PDF screenshot of the API response
- `summary.json` - Test results metadata (status, URLs, timestamps)

**Prerequisites:**

1. Create the schema and volume in Unity Catalog:
   ```sql
   CREATE SCHEMA IF NOT EXISTS data.playwright;
   CREATE VOLUME IF NOT EXISTS data.playwright.results;
   ```

2. Ensure the service principal has write access to the volume.

**Override the path:**

```bash
databricks bundle deploy -t dev --var="artifacts_volume_path=/Volumes/my_catalog/my_schema/my_volume"
```

To disable artifact storage:

```bash
databricks bundle deploy -t dev --var="artifacts_volume_path="
```

### Secret scope and authentication

- The bundle creates `resources.secret_scopes.app_oauth_scope`.
- The monitoring job passes that scope name to the notebook as parameter `scope`.
- The notebook reads:
  - `client_id` from `dbutils.secrets.get(scope=scope, key="client_id")`
  - `client_secret` from `dbutils.secrets.get(scope=scope, key="client_secret")`
- The notebook authenticates with `WorkspaceClient(...).config.authenticate()` and uses the returned `Authorization` header for the Playwright request.
- That `Authorization` header should be used for `/api/*` routes only, not full website/UI pages.

## CI/CD (GitHub Actions)

Add GitHub secrets:

- `DATABRICKS_HOST`
- `DATABRICKS_TOKEN`

For a fresh workspace, do a one-time manual bootstrap before relying on CI:

1. Deploy the bundle once (`databricks bundle deploy -t dev`).
2. Populate the deployed secret scope with `client_id` and `client_secret` (Step 3 above).
3. Ensure the configured service principal has app permission `CAN_USE` (Step 5 above).

Without this bootstrap, the CI E2E run can fail during authentication or app access checks.

After bootstrap, pushes to `main` will deploy the bundle, deploy/start the app, and run the E2E job.
