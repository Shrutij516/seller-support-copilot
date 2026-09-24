#!/usr/bin/env node
import { App } from "aws-cdk-lib";

import { type BudgetConfig, BudgetStack, budgetConfigFromContext } from "../lib/budget-stack";

const app = new App();

let budget: BudgetConfig;
try {
  budget = budgetConfigFromContext(app.node);
} catch (err) {
  // Print only the message: a stack trace here would bury the fix.
  console.error(`\nERROR: ${err instanceof Error ? err.message : String(err)}\n`);
  process.exit(1);
}

new BudgetStack(app, "BudgetStack", {
  budget,
  description: "Seller Support Copilot: monthly cost budget and email alerts",
});
