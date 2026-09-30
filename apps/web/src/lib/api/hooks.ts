"use client";

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type InfiniteData,
} from "@tanstack/react-query";
import type { components } from "@copilot/api-client";
import { getApiClient } from "./client";
import { ApiError } from "./errors";

type OrderStatus = components["schemas"]["OrderStatus"];
type CaseStatus = components["schemas"]["CaseStatus"];
type AdminCaseListResponse = components["schemas"]["AdminCaseListResponse"];

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      const { data, error } = await getApiClient().GET("/v1/me");
      if (error) throw new ApiError(error);
      return data;
    },
  });
}

export function useOrdersInfinite(status: OrderStatus | undefined, options?: { enabled?: boolean }) {
  return useInfiniteQuery({
    queryKey: ["orders", status ?? null],
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam }) => {
      const { data, error } = await getApiClient().GET("/v1/orders", {
        params: { query: { status, cursor: pageParam, limit: 20 } },
      });
      if (error) throw new ApiError(error);
      return data;
    },
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: options?.enabled ?? true,
  });
}

export function useOrder(orderId: string | null, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ["order", orderId],
    queryFn: async () => {
      const { data, error } = await getApiClient().GET("/v1/orders/{order_id}", {
        params: { path: { order_id: orderId! } },
      });
      if (error) throw new ApiError(error);
      return data;
    },
    enabled: Boolean(orderId) && (options?.enabled ?? true),
  });
}

export function useCreateRefundRequest(orderId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (reason: string) => {
      const { data, error } = await getApiClient().POST("/v1/orders/{order_id}/refund-requests", {
        params: { path: { order_id: orderId } },
        body: { reason },
      });
      if (error) throw new ApiError(error);
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["orders"] });
      void queryClient.invalidateQueries({ queryKey: ["order", orderId] });
      void queryClient.invalidateQueries({ queryKey: ["cases"] });
    },
  });
}

export function useCases(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ["cases"],
    queryFn: async () => {
      const { data, error } = await getApiClient().GET("/v1/cases");
      if (error) throw new ApiError(error);
      return data;
    },
    enabled: options?.enabled ?? true,
  });
}

export function useCase(caseId: string | null, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ["case", caseId],
    queryFn: async () => {
      const { data, error } = await getApiClient().GET("/v1/cases/{case_id}", {
        params: { path: { case_id: caseId! } },
      });
      if (error) throw new ApiError(error);
      return data;
    },
    enabled: Boolean(caseId) && (options?.enabled ?? true),
  });
}

export function useChatSessions(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ["chat-sessions"],
    queryFn: async () => {
      const { data, error } = await getApiClient().GET("/v1/chat/sessions", {
        params: { query: { limit: 20 } },
      });
      if (error) throw new ApiError(error);
      return data;
    },
    enabled: options?.enabled ?? true,
  });
}

export function useCreateChatSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (title: string) => {
      const { data, error } = await getApiClient().POST("/v1/chat/sessions", { body: { title } });
      if (error) throw new ApiError(error);
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["chat-sessions"] });
    },
  });
}

export function useChatMessages(sessionId: string | null, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ["chat-messages", sessionId],
    queryFn: async () => {
      const { data, error } = await getApiClient().GET("/v1/chat/sessions/{session_id}/messages", {
        params: { path: { session_id: sessionId! }, query: { limit: 50 } },
      });
      if (error) throw new ApiError(error);
      return data;
    },
    enabled: Boolean(sessionId) && (options?.enabled ?? true),
  });
}

export function useAdminCases(status: CaseStatus | undefined) {
  return useInfiniteQuery({
    queryKey: ["admin-cases", status ?? null],
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam }) => {
      const { data, error } = await getApiClient().GET("/v1/admin/cases", {
        params: { query: { status, cursor: pageParam, limit: 20 } },
      });
      if (error) throw new ApiError(error);
      return data;
    },
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useUpdateAdminCase() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ caseId, status }: { caseId: string; status: CaseStatus }) => {
      const { data, error } = await getApiClient().PATCH("/v1/admin/cases/{case_id}", {
        params: { path: { case_id: caseId } },
        body: { status },
      });
      if (error) throw new ApiError(error);
      return data;
    },
    onSuccess: (updatedCase) => {
      // Patch the case in place, in whatever page/position it's already cached at, instead
      // of invalidating alone: an invalidate-triggered refetch re-sorts the whole list by
      // the new canonical order (status changed), which would visibly jump or remove the row
      // out from under the cursor right as the admin clicks it. The in-place update keeps
      // today's position stable; the invalidate below still runs, so the list catches up to
      // the real server order (and drops rows that no longer match an active status filter)
      // the next time it's refetched, not synchronously with this click.
      queryClient.setQueriesData<InfiniteData<AdminCaseListResponse>>(
        { queryKey: ["admin-cases"] },
        (old) => {
          if (!old) return old;
          return {
            ...old,
            pages: old.pages.map((page) => ({
              ...page,
              items: page.items.map((item) => (item.id === updatedCase.id ? updatedCase : item)),
            })),
          };
        },
      );
      void queryClient.invalidateQueries({ queryKey: ["admin-cases"] });
    },
  });
}
