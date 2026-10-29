import { App } from "aws-cdk-lib";
import { Match, Template } from "aws-cdk-lib/assertions";

import {
  CHUNK_MAX_TOKENS,
  CHUNK_OVERLAP_PERCENT,
  EMBEDDING_DIMENSIONS,
  KB_REGION,
  KB_S3VECTORS_ACTIONS,
  KnowledgeBaseStack,
  VECTOR_BUCKET_NAME,
  VECTOR_INDEX_NAME,
} from "../lib/knowledge-base-stack";

type Json = Record<string, unknown>;

interface FoundStatement {
  readonly where: string;
  readonly statement: Json;
}

const ACCOUNT_REF = { Ref: "AWS::AccountId" };

function synth(): Template {
  // No account in env: the same env-agnostic-account synth CI does without credentials.
  const app = new App();
  const stack = new KnowledgeBaseStack(app, "TestKnowledgeBaseStack", {
    env: { region: KB_REGION },
  });
  return Template.fromStack(stack);
}

function asArray(value: unknown): unknown[] {
  if (value === undefined) return [];
  return Array.isArray(value) ? value : [value];
}

/**
 * Every policy statement in the template: role trust and inline policies, managed/inline
 * AWS::IAM::Policy documents, and resource (bucket) policies. A new policy-bearing
 * resource type added later must be added here too, or it escapes the wildcard checks.
 */
function allStatements(template: Template): FoundStatement[] {
  const found: FoundStatement[] = [];
  const collect = (where: string, doc: unknown) => {
    for (const statement of asArray((doc as Json | undefined)?.Statement)) {
      found.push({ where, statement: statement as Json });
    }
  };
  for (const [id, role] of Object.entries(template.findResources("AWS::IAM::Role"))) {
    const props = role.Properties as Json;
    collect(`${id} trust`, props.AssumeRolePolicyDocument);
    for (const policy of asArray(props.Policies)) {
      collect(`${id} inline ${(policy as Json).PolicyName as string}`, (policy as Json).PolicyDocument);
    }
  }
  for (const type of ["AWS::IAM::Policy", "AWS::IAM::ManagedPolicy", "AWS::S3::BucketPolicy"]) {
    for (const [id, resource] of Object.entries(template.findResources(type))) {
      collect(id, (resource.Properties as Json).PolicyDocument);
    }
  }
  return found;
}

/** Render an intrinsic (Fn::Join / Ref / Fn::GetAtt) as a string so wildcards are visible. */
function render(value: unknown): string {
  if (typeof value === "string") return value;
  const obj = value as Json;
  if ("Fn::Join" in obj) {
    const [sep, parts] = obj["Fn::Join"] as [string, unknown[]];
    return parts.map(render).join(sep);
  }
  if ("Ref" in obj) return `<Ref ${String(obj.Ref)}>`;
  if ("Fn::GetAtt" in obj) return `<GetAtt ${(obj["Fn::GetAtt"] as string[]).join(".")}>`;
  return JSON.stringify(obj);
}

function isWildcardAction(action: string): boolean {
  return action === "*" || /^[a-z0-9-]+:\*$/i.test(action);
}

function isEnforceSslDeny(statement: Json): boolean {
  const condition = statement.Condition as Json | undefined;
  return (
    statement.Effect === "Deny" &&
    (condition?.Bool as Json | undefined)?.["aws:SecureTransport"] === "false"
  );
}

