# infra

AWS CDK (TypeScript). Three stacks:

- `BudgetStack`: a monthly AWS cost budget with email alerts at 50%, 80%, 100% actual spend and 100% forecasted spend.
- `KnowledgeBaseStack` (us-east-1): the Bedrock Knowledge Base for seller policy docs. It contains an S3 docs bucket, an S3 Vectors bucket and index (1024-dim cosine), Titan Text Embeddings V2, an S3 data source with hierarchical chunking (parent 1,000 / child 150 / overlap 30 tokens), and a least-privilege KB service role. Outputs: `KnowledgeBaseId`, `DataSourceId`, `DocsBucketName`. Needs no context and no credentials to synth.
- `AuthStack` (us-east-1): the Cognito user pool for the web app and API. Invite-only (no self sign-up), email sign-in, optional TOTP MFA, `seller` and `admin` groups, a public PKCE code-flow app client for `http://localhost:3000`, and a classic hosted UI prefix domain on the Lite plan. Outputs: `UserPoolId`, `UserPoolClientId`, `Issuer`, `JwksUrl`, `HostedDomain`. Users are created with `make auth-create-user EMAIL=... GROUP=seller|admin`, and `make auth-env` prints the env lines for `apps/web/.env.local` and `services/api/.env`. Deployed manually, like the others.

```bash
npm ci
npm run build && npm test
npx cdk synth -c budgetEmail=you@example.com                     # default 25 USD
npx cdk synth -c budgetEmail=you@example.com -c budgetAmount=40  # override amount
```

Context:

| Key            | Required | Default | Notes                                                   |
| -------------- | -------- | ------- | ------------------------------------------------------- |
| `budgetEmail`  | yes      | none    | Synth fails with a clear message if missing or invalid. |
| `budgetAmount` | no       | `25`    | Monthly limit in USD.                                   |

Deploying is manual (`npx cdk deploy BudgetStack -c budgetEmail=...`) and is not run by CI. Budgets email alerts go straight to the address; no subscription confirmation is needed.

`KnowledgeBaseStack` is deployed manually too, and costs money once deployed. After deploying, load the docs and ingest them from the repo root: `make kb-upload` (syncs `data/policies` to the bucket, deleting anything not in the repo), then `make kb-ingest` (starts an ingestion job, waits, and prints statistics). Neither target runs in CI. To delete the stack, empty the docs bucket first: it has no auto-delete Lambda.
