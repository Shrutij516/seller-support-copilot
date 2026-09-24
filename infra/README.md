# infra

AWS CDK (TypeScript). Currently one stack, `BudgetStack`: a monthly AWS cost budget with email alerts at 50%, 80%, 100% actual spend and 100% forecasted spend.

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
