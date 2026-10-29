# CloudFormation execution policy for CDK bootstrap

`cfn-exec-policy.json` is the only IAM policy CloudFormation gets when deploying CDK stacks in this account. It's attached to the bootstrap's `CloudFormationExecutionRole` via `cdk bootstrap --cloudformation-execution-policies`, instead of the default `AdministratorAccess`. It covers **`KnowledgeBaseStack` and `AuthStack` only**. Any other stack deployed with this bootstrap fails with AccessDenied until this policy is widened in a reviewed diff (see DECISIONS.md, "Scoped CloudFormation execution policy instead of default AdministratorAccess bootstrap").

`infra/test/cfn-exec-policy.test.ts` enforces the rules below. That test also fails if `KnowledgeBaseStack` gains a resource type this policy hasn't been reviewed for.

Usage, from the repo root: `make deploy-policy-create` (first time) or `make deploy-policy-update` (after editing the JSON), then `make cdk-bootstrap`. All three change real AWS resources and are run by hand after review. CI never runs them.

**Account placeholder.** The committed JSON has `{{ACCOUNT_ID}}` wherever an ARN's account field goes. It isn't a valid policy on its own. The `deploy-policy-*` targets get the caller's account from `aws sts get-caller-identity` and check that it's 12 digits. They then `sed` the account into a private `mktemp` file and refuse to continue if any `{{` remains. The rendered copy is passed to IAM and deleted on exit, so the account ID is never written into the repo.

