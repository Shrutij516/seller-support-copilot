import { readFileSync } from "node:fs";
import { join } from "node:path";

import { App } from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";

import {
  KB_REGION,
  KnowledgeBaseStack,
  VECTOR_BUCKET_NAME,
  VECTOR_INDEX_NAME,
} from "../lib/knowledge-base-stack";

interface Statement {
  readonly Sid?: string;
  readonly Effect: string;
  readonly Action: string | string[];
  readonly Resource: string | string[];
  readonly Condition?: Record<string, Record<string, string>>;
}

const POLICY_PATH = join(__dirname, "..", "bootstrap", "cfn-exec-policy.json");
// Policy variables can't stand in for the account field of an ARN (IAM: "Where you can use
// policy variables"), so the committed policy carries this placeholder and
// `make deploy-policy-*` substitutes the caller's account into a temp copy at create time.
const ACCOUNT_PLACEHOLDER = "{{ACCOUNT_ID}}";
const KB_ROLE_PATTERN = `arn:aws:iam::${ACCOUNT_PLACEHOLDER}:role/KnowledgeBaseStack-*`;
const VECTOR_BUCKET_ARN = `arn:aws:s3vectors:us-east-1:${ACCOUNT_PLACEHOLDER}:bucket/${VECTOR_BUCKET_NAME}`;
const VECTOR_INDEX_ARN = `${VECTOR_BUCKET_ARN}/index/${VECTOR_INDEX_NAME}`;
const BOOTSTRAP_VERSION_PARAM_ARN = `arn:aws:ssm:us-east-1:${ACCOUNT_PLACEHOLDER}:parameter/cdk-bootstrap/hnb659fds/version`;
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

/** IAM ARN matching: `*` matches any run of characters, `?` any single character. */
function iamArnMatches(pattern: string, arn: string): boolean {
  const regex = pattern
    .split("")
    .map((c) => (c === "*" ? ".*" : c === "?" ? "." : c.replace(/[.+^${}()|[\]\\]/g, "\\$&")))
    .join("");
  return new RegExp(`^${regex}$`).test(arn);
}

function synthKnowledgeBaseStack(): Record<string, unknown> {
  const app = new App();
  const stack = new KnowledgeBaseStack(app, "PolicyReviewKnowledgeBaseStack", {
    env: { region: KB_REGION },
  });
  return Template.fromStack(stack).toJSON();
}

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

  test("no Resource ARN has an account wildcard; account is the placeholder or absent", () => {
    const offenders: string[] = [];
    for (const s of statements) {
      for (const arn of resourcesOf(s).filter((r) => r !== "*")) {
        // arn:partition:service:region:account:resource. S3 bucket ARNs have no account.
        const account = arn.split(":")[4];
        const ok = account === ACCOUNT_PLACEHOLDER || (account === "" && arn.startsWith("arn:aws:s3:::"));
        if (!ok) offenders.push(`${s.Sid}: ${arn}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  test("S3 Vectors access is limited to the stack's exact vector bucket and index ARNs", () => {
    const vectorStatements = statements.filter((s) =>
      actionsOf(s).some((a) => a.startsWith("s3vectors:")),
    );
    const resources = vectorStatements.map((s) => resourcesOf(s));
    expect(resources).toEqual([[VECTOR_BUCKET_ARN], [VECTOR_INDEX_ARN]]);
  });

  test("renders to a placeholder-free policy with a 12-digit account in every ARN", () => {
    const rendered = readFileSync(POLICY_PATH, "utf8").replaceAll(ACCOUNT_PLACEHOLDER, "123456789012");
    expect(rendered).not.toContain("{{");
    const parsed = JSON.parse(rendered) as { Statement: Statement[] };
    for (const s of parsed.Statement) {
      for (const arn of asArray(s.Resource).filter((r) => r !== "*")) {
        expect(arn.split(":")[4]).toMatch(arn.startsWith("arn:aws:s3:::") ? /^$/ : /^\d{12}$/);
      }
    }
  });

  test("fits IAM's 6,144-character managed policy limit", () => {
    const compact = readFileSync(POLICY_PATH, "utf8").replace(/\s/g, "");
    expect(compact.length).toBeLessThanOrEqual(6144);
  });

  test("ReadCdkBootstrapVersion grants only ssm:GetParameters on the bootstrap version parameter", () => {
    const statement = statements.find((s) => s.Sid === "ReadCdkBootstrapVersion");
    expect(statement).toBeDefined();
    expect(actionsOf(statement!)).toEqual(["ssm:GetParameters"]);
    expect(resourcesOf(statement!)).toEqual([BOOTSTRAP_VERSION_PARAM_ARN]);
  });

  test("no ssm: action is granted on any other resource", () => {
    const ssmGrants = statements
      .filter((s) => actionsOf(s).some((a) => a.startsWith("ssm:")))
      .map((s) => ({ actions: actionsOf(s), resources: resourcesOf(s) }));
    expect(ssmGrants).toEqual([
      { actions: ["ssm:GetParameters"], resources: [BOOTSTRAP_VERSION_PARAM_ARN] },
    ]);
  });

  test("every SSM-typed template parameter is readable by the execution role", () => {
    // CloudFormation resolves AWS::SSM::Parameter::Value<...> parameters with the execution
    // role when it creates the change set (the 4c deploy failed on exactly this).
    const parameters = (synthKnowledgeBaseStack().Parameters ?? {}) as Record<
      string,
      { Type: string; Default?: string }
    >;
    const ssmParams = Object.entries(parameters).filter(([, p]) =>
      p.Type.startsWith("AWS::SSM::Parameter::Value<"),
    );
    expect(ssmParams.length).toBeGreaterThan(0); // the bootstrap version check, at least
    const unreadable = ssmParams
      .map(([name, p]) => ({
        name,
        arn: `arn:aws:ssm:us-east-1:${ACCOUNT_PLACEHOLDER}:parameter${p.Default ?? ""}`,
      }))
      .filter(
        ({ arn }) =>
          !statements.some(
            (s) =>
              actionsOf(s).includes("ssm:GetParameters") &&
              resourcesOf(s).some((pattern) => iamArnMatches(pattern, arn)),
          ),
      );
    expect(unreadable).toEqual([]);
  });

  test("KnowledgeBaseStack uses only resource types this policy was reviewed for", () => {
    const resources = synthKnowledgeBaseStack().Resources as Record<
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
