import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider, type InfiniteData } from "@tanstack/react-query";
import type { ReactNode } from "react";
import type { components } from "@copilot/api-client";
import { useUpdateAdminCase } from "./hooks";
import { getApiClient } from "./client";

vi.mock("./client", () => ({
  getApiClient: vi.fn(),
}));

const mockedGetApiClient = vi.mocked(getApiClient);

type AdminCaseResponse = components["schemas"]["AdminCaseResponse"];
type AdminCaseListResponse = components["schemas"]["AdminCaseListResponse"];

function makeCase(overrides: Partial<AdminCaseResponse>): AdminCaseResponse {
  return {
    id: "case-1",
    order_id: null,
    type: "refund_request",
    status: "open",
    description: "test case",
    created_at: new Date().toISOString(),
    seller_display_name: "Acme Corp",
    ...overrides,
  };
}

describe("useUpdateAdminCase cache behavior", () => {
  beforeEach(() => {
    mockedGetApiClient.mockReset();
  });

  it("patches the transitioned case in place, without reordering the cached list, then invalidates", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const caseA = makeCase({ id: "case-a", status: "open" });
    const caseB = makeCase({ id: "case-b", status: "open" });
    const caseC = makeCase({ id: "case-c", status: "in_progress" });

    const initialData: InfiniteData<AdminCaseListResponse> = {
      pages: [{ items: [caseA, caseB, caseC], next_cursor: null }],
      pageParams: [undefined],
    };
    queryClient.setQueryData(["admin-cases", null], initialData);

    const updatedCaseB: AdminCaseResponse = { ...caseB, status: "in_progress" };
    mockedGetApiClient.mockReturnValue({
      PATCH: vi.fn().mockResolvedValue({ data: updatedCaseB, error: undefined }),
    } as unknown as ReturnType<typeof getApiClient>);

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    function wrapper({ children }: { children: ReactNode }) {
      return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
    }

    const { result } = renderHook(() => useUpdateAdminCase(), { wrapper });

    result.current.mutate({ caseId: "case-b", status: "in_progress" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const cached = queryClient.getQueryData<InfiniteData<AdminCaseListResponse>>([
      "admin-cases",
      null,
    ]);
    const items = cached?.pages[0]?.items;

    // Same array position (a, b, c), not re-sorted by the new status: index 1 is still the
    // case that was in position 1, just with its status field patched.
    expect(items?.map((c) => c.id)).toEqual(["case-a", "case-b", "case-c"]);
    expect(items?.[1]?.status).toBe("in_progress");
    // Untouched rows keep their exact object identity/content.
    expect(items?.[0]).toEqual(caseA);
    expect(items?.[2]).toEqual(caseC);

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["admin-cases"] });
  });
});
