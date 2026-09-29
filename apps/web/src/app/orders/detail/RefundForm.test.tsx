import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RefundForm } from "./page";
import { useCreateRefundRequest } from "@/lib/api/hooks";

vi.mock("@/lib/api/hooks", () => ({
  useCreateRefundRequest: vi.fn(),
}));

const mockedUseCreateRefundRequest = vi.mocked(useCreateRefundRequest);

function mutationState(overrides: Partial<ReturnType<typeof useCreateRefundRequest>> = {}) {
  return {
    mutate: vi.fn(),
    isPending: false,
    isSuccess: false,
    isError: false,
    error: null,
    ...overrides,
  } as unknown as ReturnType<typeof useCreateRefundRequest>;
}

describe("RefundForm validation", () => {
  beforeEach(() => {
    mockedUseCreateRefundRequest.mockReset();
  });

  it("rejects a reason shorter than 10 characters and does not submit", async () => {
    const mutate = vi.fn();
    mockedUseCreateRefundRequest.mockReturnValue(mutationState({ mutate }));
    const user = userEvent.setup();

    render(<RefundForm orderId="order-1" />);
    await user.type(screen.getByLabelText(/reason for refund/i), "too short");
    await user.click(screen.getByRole("button", { name: /request refund/i }));

    expect(screen.getByRole("alert")).toHaveTextContent(/at least 10 characters/i);
    expect(mutate).not.toHaveBeenCalled();
  });

  it("rejects an empty reason", async () => {
    const mutate = vi.fn();
    mockedUseCreateRefundRequest.mockReturnValue(mutationState({ mutate }));
    const user = userEvent.setup();

    render(<RefundForm orderId="order-1" />);
    await user.click(screen.getByRole("button", { name: /request refund/i }));

    expect(screen.getByRole("alert")).toHaveTextContent(/at least 10 characters/i);
    expect(mutate).not.toHaveBeenCalled();
  });

  it("submits a valid reason", async () => {
    const mutate = vi.fn();
    mockedUseCreateRefundRequest.mockReturnValue(mutationState({ mutate }));
    const user = userEvent.setup();

    render(<RefundForm orderId="order-1" />);
    await user.type(
      screen.getByLabelText(/reason for refund/i),
      "The item arrived broken and unusable.",
    );
    await user.click(screen.getByRole("button", { name: /request refund/i }));

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(mutate).toHaveBeenCalledWith("The item arrived broken and unusable.");
  });

  it("shows the server error message when the mutation fails", () => {
    mockedUseCreateRefundRequest.mockReturnValue(
      mutationState({ isError: true, error: new Error("This conflicts with the current state.") }),
    );

    render(<RefundForm orderId="order-1" />);

    expect(screen.getByRole("alert")).toHaveTextContent(/conflicts with the current state/i);
  });

  it("shows a confirmation and hides the form once the mutation succeeds", () => {
    mockedUseCreateRefundRequest.mockReturnValue(mutationState({ isSuccess: true }));

    render(<RefundForm orderId="order-1" />);

    expect(screen.getByRole("status")).toHaveTextContent(/refund request submitted/i);
    expect(screen.queryByLabelText(/reason for refund/i)).not.toBeInTheDocument();
  });
});
