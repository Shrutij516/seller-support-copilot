import { Stack, type StackProps } from "aws-cdk-lib";
import { CfnBudget } from "aws-cdk-lib/aws-budgets";
import type { Construct, Node } from "constructs";

export const DEFAULT_BUDGET_AMOUNT_USD = 25;

export interface BudgetConfig {
  readonly amountUsd: number;
  readonly email: string;
}

/**
 * Reads `budgetAmount` (optional, default 25) and `budgetEmail` (required) from CDK context.
 * Throws with an actionable message so `cdk synth` fails fast on bad input.
 */
export function budgetConfigFromContext(node: Node): BudgetConfig {
  const email: unknown = node.tryGetContext("budgetEmail");
  if (typeof email !== "string" || email.trim() === "") {
    throw new Error(
      "Missing CDK context 'budgetEmail'. Pass it on the command line, " +
        "for example: cdk synth -c budgetEmail=you@example.com",
    );
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
    throw new Error(`CDK context 'budgetEmail' is not a valid email address: '${email}'`);
  }

  const rawAmount: unknown = node.tryGetContext("budgetAmount") ?? DEFAULT_BUDGET_AMOUNT_USD;
  const amountUsd = Number(rawAmount);
  if (!Number.isFinite(amountUsd) || amountUsd <= 0) {
    throw new Error(
      `CDK context 'budgetAmount' must be a positive number (USD), got '${String(rawAmount)}'`,
    );
  }

  return { amountUsd, email: email.trim() };
}

export interface BudgetStackProps extends StackProps {
  readonly budget: BudgetConfig;
}

/** Monthly AWS cost budget that emails at 50/80/100% actual spend and 100% forecasted spend. */
export class BudgetStack extends Stack {
  constructor(scope: Construct, id: string, props: BudgetStackProps) {
    super(scope, id, props);

    const alerts: { type: "ACTUAL" | "FORECASTED"; threshold: number }[] = [
      { type: "ACTUAL", threshold: 50 },
      { type: "ACTUAL", threshold: 80 },
      { type: "ACTUAL", threshold: 100 },
      { type: "FORECASTED", threshold: 100 },
    ];

    new CfnBudget(this, "MonthlyCostBudget", {
      budget: {
        budgetName: "seller-support-copilot-monthly",
        budgetType: "COST",
        timeUnit: "MONTHLY",
        budgetLimit: { amount: props.budget.amountUsd, unit: "USD" },
      },
      notificationsWithSubscribers: alerts.map((alert) => ({
        notification: {
          notificationType: alert.type,
          comparisonOperator: "GREATER_THAN",
          threshold: alert.threshold,
          thresholdType: "PERCENTAGE",
        },
        subscribers: [{ subscriptionType: "EMAIL", address: props.budget.email }],
      })),
    });
  }
}
