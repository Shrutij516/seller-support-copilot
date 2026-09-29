import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import type { User } from "oidc-client-ts";
import OrdersPage from "./page";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useOrdersInfinite } from "@/lib/api/hooks";

vi.mock("@/lib/auth/AuthProvider", () => ({
  useAuth: vi.fn(),
}));

vi.mock("@/lib/api/hooks", () => ({
  useOrdersInfinite: vi.fn(),
}));

const mockedUseAuth = vi.mocked(useAuth);
const mockedUseOrdersInfinite = vi.mocked(useOrdersInfinite);

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

describe("OrdersPage admin gating", () => {
  beforeEach(() => {
    mockedUseAuth.mockReset();
    mockedUseOrdersInfinite.mockReset();
    mockedUseOrdersInfinite.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      isSuccess: false,
      error: null,
      hasNextPage: false,
      fetchNextPage: vi.fn(),
      isFetchingNextPage: false,
    } as unknown as ReturnType<typeof useOrdersInfinite>);
  });

  it("shows a seller-only notice for an admin instead of the orders table", () => {
    mockedUseAuth.mockReturnValue(
      authState({ user: { profile: {} } as User, roles: ["admin"] }),
    );

    render(<OrdersPage />);

    expect(screen.getByText(/this page is for sellers/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/filter by status/i)).not.toBeInTheDocument();
  });

  it("disables the orders query for an admin so the seller-only endpoint is never called", () => {
    mockedUseAuth.mockReturnValue(
      authState({ user: { profile: {} } as User, roles: ["admin"] }),
    );

    render(<OrdersPage />);

    expect(mockedUseOrdersInfinite).toHaveBeenCalledWith(undefined, { enabled: false });
  });

  it("enables the orders query and shows the table for a seller", () => {
    mockedUseAuth.mockReturnValue(
      authState({ user: { profile: {} } as User, roles: ["seller"] }),
    );

    render(<OrdersPage />);

    expect(mockedUseOrdersInfinite).toHaveBeenCalledWith(undefined, { enabled: true });
    expect(screen.queryByText(/this page is for sellers/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/filter by status/i)).toBeInTheDocument();
  });
});
