# infra

AWS CDK (TypeScript). Two stacks:

- `BudgetStack`: a monthly AWS cost budget with email alerts at 50%, 80%, 100% actual spend and 100% forecasted spend.
- `KnowledgeBaseStack` (us-east-1): the Bedrock Knowledge Base for seller policy docs. It contains an S3 docs bucket, an S3 Vectors bucket and index (1024-dim cosine), Titan Text Embeddings V2, an S3 data source with fixed 300-token / 20%-overlap chunks, and a least-privilege KB service role. Outputs: `KnowledgeBaseId`, `DataSourceId`, `DocsBucketName`. Needs no context and no credentials to synth.

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
