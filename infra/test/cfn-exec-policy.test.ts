import { readFileSync } from "node:fs";
import { join } from "node:path";

import { App } from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";

import { KB_REGION, KnowledgeBaseStack } from "../lib/knowledge-base-stack";

interface Statement {
  readonly Sid?: string;
  readonly Effect: string;
  readonly Action: string | string[];
  readonly Resource: string | string[];
  readonly Condition?: Record<string, Record<string, string>>;
}

const POLICY_PATH = join(__dirname, "..", "bootstrap", "cfn-exec-policy.json");
const KB_ROLE_PATTERN = "arn:aws:iam::*:role/KnowledgeBaseStack-*";
const DOCS_BUCKET_PATTERN = "arn:aws:s3:::knowledgebasestack-*";

// Actions AWS gives no resource-level permissions for, each with its proof in
// bootstrap/README.md. Adding to this list is a reviewed decision, not a test fix.
const RESOURCE_STAR_ALLOWED = new Set(["bedrock:CreateKnowledgeBase"]);

// Resource types this policy has been reviewed against. A new type in KnowledgeBaseStack
// (or a deliberately-widened policy) has to be added here in the same reviewed diff.
const REVIEWED_RESOURCE_TYPES = [
  "AWS::Bedrock::DataSource",
  "AWS::Bedrock::KnowledgeBase",
  "AWS::IAM::Role",
  "AWS::S3::Bucket",
  "AWS::S3::BucketPolicy",
  "AWS::S3Vectors::Index",
  "AWS::S3Vectors::VectorBucket",
];

const asArray = (value: string | string[]): string[] => (Array.isArray(value) ? value : [value]);

function loadStatements(): Statement[] {
  const policy = JSON.parse(readFileSync(POLICY_PATH, "utf8")) as {
    Version: string;
    Statement: Statement[];
  };
  expect(policy.Version).toBe("2012-10-17");
  return policy.Statement;
}

describe("CloudFormation execution policy (bootstrap/cfn-exec-policy.json)", () => {
  const statements = loadStatements();
  const actionsOf = (s: Statement) => asArray(s.Action);
  const resourcesOf = (s: Statement) => asArray(s.Resource);

  test("every statement is an Allow with at least one action and resource", () => {
    for (const s of statements) {
      expect(s.Effect).toBe("Allow");
      expect(actionsOf(s).length).toBeGreaterThan(0);
      expect(resourcesOf(s).length).toBeGreaterThan(0);
    }
  });

  test('no Action "*" and no wildcard actions such as "s3:*" or "iam:Get*"', () => {
    const wildcards = statements.flatMap((s) =>
      actionsOf(s)
        .filter((a) => a.includes("*"))
        .map((a) => `${s.Sid}: ${a}`),
    );
    expect(wildcards).toEqual([]);
  });

  test("every iam: action is scoped to the KnowledgeBaseStack-* role pattern only", () => {
    const iamStatements = statements.filter((s) => actionsOf(s).some((a) => a.startsWith("iam:")));
    expect(iamStatements.length).toBeGreaterThan(0);
    for (const s of iamStatements) {
      expect({ sid: s.Sid, resources: resourcesOf(s) }).toEqual({
        sid: s.Sid,
        resources: [KB_ROLE_PATTERN],
      });
    }
  });

  test("iam:PassRole is alone in its statement and only to bedrock.amazonaws.com", () => {
    const passRole = statements.filter((s) => actionsOf(s).includes("iam:PassRole"));
    expect(passRole).toHaveLength(1);
    const [statement] = passRole;
    expect(actionsOf(statement!)).toEqual(["iam:PassRole"]);
    expect(statement!.Condition?.StringEquals?.["iam:PassedToService"]).toBe(
      "bedrock.amazonaws.com",
    );
  });

  test("every s3: action is scoped to the knowledgebasestack-* bucket pattern only", () => {
    for (const s of statements.filter((st) => actionsOf(st).some((a) => a.startsWith("s3:")))) {
      expect({ sid: s.Sid, resources: resourcesOf(s) }).toEqual({
        sid: s.Sid,
        resources: [DOCS_BUCKET_PATTERN],
      });
    }
  });

  test('Resource "*" appears only for documented no-resource-level actions', () => {
    const offenders = statements
      .filter((s) => resourcesOf(s).includes("*"))
      .flatMap((s) => actionsOf(s).filter((a) => !RESOURCE_STAR_ALLOWED.has(a)));
    expect(offenders).toEqual([]);
  });

  test("every statement is locked to us-east-1 via aws:RequestedRegion", () => {
    for (const s of statements) {
      expect({ sid: s.Sid, region: s.Condition?.StringEquals?.["aws:RequestedRegion"] }).toEqual({
        sid: s.Sid,
        region: "us-east-1",
      });
    }
  });

  test("fits IAM's 6,144-character managed policy limit", () => {
    const compact = readFileSync(POLICY_PATH, "utf8").replace(/\s/g, "");
    expect(compact.length).toBeLessThanOrEqual(6144);
  });

  test("KnowledgeBaseStack uses only resource types this policy was reviewed for", () => {
    const app = new App();
    const stack = new KnowledgeBaseStack(app, "PolicyReviewKnowledgeBaseStack", {
      env: { region: KB_REGION },
    });
    const resources = Template.fromStack(stack).toJSON().Resources as Record<
      string,
      { Type: string }
    >;
    // AWS::CDK::Metadata (added by the CLI, not in tests) needs no CloudFormation permissions.
    const types = [...new Set(Object.values(resources).map((r) => r.Type))]
      .filter((t) => t !== "AWS::CDK::Metadata")
      .sort();
    expect(types).toEqual(REVIEWED_RESOURCE_TYPES);
  });
});
