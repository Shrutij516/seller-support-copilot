import { readFileSync } from "node:fs";
import { join } from "node:path";

import { App } from "aws-cdk-lib";
import { Match, Template } from "aws-cdk-lib/assertions";

import {
  AUTH_REGION,
  AuthStack,
  HOSTED_DOMAIN_PREFIX,
  USER_GROUPS,
  WEB_CALLBACK_URL,
  WEB_LOGOUT_URL,
} from "../lib/auth-stack";

function synth(): Template {
  const app = new App();
  return Template.fromStack(new AuthStack(app, "TestAuthStack", { env: { region: AUTH_REGION } }));
}

/** Reads a NEXT_PUBLIC_* value from apps/web/.env.example, the web app's documented config. */
function webEnvExample(key: string): string {
  const text = readFileSync(join(__dirname, "..", "..", "apps", "web", ".env.example"), "utf8");
  const line = text.split("\n").find((l) => l.startsWith(`${key}=`));
  if (!line) throw new Error(`${key} not in apps/web/.env.example`);
  return line.slice(key.length + 1).trim();
}

describe("AuthStack", () => {
  const template = synth();

  test("user pool: self sign-up disabled (admin-created users only)", () => {
    template.hasResourceProperties("AWS::Cognito::UserPool", {
      AdminCreateUserConfig: { AllowAdminCreateUserOnly: true },
    });
  });

  test("user pool: Lite plan, email sign-in, strong passwords, email-only recovery, demo teardown", () => {
    template.hasResourceProperties("AWS::Cognito::UserPool", {
      UserPoolTier: "LITE",
      UsernameAttributes: ["email"],
      Policies: {
        PasswordPolicy: Match.objectLike({
          MinimumLength: 12,
          RequireLowercase: true,
          RequireUppercase: true,
          RequireNumbers: true,
          RequireSymbols: true,
        }),
      },
      AccountRecoverySetting: { RecoveryMechanisms: [{ Name: "verified_email", Priority: 1 }] },
      DeletionProtection: "INACTIVE",
    });
    template.hasResource("AWS::Cognito::UserPool", { DeletionPolicy: "Delete" });
  });

  test("MFA is optional and TOTP-only (no SMS)", () => {
    template.hasResourceProperties("AWS::Cognito::UserPool", {
      MfaConfiguration: "OPTIONAL",
      EnabledMfas: ["SOFTWARE_TOKEN_MFA"],
      SmsConfiguration: Match.absent(),
    });
  });

  test("groups seller and admin exist", () => {
    expect(USER_GROUPS).toEqual(["seller", "admin"]);
    template.resourceCountIs("AWS::Cognito::UserPoolGroup", 2);
    for (const group of USER_GROUPS) {
      template.hasResourceProperties("AWS::Cognito::UserPoolGroup", { GroupName: group });
    }
  });

  test("app client: public (no secret), code grant only, no implicit, no client credentials", () => {
    template.resourceCountIs("AWS::Cognito::UserPoolClient", 1);
    template.hasResourceProperties("AWS::Cognito::UserPoolClient", {
      GenerateSecret: false,
      AllowedOAuthFlows: ["code"],
      AllowedOAuthFlowsUserPoolClient: true,
      AllowedOAuthScopes: ["openid", "email", "profile"],
      ExplicitAuthFlows: ["ALLOW_REFRESH_TOKEN_AUTH"],
      SupportedIdentityProviders: ["COGNITO"],
    });
  });

  test("app client: token revocation on, access token 1 hour, user existence errors hidden", () => {
    template.hasResourceProperties("AWS::Cognito::UserPoolClient", {
      EnableTokenRevocation: true,
      PreventUserExistenceErrors: "ENABLED",
      AccessTokenValidity: 60,
      TokenValidityUnits: Match.objectLike({ AccessToken: "minutes" }),
    });
  });

  test("callback and logout URLs match the web app's routes exactly", () => {
    expect(WEB_CALLBACK_URL).toBe(webEnvExample("NEXT_PUBLIC_COGNITO_REDIRECT_URI"));
    expect(WEB_LOGOUT_URL).toBe(webEnvExample("NEXT_PUBLIC_COGNITO_LOGOUT_URI"));
    template.hasResourceProperties("AWS::Cognito::UserPoolClient", {
      CallbackURLs: ["http://localhost:3000/auth/callback"],
      LogoutURLs: ["http://localhost:3000"],
    });
  });

  test("web scope request is allowed by the client", () => {
    const requested = webEnvExample("NEXT_PUBLIC_COGNITO_SCOPE").split(/\s+/);
    for (const scope of requested) expect(["openid", "email", "profile"]).toContain(scope);
  });

  test("prefix domain on the classic hosted UI (Lite plan) uses the fixed prefix constant", () => {
    template.hasResourceProperties("AWS::Cognito::UserPoolDomain", {
      Domain: HOSTED_DOMAIN_PREFIX,
      ManagedLoginVersion: 1,
      CustomDomainConfig: Match.absent(),
    });
  });

  test("domain prefix never contains the account ID (it would be public in every login URL)", () => {
    const domains = Object.values(template.findResources("AWS::Cognito::UserPoolDomain")).map(
      (r) => (r.Properties as { Domain: unknown }).Domain,
    );
    expect(domains).toHaveLength(1);
    expect(typeof domains[0]).toBe("string"); // a literal, not an intrinsic built from tokens
    expect(JSON.stringify(domains[0])).not.toContain("AWS::AccountId");
    expect(HOSTED_DOMAIN_PREFIX).not.toMatch(/\d{12}/);
  });

  test("domain prefix follows Cognito's prefix rules", () => {
    // CreateUserPoolDomain Domain pattern, plus the developer guide's reserved terms.
    expect(HOSTED_DOMAIN_PREFIX).toMatch(/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/);
    for (const reserved of ["aws", "amazon", "cognito"]) {
      expect(HOSTED_DOMAIN_PREFIX).not.toContain(reserved);
    }
    expect(HOSTED_DOMAIN_PREFIX).toMatch(/^seller-copilot-[a-z0-9]{6}$/);
  });

  test("outputs the values the web app and API need", () => {
    for (const name of ["UserPoolId", "UserPoolClientId", "Issuer", "JwksUrl", "HostedDomain"]) {
      template.hasOutput(name, Match.anyValue());
    }
  });

  test("only reviewed resource types (no Lambda triggers, no SMS role)", () => {
    const types = [
      ...new Set(
        Object.values(template.toJSON().Resources as Record<string, { Type: string }>).map((r) => r.Type),
      ),
    ].sort();
    expect(types).toEqual([
      "AWS::Cognito::UserPool",
      "AWS::Cognito::UserPoolClient",
      "AWS::Cognito::UserPoolDomain",
      "AWS::Cognito::UserPoolGroup",
    ]);
  });
});