Why not `${aws:PrincipalAccount}`: IAM allows policy variables in `Resource` "only in the resource portion of the ARN. This portion of the ARN appears after the fifth colon (:). You can't use a variable to replace parts of the ARN before the fifth colon, such as the service or account." ([Where you can use policy variables](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_variables.html#policy-vars-wheretouse))

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

All 67 `KnowledgeBaseStack` resource actions appear in those handler lists. The one action not from a handler list is `ssm:GetParameters` on the CDK bootstrap version parameter (see "Template parameters" below). That makes 68 for `KnowledgeBaseStack`. `AuthStack` adds 22 Cognito actions (see "AuthStack (Cognito)" below), for 90 in total.

## Template parameters

CloudFormation resolves every `AWS::SSM::Parameter::Value<...>` template parameter **with this execution role** when it creates the change set. The synthesized `KnowledgeBaseStack` has one: `BootstrapVersion` (`Type: AWS::SSM::Parameter::Value<String>`, `Default: /cdk-bootstrap/hnb659fds/version`), which CDK's `CheckBootstrapVersion` rule reads. Statement `ReadCdkBootstrapVersion` grants `ssm:GetParameters` on exactly `arn:aws:ssm:us-east-1:{{ACCOUNT_ID}}:parameter/cdk-bootstrap/hnb659fds/version`, region-locked. The test `every SSM-typed template parameter is readable by the execution role` fails if a stack adds an SSM-typed parameter this policy can't read.

## `Resource: "*"` exceptions

| Action | Why `*` | Evidence |
|---|---|---|
| `bedrock:CreateKnowledgeBase` | The action defines no resource type; the KB ARN doesn't exist until the call returns. Region-locked like everything else. | [Bedrock SAR](https://docs.aws.amazon.com/service-authorization/latest/reference/list_amazonbedrock.html): `CreateKnowledgeBase` has an empty "Resource types" column. Machine-readable copy: `bedrock.json`, which has no `Resources` key for it. |

| `cognito-idp:CreateUserPool` | No resource type: the pool's ARN doesn't exist until the call returns. Region-locked. | [Cognito user pools SAR](https://docs.aws.amazon.com/service-authorization/latest/reference/list_amazoncognitouserpools.html): empty "Resource types" for `CreateUserPool` (machine-readable `cognito-idp.json`: no `Resources` key). |
| `cognito-idp:DescribeUserPoolDomain` | No resource type: it's looked up by domain name, not pool ARN. Region-locked. | Same SAR: empty "Resource types" for `DescribeUserPoolDomain`. |

Those three are the only ones. Every other granted action supports a resource ARN and is scoped to one.

## AuthStack (Cognito)

- **Resource types** (synthesized `AuthStack`): `AWS::Cognito::UserPool`, `AWS::Cognito::UserPoolClient`, `AWS::Cognito::UserPoolGroup`, `AWS::Cognito::UserPoolDomain`.
- **Candidate actions:** the `handlers.{create,read,update,delete}.permissions` of `aws-cognito-userpool.json`, `aws-cognito-userpoolclient.json`, `aws-cognito-userpoolgroup.json` and `aws-cognito-userpooldomain.json` in the [CloudFormation schema bundle](https://schema.cloudformation.us-east-1.amazonaws.com/CloudformationSchema.zip). Template Reference pages:
  - https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-cognito-userpool.html
  - https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-cognito-userpoolclient.html
  - https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-cognito-userpoolgroup.html
  - https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-cognito-userpooldomain.html
- **Granted:** 22 `cognito-idp:` actions. 20 are scoped to `arn:aws:cognito-idp:us-east-1:{{ACCOUNT_ID}}:userpool/*` (statement `AuthStackUserPool`); `CreateUserPool` and `DescribeUserPoolDomain` are on `*` (statement `AuthStackNoResourceLevelSupport`; see the table above). Resource-level support was checked per action in the [Cognito user pools SAR](https://docs.aws.amazon.com/service-authorization/latest/reference/list_amazoncognitouserpools.html), whose ARN format is `arn:${Partition}:cognito-idp:${Region}:${Account}:userpool/${UserPoolId}`.
- **Left out:**
  - **KMS actions:** no customer-managed key.
  - **`iam:PassRole`, `iam:PutRolePolicy`, `iam:DeleteRolePolicy`, `iam:CreateServiceLinkedRole`:** these serve SMS roles, Lambda triggers and analytics, none of which `AuthStack` has. SMS MFA is off and there are no triggers.
  - **`cloudfront:updateDistribution`:** only for custom domains; this is a Cognito prefix domain.
  - **`cognito-idp:AddCustomAttributes`:** no custom attributes.

  If `AuthStack` adds any of these features, the first deploy fails with AccessDenied and this policy must be widened in a reviewed diff.
- **Scope note:** `userpool/*` covers every user pool in the account and region, because pool ids are generated. There's no predictable name to scope to, unlike the S3 Vectors resources.

## Resource scoping and naming

| Resource | Pattern | Why it's predictable (or not) |
|---|---|---|
| KB service role | `arn:aws:iam::{{ACCOUNT_ID}}:role/KnowledgeBaseStack-*` | The stack sets no `RoleName`, so CloudFormation names it `<stack name>-<logical id>-<random>`, for example `KnowledgeBaseStack-KnowledgeBaseRoleA2B317B9-ABC123...`. That's 57 characters, under the 64 limit, so it isn't truncated. Pattern from [Resource naming](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-name.html) ("`MyStack-MyBucket-abcdefghijk1`"). |
| Docs bucket | `arn:aws:s3:::knowledgebasestack-*` | Same `<stack>-<logical id>-<random>` scheme. S3 names must be lowercase, so the generated name is `knowledgebasestack-docsbucketecea003f-<random>` (about 50 characters, under 63, not truncated). |
| S3 Vectors bucket | `arn:aws:s3vectors:us-east-1:{{ACCOUNT_ID}}:bucket/seller-copilot-kb-vectors` | **Exact.** The stack sets `vectorBucketName` explicitly, because CloudFormation's generated vector bucket names have no documented prefix ([VectorBucket docs](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-s3vectors-vectorbucket.html): "generates a unique ID"). The ARN format `arn:${Partition}:s3vectors:${Region}:${Account}:bucket/${BucketName}` is from the [S3 Vectors SAR](https://docs.aws.amazon.com/service-authorization/latest/reference/list_amazons3vectors.html). The name follows the [vector bucket naming rules](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-buckets-naming.html): 3–63 characters, `a-z0-9-`, starting and ending with a letter or number. |
| S3 Vectors index | `arn:aws:s3vectors:us-east-1:{{ACCOUNT_ID}}:bucket/seller-copilot-kb-vectors/index/seller-policies` | **Exact.** The stack sets `indexName` explicitly. The SAR format is `.../bucket/${BucketName}/index/${IndexName}`. The name follows the [index naming rules](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-indexes.html#s3-vectors-indexes-naming): 3–63 characters, `a-z0-9.-`, starting and ending with a letter or number. |
| Knowledge Base + data source | `arn:aws:bedrock:us-east-1:{{ACCOUNT_ID}}:knowledge-base/*` | KB ARNs use a service-generated id (`knowledge-base/${KnowledgeBaseId}`). Data source actions authorize against the parent KB ARN (SAR). |

No `Resource` has an account wildcard. Every ARN with an account field uses the rendered account, and S3 bucket ARNs have no account field at all.

**Cost of the explicit vector names:**
- **No in-place replacement.** CloudFormation can't replace these two resources while keeping the same name. Changing the dimension, distance metric or non-filterable keys means picking a new index name (e.g. `seller-policies-v2`) and updating this policy in the same reviewed diff.
- **One stack per account and region.** Vector bucket names are unique per account and region, so a second copy of `KnowledgeBaseStack` there (e.g. a staging stack) would collide. It would need its own names and its own policy statements.

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
- **Correction (first deploy, 2026-10-29):** an earlier version of this README said the bootstrap version parameter was resolved with the deploy role's `ssm:GetParameters`, so this role needed no SSM permission. That was wrong. It rested on a comment in CDK's bootstrap template (the deploy role's `ReadVersion` statement), not on the synthesized template or CloudFormation's behavior. The first `cdk deploy` failed with AccessDenied on `ssm:GetParameters` for this execution role. See "Template parameters" above and the Incidents entry in DECISIONS.md.
- **Unverified against a real deployment.** This policy hasn't been exercised yet, because no AWS calls were allowed in this phase. A missing permission shows up as AccessDenied on the first deploy, followed by an automatic rollback. The fix is a reviewed widening of this file, not falling back to `AdministratorAccess`.
