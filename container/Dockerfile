# Databricks Runtime base image with Playwright + Chromium pre-installed.
# See: https://docs.databricks.com/aws/en/compute/custom-containers
FROM databricksruntime/standard:16.4-LTS

# Store Playwright browsers in a shared location (not per-user cache).
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Install Playwright + databricks-sdk, then install Chromium with system dependencies.
# Using /databricks/python3/bin/pip ensures we install into the correct environment.
RUN /databricks/python3/bin/pip install --no-cache-dir playwright databricks-sdk && \
    /databricks/python3/bin/python -m playwright install --with-deps chromium && \
    chmod -R 755 /ms-playwright
