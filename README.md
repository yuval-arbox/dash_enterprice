# Enterprise Customers Dashboard

A single-page dashboard of every Jira ticket for Arbox's Enterprise customers, pulled from the **ECS** (Enterprise Customers - Sivan) board, plus linked engineering/product work from the **RD** and **PM** boards.

- Search for a business to see only its tickets, across all three boards.
- The summary numbers are clickable filters.
- `index.html` is the generated page - do not hand-edit it, it's overwritten on every rebuild.

## How it updates

`scripts/build_enterprise_tickets.py` pulls live data from the Jira REST API and regenerates `index.html` from `templates/enterprise_tickets_template.html`.

A scheduled GitHub Action (`.github/workflows/update-enterprise-tickets.yml`) runs it every 6 hours (and on manual dispatch), committing the refreshed page only when the data actually changed.

**Required repo secrets** (Settings → Secrets and variables → Actions):
- `JIRA_EMAIL` - the Atlassian account email used to authenticate
- `JIRA_API_TOKEN` - an API token for that account, from https://id.atlassian.com/manage-profile/security/api-tokens

## Publishing the page

Enable GitHub Pages for this repo (Settings → Pages → Source: Deploy from a branch → `main` / `(root)`) to get a public URL at `https://yuval-arbox.github.io/dash_enterprice/`.
