import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import type { User } from "oidc-client-ts";
import AdminCasesPage from "./page";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useAdminCases, useMe } from "@/lib/api/hooks";

vi.mock("@/lib/auth/AuthProvider", () => ({
  useAuth: vi.fn(),
}));

vi.mock("@/lib/api/hooks", () => ({
  useAdminCases: vi.fn(),
  useMe: vi.fn(),
  useUpdateAdminCase: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  })),
}));

const mockedUseAuth = vi.mocked(useAuth);
const mockedUseAdminCases = vi.mocked(useAdminCases);
const mockedUseMe = vi.mocked(useMe);

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
    mockedUseMe.mockReset();
    mockedUseMe.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      isSuccess: false,
      error: null,
    } as unknown as ReturnType<typeof useMe>);
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

  it("greets an admin with no display name by role, not a blank or null", () => {
    mockedUseAuth.mockReturnValue(
      authState({ user: { profile: {} } as User, roles: ["admin"] }),
    );
    mockedUseMe.mockReturnValue({
      data: { seller_id: null, email: null, display_name: null, roles: ["admin"] },
      isLoading: false,
      isError: false,
      isSuccess: true,
      error: null,
    } as unknown as ReturnType<typeof useMe>);

    render(<AdminCasesPage />);

    expect(screen.getByText(/welcome back, admin\./i)).toBeInTheDocument();
  });

  it("greets an admin who is also a seller by their display name", () => {
    mockedUseAuth.mockReturnValue(
      authState({ user: { profile: {} } as User, roles: ["admin"] }),
    );
    mockedUseMe.mockReturnValue({
      data: { seller_id: "s-1", email: "a@example.com", display_name: "Acme Corp", roles: ["admin"] },
      isLoading: false,
      isError: false,
      isSuccess: true,
      error: null,
    } as unknown as ReturnType<typeof useMe>);

    render(<AdminCasesPage />);

    expect(screen.getByText(/welcome back, acme corp\./i)).toBeInTheDocument();
  });
});
