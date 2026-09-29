import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import type { User } from "oidc-client-ts";
import DashboardPage from "./page";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useCases, useMe, useOrdersInfinite } from "@/lib/api/hooks";

const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
}));

vi.mock("@/lib/auth/AuthProvider", () => ({
  useAuth: vi.fn(),
}));

vi.mock("@/lib/api/hooks", () => ({
  useMe: vi.fn(),
  useOrdersInfinite: vi.fn(),
  useCases: vi.fn(),
}));

const mockedUseAuth = vi.mocked(useAuth);
const mockedUseMe = vi.mocked(useMe);
const mockedUseOrdersInfinite = vi.mocked(useOrdersInfinite);
const mockedUseCases = vi.mocked(useCases);

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

const emptyQuery = {
  data: undefined,
  isLoading: false,
  isError: false,
  isSuccess: false,
  error: null,
} as const;

describe("DashboardPage admin redirect", () => {
  beforeEach(() => {
    replace.mockReset();
    mockedUseAuth.mockReset();
    mockedUseMe.mockReturnValue(emptyQuery as unknown as ReturnType<typeof useMe>);
    mockedUseOrdersInfinite.mockReturnValue({
      ...emptyQuery,
      hasNextPage: false,
    } as unknown as ReturnType<typeof useOrdersInfinite>);
    mockedUseCases.mockReturnValue(emptyQuery as unknown as ReturnType<typeof useCases>);
  });

  it("redirects an admin to /admin/cases instead of showing the seller dashboard", async () => {
    mockedUseAuth.mockReturnValue(
      authState({ user: { profile: {} } as User, roles: ["admin"] }),
    );

    render(<DashboardPage />);

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/admin/cases"));
    expect(screen.queryByText(/recent orders/i)).not.toBeInTheDocument();
    expect(mockedUseOrdersInfinite).not.toHaveBeenCalled();
    expect(mockedUseCases).not.toHaveBeenCalled();
  });

  it("shows the seller dashboard and does not redirect for a signed-in seller", () => {
    mockedUseAuth.mockReturnValue(
      authState({ user: { profile: {} } as User, roles: ["seller"] }),
    );

    render(<DashboardPage />);

    expect(replace).not.toHaveBeenCalled();
    expect(screen.getByText(/recent orders/i)).toBeInTheDocument();
  });

  it("shows the sign-in prompt when signed out, without redirecting", () => {
    mockedUseAuth.mockReturnValue(authState({ user: null, roles: [] }));

    render(<DashboardPage />);

    expect(replace).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
  });
});
