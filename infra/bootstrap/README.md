# CloudFormation execution policy for CDK bootstrap

`cfn-exec-policy.json` is the only IAM policy CloudFormation gets when deploying CDK stacks in this account. It's attached to the bootstrap's `CloudFormationExecutionRole` via `cdk bootstrap --cloudformation-execution-policies`, instead of the default `AdministratorAccess`. It covers **`KnowledgeBaseStack` only**. Any other stack deployed with this bootstrap fails with AccessDenied until this policy is widened in a reviewed diff (see DECISIONS.md, "Scoped CloudFormation execution policy instead of default AdministratorAccess bootstrap").

`infra/test/cfn-exec-policy.test.ts` enforces the rules below. That test also fails if `KnowledgeBaseStack` gains a resource type this policy hasn't been reviewed for.

Usage, from the repo root: `make deploy-policy-create` (first time) or `make deploy-policy-update` (after editing the JSON), then `make cdk-bootstrap`. All three change real AWS resources and are run by hand after review. CI never runs them.

## How the action list was derived

1. **Resource types** come from the synthesized template (`cdk synth`, then `cdk.out/KnowledgeBaseStack.template.json`): `AWS::S3::Bucket`, `AWS::S3::BucketPolicy`, `AWS::S3Vectors::VectorBucket`, `AWS::S3Vectors::Index`, `AWS::IAM::Role`, `AWS::Bedrock::KnowledgeBase`, `AWS::Bedrock::DataSource`, and `AWS::CDK::Metadata`. The last is a metadata-only resource that CloudFormation needs no permissions for.
2. **Candidate actions** are each type's `handlers.{create,read,update,delete}.permissions` from AWS's published CloudFormation resource schemas: https://schema.cloudformation.us-east-1.amazonaws.com/CloudformationSchema.zip (`aws-s3-bucket.json`, `aws-s3-bucketpolicy.json`, `aws-s3vectors-vectorbucket.json`, `aws-s3vectors-index.json`, `aws-iam-role.json`, `aws-bedrock-knowledgebase.json`, `aws-bedrock-datasource.json`). The `list` handlers aren't used: CloudFormation doesn't call them during stack create, update or delete. The Template Reference pages show the same lists where AWS has published them:
   - https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-s3vectors-vectorbucket.html
   - https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-s3vectors-index.html
   - https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-s3-bucket.html (no permissions section; schema used)
   - https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-s3-bucketpolicy.html (schema used)
   - https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-iam-role.html (schema used)
   - https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrock-knowledgebase.html (no permissions section; schema used)
   - https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrock-datasource.html (schema used)
3. **Resource-level support** for every granted action was checked in the Service Authorization Reference (machine-readable copy: `https://servicereference.us-east-1.amazonaws.com/v1/<service>/<service>.json`):
   - https://docs.aws.amazon.com/service-authorization/latest/reference/list_identityandaccessmanagement.html
   - https://docs.aws.amazon.com/service-authorization/latest/reference/list_amazons3.html
   - https://docs.aws.amazon.com/service-authorization/latest/reference/list_amazons3vectors.html
   - https://docs.aws.amazon.com/service-authorization/latest/reference/list_amazonbedrock.html
4. **Region lock:** every statement requires `aws:RequestedRegion = us-east-1`. It's a global condition key present on every request, including IAM, whose requests resolve to us-east-1: https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_condition-keys.html#condition-keys-requestedregion
5. **Pass-role restriction:** `iam:PassRole` is limited to `iam:PassedToService = bedrock.amazonaws.com`: https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_iam-condition-keys.html#ck_PassedToService

All 67 granted actions appear in those handler lists. Nothing outside them was added.

## `Resource: "*"` exceptions

| Action | Why `*` | Evidence |
|---|---|---|
| `bedrock:CreateKnowledgeBase` | The action defines no resource type; the KB ARN doesn't exist until the call returns. Region-locked like everything else. | [Bedrock SAR](https://docs.aws.amazon.com/service-authorization/latest/reference/list_amazonbedrock.html): `CreateKnowledgeBase` has an empty "Resource types" column. Machine-readable copy: `bedrock.json`, which has no `Resources` key for it. |

That's the only one. Every other granted action supports a resource ARN and is scoped to one.

## Resource scoping and naming

