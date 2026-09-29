import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import AuthCallbackPage from "./page";
import { getUserManager } from "@/lib/auth/userManager";

const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
}));

vi.mock("@/lib/auth/userManager", () => ({
  getUserManager: vi.fn(),
}));

const mockedGetUserManager = vi.mocked(getUserManager);

describe("AuthCallbackPage", () => {
  beforeEach(() => {
    replace.mockReset();
    mockedGetUserManager.mockReset();
  });

  it("redirects to the dashboard on a successful callback", async () => {
    mockedGetUserManager.mockReturnValue({
      signinCallback: vi.fn().mockResolvedValue(undefined),
    } as unknown as ReturnType<typeof getUserManager>);

    render(<AuthCallbackPage />);

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows the failure message and a way back to the dashboard when the callback fails", async () => {
    mockedGetUserManager.mockReturnValue({
      signinCallback: vi.fn().mockRejectedValue(new Error("state mismatch")),
    } as unknown as ReturnType<typeof getUserManager>);

    render(<AuthCallbackPage />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/sign-in failed/i);
    expect(alert).toHaveTextContent(/state mismatch/i);
    expect(screen.getByRole("link", { name: /return to the dashboard/i })).toHaveAttribute(
      "href",
      "/",
    );
    expect(replace).not.toHaveBeenCalled();
  });

  it("falls back to a generic message when the rejection is not an Error", async () => {
    mockedGetUserManager.mockReturnValue({
      signinCallback: vi.fn().mockRejectedValue("not an error instance"),
    } as unknown as ReturnType<typeof getUserManager>);

    render(<AuthCallbackPage />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/please try again/i);
  });
});
