import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import type { User } from "oidc-client-ts";
import AdminCasesPage from "./page";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useAdminCases } from "@/lib/api/hooks";

vi.mock("@/lib/auth/AuthProvider", () => ({
  useAuth: vi.fn(),
}));

vi.mock("@/lib/api/hooks", () => ({
  useAdminCases: vi.fn(),
  useUpdateAdminCase: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  })),
}));

const mockedUseAuth = vi.mocked(useAuth);
const mockedUseAdminCases = vi.mocked(useAdminCases);

function authState(overrides: Partial<ReturnType<typeof useAuth>>): ReturnType<typeof useAuth> {
  return {
    user: null,
    roles: [],
    isLoading: false,
    configError: null,
    signIn: vi.fn(),
    signOut: vi.fn(),
    ...overrides,
  };
}

describe("AdminCasesPage role gate", () => {
  beforeEach(() => {
    mockedUseAuth.mockReset();
    mockedUseAdminCases.mockReset();
    mockedUseAdminCases.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      isSuccess: false,
      error: null,
    } as unknown as ReturnType<typeof useAdminCases>);
  });

  it("prompts sign-in when there is no user", () => {
    mockedUseAuth.mockReturnValue(authState({ user: null }));

    render(<AdminCasesPage />);

    expect(screen.getByText(/sign in to continue/i)).toBeInTheDocument();
  });

  it("shows an access message and withholds the case list for a signed-in non-admin", () => {
    mockedUseAuth.mockReturnValue(
      authState({ user: { profile: {} } as User, roles: ["seller"] }),
    );

    render(<AdminCasesPage />);

    expect(screen.getByRole("alert")).toHaveTextContent(/only available to admins/i);
    expect(screen.queryByLabelText(/filter by status/i)).not.toBeInTheDocument();
  });

  it("renders the case list for a signed-in admin", () => {
    mockedUseAuth.mockReturnValue(
      authState({ user: { profile: {} } as User, roles: ["admin"] }),
    );

    render(<AdminCasesPage />);

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByLabelText(/filter by status/i)).toBeInTheDocument();
  });
});
