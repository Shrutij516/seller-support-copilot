import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import type { User } from "oidc-client-ts";
import { NavShell } from "./NavShell";
import { useAuth } from "@/lib/auth/AuthProvider";

vi.mock("@/lib/auth/AuthProvider", () => ({
  useAuth: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

const mockedUseAuth = vi.mocked(useAuth);

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

describe("NavShell role-aware navigation", () => {
  beforeEach(() => {
    mockedUseAuth.mockReset();
  });

  it("shows the seller links and no Admin link for a signed-in seller", () => {
    mockedUseAuth.mockReturnValue(
      authState({ user: { profile: {} } as User, roles: ["seller"] }),
    );

    render(<NavShell>content</NavShell>);

    const nav = screen.getByRole("navigation", { name: /primary/i });
    expect(screen.getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Orders" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Cases" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Chat" })).toBeInTheDocument();
    expect(nav).not.toHaveTextContent("Admin");
  });

  it("shows only the Admin link for a signed-in admin, hiding seller links", () => {
    mockedUseAuth.mockReturnValue(
      authState({ user: { profile: {} } as User, roles: ["admin"] }),
    );

    render(<NavShell>content</NavShell>);

    expect(screen.getByRole("link", { name: "Admin" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Dashboard" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Orders" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Cases" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Chat" })).not.toBeInTheDocument();
  });

  it("shows the seller links for a signed-out visitor", () => {
    mockedUseAuth.mockReturnValue(authState({ user: null, roles: [] }));

    render(<NavShell>content</NavShell>);

    expect(screen.getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Admin" })).not.toBeInTheDocument();
  });
});
