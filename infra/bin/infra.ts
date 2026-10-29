#!/usr/bin/env node
import { App } from "aws-cdk-lib";

import { type BudgetConfig, BudgetStack, budgetConfigFromContext } from "../lib/budget-stack";
import { KB_REGION, KnowledgeBaseStack } from "../lib/knowledge-base-stack";
import { AUTH_REGION, AuthStack } from "../lib/auth-stack";

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

new KnowledgeBaseStack(app, "KnowledgeBaseStack", {
  // Region pinned (Titan V2 + S3 Vectors + the API all live there); account left to the
  // deploying credentials, so synth needs neither credentials nor lookups.
  env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: KB_REGION },
  description: "Seller Support Copilot: Bedrock Knowledge Base over seller policy docs",
});

new AuthStack(app, "AuthStack", {
  env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: AUTH_REGION },
  description: "Seller Support Copilot: Cognito user pool, groups, web app client, hosted UI domain",
});
