import { CfnOutput, RemovalPolicy, Stack, type StackProps } from "aws-cdk-lib";
import { CfnDataSource, CfnKnowledgeBase } from "aws-cdk-lib/aws-bedrock";
import { Effect, PolicyDocument, PolicyStatement, Role, ServicePrincipal } from "aws-cdk-lib/aws-iam";
import { BlockPublicAccess, Bucket, BucketEncryption } from "aws-cdk-lib/aws-s3";
import { CfnIndex, CfnVectorBucket } from "aws-cdk-lib/aws-s3vectors";
import type { Construct } from "constructs";

export const KB_REGION = "us-east-1";
export const EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0";
export const EMBEDDING_DIMENSIONS = 1024;
export const CHUNK_MAX_TOKENS = 300;
export const CHUNK_OVERLAP_PERCENT = 20;

// Explicit (not CloudFormation-generated) names so the CloudFormation execution policy can
// grant S3 Vectors access on these two exact ARNs (infra/bootstrap/cfn-exec-policy.json).
// Both follow the S3 Vectors naming rules: 3-63 chars; bucket [a-z0-9-], index [a-z0-9.-];
// start and end with a letter or number. Cost: these resources can't be replaced in place
// (e.g. a new dimension needs a new index name), and one stack per account/region.
export const VECTOR_BUCKET_NAME = "seller-copilot-kb-vectors";
export const VECTOR_INDEX_NAME = "seller-policies";

// Bedrock writes the chunk text and its own metadata blob into every vector. Both are too
// large for S3 Vectors' filterable-metadata limit, so they must be declared non-filterable
// when the index is created (it can't be changed afterwards).
export const NON_FILTERABLE_METADATA_KEYS = ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"];

// Minimal S3 Vectors actions for Bedrock KB ingest (put/delete) and query, per
// https://docs.aws.amazon.com/bedrock/latest/userguide/kb-permissions.html#kb-permissions-s3vectors
export const KB_S3VECTORS_ACTIONS = [
  "s3vectors:PutVectors",
  "s3vectors:GetVectors",
  "s3vectors:DeleteVectors",
  "s3vectors:QueryVectors",
  "s3vectors:GetIndex",
];

/**
 * Bedrock Knowledge Base over the seller policy docs: an S3 docs bucket (the data source),
 * an S3 Vectors bucket + index (the vector store), Titan Text Embeddings V2, and a service
 * role scoped to exactly those resources. Docs are uploaded and ingested out of band
 * (`make kb-upload`, `make kb-ingest`), never by a deploy.
 *
 * Synthesizes with no AWS credentials and no lookups: the account is the deploy-time
 * `AWS::AccountId` pseudo parameter unless CDK_DEFAULT_ACCOUNT pins it.
 */
export class KnowledgeBaseStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    const docsBucket = new Bucket(this, "DocsBucket", {
      blockPublicAccess: BlockPublicAccess.BLOCK_ALL,
      encryption: BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      versioned: false,
      // Deleting the stack deletes the bucket, but only once it's empty: no custom-resource
      // Lambda emptying it behind our back. Emptying is a deliberate manual step.
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: false,
    });

    const vectorBucket = new CfnVectorBucket(this, "VectorBucket", {
      vectorBucketName: VECTOR_BUCKET_NAME,
    });
    vectorBucket.applyRemovalPolicy(RemovalPolicy.DESTROY);

    const vectorIndex = new CfnIndex(this, "VectorIndex", {
      vectorBucketArn: vectorBucket.attrVectorBucketArn,
      indexName: VECTOR_INDEX_NAME,
      dimension: EMBEDDING_DIMENSIONS,
      distanceMetric: "cosine",
      dataType: "float32",
      metadataConfiguration: { nonFilterableMetadataKeys: NON_FILTERABLE_METADATA_KEYS },
    });
    vectorIndex.applyRemovalPolicy(RemovalPolicy.DESTROY);

    const embeddingModelArn = `arn:aws:bedrock:${this.region}::foundation-model/${EMBEDDING_MODEL_ID}`;

    // Policy is inline on the role (not a separate AWS::IAM::Policy), so it exists before
    // CloudFormation creates the KB, which validates the role's access at creation time.
    const kbRole = new Role(this, "KnowledgeBaseRole", {
      description: "Service role for the seller policies Bedrock Knowledge Base",
      // Confused-deputy protection: only Bedrock acting for a KB in this account may assume it.
      assumedBy: new ServicePrincipal("bedrock.amazonaws.com").withConditions({
        StringEquals: { "aws:SourceAccount": this.account },
        ArnLike: {
          "aws:SourceArn": `arn:aws:bedrock:${this.region}:${this.account}:knowledge-base/*`,
        },
      }),
      inlinePolicies: {
        KnowledgeBaseAccess: new PolicyDocument({
          statements: [
            new PolicyStatement({
              sid: "ListDocsBucket",
              effect: Effect.ALLOW,
              actions: ["s3:ListBucket"],
              resources: [docsBucket.bucketArn],
              conditions: { StringEquals: { "aws:ResourceAccount": this.account } },
            }),
            new PolicyStatement({
              sid: "ReadDocsObjects",
              effect: Effect.ALLOW,
              actions: ["s3:GetObject"],
              resources: [docsBucket.arnForObjects("*")],
              conditions: { StringEquals: { "aws:ResourceAccount": this.account } },
            }),
            new PolicyStatement({
              sid: "InvokeEmbeddingModel",
              effect: Effect.ALLOW,
              actions: ["bedrock:InvokeModel"],
              resources: [embeddingModelArn],
            }),
            new PolicyStatement({
              sid: "ReadWriteVectorIndex",
              effect: Effect.ALLOW,
              actions: KB_S3VECTORS_ACTIONS,
              resources: [vectorIndex.attrIndexArn],
            }),
          ],
        }),
      },
    });

    const knowledgeBase = new CfnKnowledgeBase(this, "KnowledgeBase", {
      name: "seller-support-policies",
      description: "Marketplace seller policies (data/policies) for Seller Support Copilot",
      roleArn: kbRole.roleArn,
      knowledgeBaseConfiguration: {
        type: "VECTOR",
        vectorKnowledgeBaseConfiguration: {
          embeddingModelArn,
          embeddingModelConfiguration: {
            bedrockEmbeddingModelConfiguration: {
              dimensions: EMBEDDING_DIMENSIONS,
              embeddingDataType: "FLOAT32",
            },
          },
        },
      },
      storageConfiguration: {
        type: "S3_VECTORS",
        s3VectorsConfiguration: { indexArn: vectorIndex.attrIndexArn },
      },
    });

    const dataSource = new CfnDataSource(this, "DocsDataSource", {
      name: "policies-s3",
      knowledgeBaseId: knowledgeBase.attrKnowledgeBaseId,
      dataSourceConfiguration: {
        type: "S3",
        s3Configuration: { bucketArn: docsBucket.bucketArn },
      },
      vectorIngestionConfiguration: {
        chunkingConfiguration: {
          chunkingStrategy: "FIXED_SIZE",
          fixedSizeChunkingConfiguration: {
            maxTokens: CHUNK_MAX_TOKENS,
            overlapPercentage: CHUNK_OVERLAP_PERCENT,
          },
        },
      },
    });

    new CfnOutput(this, "KnowledgeBaseId", { value: knowledgeBase.attrKnowledgeBaseId });
    new CfnOutput(this, "DataSourceId", { value: dataSource.attrDataSourceId });
    new CfnOutput(this, "DocsBucketName", { value: docsBucket.bucketName });
  }
}