describe("KnowledgeBaseStack", () => {
  const template = synth();

  test("docs bucket blocks all public access, uses SSE-S3, is unversioned", () => {
    template.resourceCountIs("AWS::S3::Bucket", 1);
    template.hasResourceProperties("AWS::S3::Bucket", {
      PublicAccessBlockConfiguration: {
        BlockPublicAcls: true,
        BlockPublicPolicy: true,
        IgnorePublicAcls: true,
        RestrictPublicBuckets: true,
      },
      BucketEncryption: {
        ServerSideEncryptionConfiguration: [
          { ServerSideEncryptionByDefault: { SSEAlgorithm: "AES256" } },
        ],
      },
      VersioningConfiguration: Match.absent(),
    });
    template.hasResource("AWS::S3::Bucket", { DeletionPolicy: "Delete" });
  });

  test("docs bucket denies non-TLS requests", () => {
    const ssl = allStatements(template).filter(({ statement }) => isEnforceSslDeny(statement));
    expect(ssl).toHaveLength(1);
  });

  test("no auto-delete or BucketDeployment custom resources (no Lambda at all)", () => {
    template.resourceCountIs("AWS::Lambda::Function", 0);
    const custom = Object.values(template.toJSON().Resources as Record<string, Json>).filter(
      (r) => String(r.Type).startsWith("Custom::"),
    );
    expect(custom).toEqual([]);
  });

  test("S3 Vectors bucket and a 1024-dim cosine float32 index with Bedrock keys non-filterable", () => {
    template.resourceCountIs("AWS::S3Vectors::VectorBucket", 1);
    template.resourceCountIs("AWS::S3Vectors::Index", 1);
    template.hasResourceProperties("AWS::S3Vectors::VectorBucket", {
      VectorBucketName: "seller-copilot-kb-vectors",
    });
    template.hasResourceProperties("AWS::S3Vectors::Index", {
      IndexName: "seller-policies",
      Dimension: 1024,
      DistanceMetric: "cosine",
      DataType: "float32",
      MetadataConfiguration: {
        NonFilterableMetadataKeys: ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"],
      },
      VectorBucketArn: { "Fn::GetAtt": [Match.stringLikeRegexp("VectorBucket"), "VectorBucketArn"] },
    });
  });

  test("knowledge base uses Titan Text Embeddings V2 (1024) and S3_VECTORS storage", () => {
    template.resourceCountIs("AWS::Bedrock::KnowledgeBase", 1);
    template.hasResourceProperties("AWS::Bedrock::KnowledgeBase", {
      KnowledgeBaseConfiguration: {
        Type: "VECTOR",
        VectorKnowledgeBaseConfiguration: {
          EmbeddingModelArn:
            "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0",
          EmbeddingModelConfiguration: {
            BedrockEmbeddingModelConfiguration: {
              Dimensions: EMBEDDING_DIMENSIONS,
              EmbeddingDataType: "FLOAT32",
            },
          },
        },
      },
      StorageConfiguration: {
        Type: "S3_VECTORS",
        S3VectorsConfiguration: {
          IndexArn: { "Fn::GetAtt": [Match.stringLikeRegexp("VectorIndex"), "IndexArn"] },
        },
      },
    });
  });

  test("S3 data source on the docs bucket with fixed-size 300-token / 20% chunks", () => {
    template.resourceCountIs("AWS::Bedrock::DataSource", 1);
    template.hasResourceProperties("AWS::Bedrock::DataSource", {
      DataSourceConfiguration: {
        Type: "S3",
        S3Configuration: {
          BucketArn: { "Fn::GetAtt": [Match.stringLikeRegexp("DocsBucket"), "Arn"] },
        },
      },
      VectorIngestionConfiguration: {
        ChunkingConfiguration: {
          ChunkingStrategy: "FIXED_SIZE",
          FixedSizeChunkingConfiguration: {
            MaxTokens: CHUNK_MAX_TOKENS,
            OverlapPercentage: CHUNK_OVERLAP_PERCENT,
          },
        },
      },
    });
    expect([CHUNK_MAX_TOKENS, CHUNK_OVERLAP_PERCENT]).toEqual([300, 20]);
  });

  test("KB role trust is bedrock.amazonaws.com with SourceAccount and SourceArn conditions", () => {
    const trust = allStatements(template).filter(({ where }) => where.endsWith(" trust"));
    expect(trust).toHaveLength(1);
    expect(trust[0]?.statement).toEqual({
      Effect: "Allow",
      Action: "sts:AssumeRole",
      Principal: { Service: "bedrock.amazonaws.com" },
      Condition: {
        StringEquals: { "aws:SourceAccount": ACCOUNT_REF },
        ArnLike: {
          "aws:SourceArn": {
            "Fn::Join": ["", ["arn:aws:bedrock:us-east-1:", ACCOUNT_REF, ":knowledge-base/*"]],
          },
        },
      },
    });
  });

  test("KB role grants exactly the expected actions, each on its own scoped resource", () => {
    const logicalId = (type: string) => Object.keys(template.findResources(type))[0] ?? "";
    const docs = `<GetAtt ${logicalId("AWS::S3::Bucket")}.Arn>`;
    const index = `<GetAtt ${logicalId("AWS::S3Vectors::Index")}.IndexArn>`;
    const granted = Object.fromEntries(
      allStatements(template)
        .filter(({ where }) => where.includes(" inline "))
        .map(({ statement }) => [
          statement.Sid,
          { actions: asArray(statement.Action), resources: asArray(statement.Resource).map(render) },
        ]),
    );
    expect(granted).toEqual({
      ListDocsBucket: {
        actions: ["s3:ListBucket"],
        resources: [docs],
      },
      ReadDocsObjects: {
        actions: ["s3:GetObject"],
        resources: [`${docs}/*`],
      },
      InvokeEmbeddingModel: {
        actions: ["bedrock:InvokeModel"],
        resources: ["arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0"],
      },
      ReadWriteVectorIndex: {
        actions: KB_S3VECTORS_ACTIONS,
        resources: [index],
      },
    });
  });

  test('no Allow statement anywhere has Action "*", a service wildcard, or Resource "*"', () => {
    const offenders: string[] = [];
    for (const { where, statement } of allStatements(template)) {
      // The one Deny-everything statement is enforceSSL's: a wildcard Deny narrows access.
      if (isEnforceSslDeny(statement)) continue;
      for (const action of asArray(statement.Action).concat(asArray(statement.NotAction))) {
        if (typeof action === "string" && isWildcardAction(action)) {
          offenders.push(`${where}: Action ${action}`);
        }
      }
      for (const resource of asArray(statement.Resource).concat(asArray(statement.NotResource))) {
        if (render(resource) === "*") offenders.push(`${where}: Resource *`);
      }
      if (statement.Effect !== "Allow") offenders.push(`${where}: unexpected ${String(statement.Effect)}`);
    }
    expect(offenders).toEqual([]);
  });

  test("vector bucket and index names satisfy the S3 Vectors naming rules", () => {
    // https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-buckets-naming.html
    expect(VECTOR_BUCKET_NAME).toMatch(/^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$/);
    // https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-indexes.html#s3-vectors-indexes-naming
    expect(VECTOR_INDEX_NAME).toMatch(/^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$/);
  });

  test("outputs the KB id, data source id, and docs bucket name", () => {
    template.hasOutput("KnowledgeBaseId", {
      Value: { "Fn::GetAtt": [Match.anyValue(), "KnowledgeBaseId"] },
    });
    template.hasOutput("DataSourceId", { Value: { "Fn::GetAtt": [Match.anyValue(), "DataSourceId"] } });
    template.hasOutput("DocsBucketName", { Value: { Ref: Match.stringLikeRegexp("DocsBucket") } });
  });
});
