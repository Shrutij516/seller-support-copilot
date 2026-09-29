import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
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

    render(<RefundForm orderId="order-1" ineligibleReason={null} />);
    await user.type(screen.getByLabelText(/reason for refund/i), "too short");
    await user.click(screen.getByRole("button", { name: /request refund/i }));

    expect(screen.getByRole("alert")).toHaveTextContent(/at least 10 characters/i);
    expect(mutate).not.toHaveBeenCalled();
  });

  it("rejects an empty reason", async () => {
    const mutate = vi.fn();
    mockedUseCreateRefundRequest.mockReturnValue(mutationState({ mutate }));
    const user = userEvent.setup();

    render(<RefundForm orderId="order-1" ineligibleReason={null} />);
    await user.click(screen.getByRole("button", { name: /request refund/i }));

    expect(screen.getByRole("alert")).toHaveTextContent(/at least 10 characters/i);
    expect(mutate).not.toHaveBeenCalled();
  });

  it("submits a valid reason", async () => {
    const mutate = vi.fn();
    mockedUseCreateRefundRequest.mockReturnValue(mutationState({ mutate }));
    const user = userEvent.setup();

    render(<RefundForm orderId="order-1" ineligibleReason={null} />);
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

    render(<RefundForm orderId="order-1" ineligibleReason={null} />);

    expect(screen.getByRole("alert")).toHaveTextContent(/conflicts with the current state/i);
  });

  it("shows a confirmation and hides the form once the mutation succeeds", () => {
    mockedUseCreateRefundRequest.mockReturnValue(mutationState({ isSuccess: true }));

    render(<RefundForm orderId="order-1" ineligibleReason={null} />);

    expect(screen.getByRole("status")).toHaveTextContent(/refund request submitted/i);
    expect(screen.queryByLabelText(/reason for refund/i)).not.toBeInTheDocument();
  });
});

describe("RefundForm eligibility", () => {
  beforeEach(() => {
    mockedUseCreateRefundRequest.mockReset();
  });

  it("shows the ineligibility reason up front and disables the fields, instead of hiding the form", () => {
    const mutate = vi.fn();
    mockedUseCreateRefundRequest.mockReturnValue(mutationState({ mutate }));

    render(
      <RefundForm
        orderId="order-1"
        ineligibleReason="This order hasn't been delivered yet, so it isn't eligible for a refund."
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent(/hasn't been delivered yet/i);
    expect(screen.getByLabelText(/reason for refund/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/reason for refund/i)).toBeDisabled();
    expect(screen.getByRole("button", { name: /request refund/i })).toBeDisabled();
  });

  it("does not call mutate on submit when ineligible", async () => {
    const mutate = vi.fn();
    mockedUseCreateRefundRequest.mockReturnValue(mutationState({ mutate }));

    const { container } = render(
      <RefundForm orderId="order-1" ineligibleReason="Outside the refund window." />,
    );
    // The submit button is disabled (browsers block this click), so submit the form directly
    // to also cover the handler's own ineligibleReason guard.
    const form = container.querySelector("form");
    if (form) fireEvent.submit(form);

    expect(mutate).not.toHaveBeenCalled();
  });
});
