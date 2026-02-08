# databricks-apps-e2e-playwright-testing-dab

E2E monitoring and auto-testing for Databricks Apps: scheduled Playwright test in Lakeflow Jobs, configured and deployed with DABs.

This repo is a minimal **Databricks Asset Bundles (DABs)** project that deploys:

1) A **Databricks App** (FastAPI) that returns `<h1>Hello World</h1>`  
2) A **Lakeflow Job** (Databricks Workflows job) that runs a **Playwright** browser test notebook against the app URL  
3) Two extra **ephemeral jobs**:
   - install Playwright + Chromium onto the named cluster from a notebook
   - run an E2E workflow that calls the monitor job via `run_job_task`

## Project layout

- `databricks.yml` – bundle root config
- `resources/` – bundle resources (app, cluster, jobs, secret scope)
- `app/` – Databricks App source code (`app.yaml`, `requirements.txt`, `main.py`)
- `src/` – notebooks used by the jobs (`install_playwright.ipynb`, `playwright_test.ipynb`)
- `.github/workflows/bundle.yml` – minimal CI/CD

## Local usage

### Prerequisite

- Databricks CLI `v0.252.0` or above (required for `resources.secret_scopes`)

### 1) Create the service principal and generate OAuth credentials

Set the principal name in `databricks.yml` variable `service_principal_name` (default: `app-monitoring`), then create that principal in the UI.

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

### 6) (Optional) Pre-install Playwright runtime on the monitoring cluster

```bash
databricks bundle run -t dev install_playwright_job
```

The install notebook uses `playwright install --with-deps chromium` to install both Chromium and required Linux shared libraries.

### 7) Run the monitoring job once

```bash
databricks bundle run -t dev monitor_app_job
```

`monitor_app_job` now includes a bootstrap task that runs the install notebook before the Playwright healthcheck, so scheduled runs are resilient after cluster restarts.

### 8) Run the E2E wrapper job (calls monitor job)

```bash
databricks bundle run -t dev e2e_test_job
```

## Important configuration

### App endpoint

The monitoring notebook uses a single app identifier parameter:

- `app_url = ${resources.apps.hello-world-app.name}`

This reuses the app resource name from `resources/app.yml`, so the composed app name is defined in one place. The notebook normalizes this value and composes the full URL as `https://<app_name>-<workspace_host>` by reading the workspace host from SDK/runtime config.

### Cluster node type (`node_type_id`)

`databricks.yml` currently defaults `node_type_id` to Azure value `Standard_DS3_v2`.

If you deploy on AWS or GCP, override this variable for your target/environment:

```bash
databricks bundle deploy -t dev --var="node_type_id=<your-node-type>"
```

Examples:

- AWS: `--var="node_type_id=t3.medium"`
- GCP: `--var="node_type_id=n2-standard-4"`

### Secret scope and authentication

- The bundle creates `resources.secret_scopes.app_oauth_scope`.
- The monitoring job passes that scope name to the notebook as parameter `scope`.
- The notebook reads:
  - `client_id` from `dbutils.secrets.get(scope=scope, key="client_id")`
  - `client_secret` from `dbutils.secrets.get(scope=scope, key="client_secret")`
- The notebook authenticates with `WorkspaceClient(...).config.authenticate()` and uses the returned `Authorization` header for the Playwright request.

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
