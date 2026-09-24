import { App } from "aws-cdk-lib";
import { Match, Template } from "aws-cdk-lib/assertions";

import { BudgetStack, budgetConfigFromContext } from "../lib/budget-stack";

const EMAIL = "test@example.com";

function synth(context: Record<string, unknown>): Template {
  const app = new App({ context });
  const stack = new BudgetStack(app, "TestBudgetStack", {
    budget: budgetConfigFromContext(app.node),
  });
  return Template.fromStack(stack);
}

function notification(type: string, threshold: number) {
  return {
    Notification: {
      NotificationType: type,
      ComparisonOperator: "GREATER_THAN",
      Threshold: threshold,
      ThresholdType: "PERCENTAGE",
    },
    Subscribers: [{ SubscriptionType: "EMAIL", Address: EMAIL }],
  };
}

describe("BudgetStack", () => {
  test("creates one monthly cost budget with the default 25 USD limit", () => {
    const template = synth({ budgetEmail: EMAIL });
    template.resourceCountIs("AWS::Budgets::Budget", 1);
    template.hasResourceProperties("AWS::Budgets::Budget", {
      Budget: Match.objectLike({
        BudgetType: "COST",
        TimeUnit: "MONTHLY",
        BudgetLimit: { Amount: 25, Unit: "USD" },
      }),
    });
  });

  test("has exactly the four required notifications", () => {
    const template = synth({ budgetEmail: EMAIL });
    template.hasResourceProperties("AWS::Budgets::Budget", {
      NotificationsWithSubscribers: [
        notification("ACTUAL", 50),
        notification("ACTUAL", 80),
        notification("ACTUAL", 100),
        notification("FORECASTED", 100),
      ],
    });
  });

  test("uses budgetAmount from context, including string values from -c", () => {
    const template = synth({ budgetEmail: EMAIL, budgetAmount: "40" });
    template.hasResourceProperties("AWS::Budgets::Budget", {
      Budget: Match.objectLike({ BudgetLimit: { Amount: 40, Unit: "USD" } }),
    });
  });

  test("fails with a clear message when budgetEmail is missing", () => {
    expect(() => synth({})).toThrow(/Missing CDK context 'budgetEmail'/);
  });

  test("rejects an invalid email", () => {
    expect(() => synth({ budgetEmail: "not-an-email" })).toThrow(/not a valid email/);
  });

  test("rejects a non-positive amount", () => {
    expect(() => synth({ budgetEmail: EMAIL, budgetAmount: "0" })).toThrow(
      /must be a positive number/,
    );
  });
});