| Resource | Pattern | Why it's predictable (or not) |
|---|---|---|
| KB service role | `arn:aws:iam::*:role/KnowledgeBaseStack-*` | The stack sets no `RoleName`, so CloudFormation names it `<stack name>-<logical id>-<random>`, for example `KnowledgeBaseStack-KnowledgeBaseRoleA2B317B9-ABC123...`. That's 57 characters, under the 64 limit, so it isn't truncated. Pattern from [Resource naming](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-name.html) ("`MyStack-MyBucket-abcdefghijk1`"). |
| Docs bucket | `arn:aws:s3:::knowledgebasestack-*` | Same `<stack>-<logical id>-<random>` scheme. S3 names must be lowercase, so the generated name is `knowledgebasestack-docsbucketecea003f-<random>` (about 50 characters, under 63, not truncated). |
| S3 Vectors bucket | `arn:aws:s3vectors:us-east-1:*:bucket/*` | **Not predictable.** The [VectorBucket docs](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-s3vectors-vectorbucket.html) only say CloudFormation "generates a unique ID", with no stack-name prefix promised. The tightest honest scope is every vector bucket in this account and region. |
| S3 Vectors index | `arn:aws:s3vectors:us-east-1:*:bucket/*/index/*` | Same: [Index docs](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-s3vectors-index.html) say "generates a unique ID". |
| Knowledge Base + data source | `arn:aws:bedrock:us-east-1:*:knowledge-base/*` | KB ARNs use a service-generated id (`knowledge-base/${KnowledgeBaseId}`). Data source actions authorize against the parent KB ARN (SAR). |

Account is `*` in the IAM, S3 Vectors and Bedrock ARNs. An identity policy can't reach resources in another account unless that account's own resource policy also allows it, so this matches "this account" in practice.

**Proposed tightening (not done here, since it changes `KnowledgeBaseStack`):** give the vector bucket and index explicit names, e.g. `vectorBucketName: "knowledgebasestack-vectors"` and `indexName: "policies-v1"`. The S3 Vectors statements could then be scoped to exact ARNs. The cost: explicitly named resources can't be replaced in place, so changing the dimension or metric would mean a new name, such as `policies-v2`.

## Handler permissions deliberately left out (55)

Each of these is in a handler's list but serves a property or feature `KnowledgeBaseStack` doesn't use. If the stack starts using one, the deploy fails with AccessDenied and this policy must be widened in a reviewed diff.

- **`kms:*` actions (7):** no customer-managed KMS keys. The docs bucket uses SSE-S3, S3 Vectors uses its default encryption, and the KB has no key.
- **`s3tables:*` (9) and the `s3:*BucketMetadata*` create, update and delete actions (5):** S3 Metadata tables aren't configured.
- **`s3:Put*` and `s3:Delete*` bucket configuration actions** for properties the bucket doesn't set: ACL, CORS, lifecycle, logging, notifications, replication, website, versioning, object lock, ownership controls, inventory, metrics, analytics, intelligent tiering, accelerate, ABAC, default storage class. Also `s3:PutObjectAcl` and `s3:DeleteObject`. The matching **`Get*` read actions are kept**, because the read handler calls them after every create and update.
- **`iam:AttachRolePolicy`, `DetachRolePolicy`, `PutRolePermissionsBoundary`, `DeleteRolePermissionsBoundary`, `UpdateRole`:** the role has no managed policies, no permissions boundary, and no max-session setting. `UpdateRoleDescription` is kept because the role has a description.
- **`bedrock:AssociateThirdPartyKnowledgeBase`:** only for third-party vector stores.
- **`iam:PassRole` for S3 replication:** dropped. The only `PassRole` left is to Bedrock.

## Known caveats

- **`s3:GetBucketDefaultStorageClass`** is in the `AWS::S3::Bucket` read handler but not (yet) in the S3 Service Authorization Reference. It's kept so the read handler isn't denied, and is harmless if IAM never evaluates it.
- **The CDK bootstrap version check** (`/cdk-bootstrap/hnb659fds/version` SSM parameter) is resolved during `CreateChangeSet` with the bootstrap **deploy** role's `ssm:GetParameters`, not this execution role's. See the `ReadVersion` statement on `DeploymentActionRole` in `node_modules/aws-cdk/lib/api/bootstrap/bootstrap-template.yaml`. So no SSM permission here.
- **Unverified against a real deployment.** This policy hasn't been exercised yet, because no AWS calls were allowed in this phase. A missing permission shows up as AccessDenied on the first deploy, followed by an automatic rollback. The fix is a reviewed widening of this file, not falling back to `AdministratorAccess`.
