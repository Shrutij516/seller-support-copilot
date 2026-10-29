import { Aws, CfnOutput, Duration, RemovalPolicy, Stack, type StackProps } from "aws-cdk-lib";
import {
  AccountRecovery,
  CfnUserPoolClient,
  CfnUserPoolGroup,
  FeaturePlan,
  ManagedLoginVersion,
  Mfa,
  OAuthScope,
  UserPool,
  UserPoolClient,
  UserPoolDomain,
} from "aws-cdk-lib/aws-cognito";
import type { Construct } from "constructs";

export const AUTH_REGION = "us-east-1";

// Must match apps/web exactly: NEXT_PUBLIC_COGNITO_REDIRECT_URI and NEXT_PUBLIC_COGNITO_LOGOUT_URI
// (apps/web/.env.example). Cognito compares these strings exactly, trailing slash included.
export const WEB_CALLBACK_URL = "http://localhost:3000/auth/callback";
export const WEB_LOGOUT_URL = "http://localhost:3000";

// Must match the API's require_role(...) checks and the web's role gating (cognito:groups).
export const USER_GROUPS = ["seller", "admin"] as const;

/**
 * Cognito user pool for the web app (oidc-client-ts, Authorization Code + PKCE) and the API's
 * JWT checks (iss, client_id, token_use=access, cognito:groups). Invite-only: no self sign-up;
 * users are created by an admin (`make auth-create-user`). Demo pool: deletion protection off
 * and DESTROY on stack delete, so tearing down the stack deletes every user in it.
 *
 * Feature plan LITE with the classic hosted UI: covers everything used here (groups, the OIDC
 * authorization server with code grant, TOTP MFA, hosted sign-in pages) at the lowest price
 * (see DECISIONS.md, "Cognito feature plan: Lite with the classic hosted UI").
 */
export class AuthStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    const userPool = new UserPool(this, "UserPool", {
      userPoolName: "seller-support-copilot",
      featurePlan: FeaturePlan.LITE,
      selfSignUpEnabled: false,
      signInAliases: { email: true },
      signInCaseSensitive: false,
      autoVerify: { email: true },
      standardAttributes: { email: { required: true, mutable: true } },
      passwordPolicy: {
        minLength: 12,
        requireLowercase: true,
        requireUppercase: true,
        requireDigits: true,
        requireSymbols: true,
        tempPasswordValidity: Duration.days(3),
      },
      // TOTP (authenticator apps) only. SMS MFA costs money per message and needs an SNS role.
      mfa: Mfa.OPTIONAL,
      mfaSecondFactor: { otp: true, sms: false },
      accountRecovery: AccountRecovery.EMAIL_ONLY,
      deletionProtection: false,
      removalPolicy: RemovalPolicy.DESTROY,
    });

    for (const group of USER_GROUPS) {
      new CfnUserPoolGroup(this, `Group-${group}`, {
        userPoolId: userPool.userPoolId,
        groupName: group,
        description: `Copilot ${group}s (cognito:groups claim checked by the API)`,
      });
    }

    const client = new UserPoolClient(this, "WebClient", {
      userPool,
      userPoolClientName: "web",
      generateSecret: false, // public SPA client: a secret in browser code isn't a secret
      oAuth: {
        flows: { authorizationCodeGrant: true, implicitCodeGrant: false, clientCredentials: false },
        scopes: [OAuthScope.OPENID, OAuthScope.EMAIL, OAuthScope.PROFILE],
        callbackUrls: [WEB_CALLBACK_URL],
        logoutUrls: [WEB_LOGOUT_URL],
      },
      preventUserExistenceErrors: true,
      enableTokenRevocation: true,
      accessTokenValidity: Duration.hours(1),
      idTokenValidity: Duration.hours(1),
      refreshTokenValidity: Duration.days(1),
    });

    // Omitting ExplicitAuthFlows makes Cognito enable its default direct sign-in API flows
    // (SRP, custom). Sign-in here is only through the hosted UI + code grant, so allow just
    // refresh-token auth.
    (client.node.defaultChild as CfnUserPoolClient).explicitAuthFlows = ["ALLOW_REFRESH_TOKEN_AUTH"];

    const domain = new UserPoolDomain(this, "Domain", {
      userPool,
      cognitoDomain: { domainPrefix: `seller-copilot-${Aws.ACCOUNT_ID}` },
      managedLoginVersion: ManagedLoginVersion.CLASSIC_HOSTED_UI,
    });

    const issuer = `https://cognito-idp.${this.region}.amazonaws.com/${userPool.userPoolId}`;
    new CfnOutput(this, "UserPoolId", { value: userPool.userPoolId });
    new CfnOutput(this, "UserPoolClientId", { value: client.userPoolClientId });
    new CfnOutput(this, "Issuer", { value: issuer });
    new CfnOutput(this, "JwksUrl", { value: `${issuer}/.well-known/jwks.json` });
    new CfnOutput(this, "HostedDomain", { value: domain.baseUrl() });
  }
}
