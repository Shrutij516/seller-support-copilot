import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { User } from "oidc-client-ts";
import AdminCasesPage from "./page";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useAdminCases, useMe, useUpdateAdminCase } from "@/lib/api/hooks";

vi.mock("@/lib/auth/AuthProvider", () => ({
  useAuth: vi.fn(),
}));

vi.mock("@/lib/api/hooks", () => ({
  useAdminCases: vi.fn(),
  useMe: vi.fn(),
  useUpdateAdminCase: vi.fn(),
}));

const mockedUseAuth = vi.mocked(useAuth);
const mockedUseAdminCases = vi.mocked(useAdminCases);
const mockedUseMe = vi.mocked(useMe);
const mockedUseUpdateAdminCase = vi.mocked(useUpdateAdminCase);

function updateMutationState(overrides: Partial<ReturnType<typeof useUpdateAdminCase>> = {}) {
  return {
    mutate: vi.fn(),
    variables: undefined,
    isPending: false,
    isSuccess: false,
    isError: false,
    error: null,
    ...overrides,
  } as unknown as ReturnType<typeof useUpdateAdminCase>;
}

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
      hasNextPage: false,
      fetchNextPage: vi.fn(),
      isFetchingNextPage: false,
    } as unknown as ReturnType<typeof useAdminCases>);
    mockedUseMe.mockReset();
    mockedUseMe.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      isSuccess: false,
      error: null,
    } as unknown as ReturnType<typeof useMe>);
    mockedUseUpdateAdminCase.mockReset();
    mockedUseUpdateAdminCase.mockReturnValue(updateMutationState());
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

function adminAuthState(): ReturnType<typeof useAuth> {
  return authState({ user: { profile: {} } as User, roles: ["admin"] });
}

const openCase = {
  id: "case-open-1",
  order_id: "order-1",
  type: "refund_request",
  status: "open",
  description: "Item arrived damaged",
  created_at: new Date().toISOString(),
  seller_display_name: "Acme Corp",
};

describe("AdminCasesPage case rows", () => {
  beforeEach(() => {
    mockedUseAuth.mockReset();
    mockedUseAuth.mockReturnValue(adminAuthState());
    mockedUseMe.mockReset();
    mockedUseMe.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      isSuccess: false,
      error: null,
    } as unknown as ReturnType<typeof useMe>);
    mockedUseAdminCases.mockReset();
    mockedUseUpdateAdminCase.mockReset();
  });

  it("shows the seller display name and a link to the order", () => {
    mockedUseAdminCases.mockReturnValue({
      data: { pages: [{ items: [openCase], next_cursor: null }] },
      isLoading: false,
      isError: false,
      isSuccess: true,
      error: null,
      hasNextPage: false,
      fetchNextPage: vi.fn(),
      isFetchingNextPage: false,
    } as unknown as ReturnType<typeof useAdminCases>);
    mockedUseUpdateAdminCase.mockReturnValue(updateMutationState());

    render(<AdminCasesPage />);

    expect(screen.getByText(/acme corp/i)).toBeInTheDocument();
    const orderLink = screen.getByRole("link", { name: /view order/i });
    expect(orderLink).toHaveAttribute("href", "/orders/detail?id=order-1");
  });

  it("shows a confirmation in an aria-live region after a successful transition, without hiding the row", async () => {
    mockedUseAdminCases.mockReturnValue({
      data: { pages: [{ items: [openCase], next_cursor: null }] },
      isLoading: false,
      isError: false,
      isSuccess: true,
      error: null,
      hasNextPage: false,
      fetchNextPage: vi.fn(),
      isFetchingNextPage: false,
    } as unknown as ReturnType<typeof useAdminCases>);
    const mutate = vi.fn();
    mockedUseUpdateAdminCase.mockReturnValue(
      updateMutationState({
        mutate,
        isSuccess: true,
        variables: { caseId: "case-open-1", status: "in_progress" },
      }),
    );

    render(<AdminCasesPage />);

    expect(screen.getByText(/item arrived damaged/i)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/updated to in progress/i);
  });

  it("clicking the transition button mutates to the next allowed status", async () => {
    mockedUseAdminCases.mockReturnValue({
      data: { pages: [{ items: [openCase], next_cursor: null }] },
      isLoading: false,
      isError: false,
      isSuccess: true,
      error: null,
      hasNextPage: false,
      fetchNextPage: vi.fn(),
      isFetchingNextPage: false,
    } as unknown as ReturnType<typeof useAdminCases>);
    const mutate = vi.fn();
    mockedUseUpdateAdminCase.mockReturnValue(updateMutationState({ mutate }));
    const user = userEvent.setup();

    render(<AdminCasesPage />);

    await user.click(screen.getByRole("button", { name: /mark in progress/i }));

    expect(mutate).toHaveBeenCalledWith({ caseId: "case-open-1", status: "in_progress" });
  });
});
