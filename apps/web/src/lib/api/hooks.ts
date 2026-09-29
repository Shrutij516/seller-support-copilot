"use client";

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@copilot/api-client";
import { getApiClient } from "./client";
import { ApiError } from "./errors";

type OrderStatus = components["schemas"]["OrderStatus"];
type CaseStatus = components["schemas"]["CaseStatus"];

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

export function useOrdersInfinite(status: OrderStatus | undefined) {
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
  });
}

export function useOrder(orderId: string | null) {
  return useQuery({
    queryKey: ["order", orderId],
    queryFn: async () => {
      const { data, error } = await getApiClient().GET("/v1/orders/{order_id}", {
        params: { path: { order_id: orderId! } },
      });
      if (error) throw new ApiError(error);
      return data;
    },
    enabled: Boolean(orderId),
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

export function useCases() {
  return useQuery({
    queryKey: ["cases"],
    queryFn: async () => {
      const { data, error } = await getApiClient().GET("/v1/cases");
      if (error) throw new ApiError(error);
      return data;
    },
  });
}

export function useCase(caseId: string | null) {
  return useQuery({
    queryKey: ["case", caseId],
    queryFn: async () => {
      const { data, error } = await getApiClient().GET("/v1/cases/{case_id}", {
        params: { path: { case_id: caseId! } },
      });
      if (error) throw new ApiError(error);
      return data;
    },
    enabled: Boolean(caseId),
  });
}

export function useChatSessions() {
  return useQuery({
    queryKey: ["chat-sessions"],
    queryFn: async () => {
      const { data, error } = await getApiClient().GET("/v1/chat/sessions", {
        params: { query: { limit: 20 } },
      });
      if (error) throw new ApiError(error);
      return data;
    },
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

export function useChatMessages(sessionId: string | null) {
  return useQuery({
    queryKey: ["chat-messages", sessionId],
    queryFn: async () => {
      const { data, error } = await getApiClient().GET("/v1/chat/sessions/{session_id}/messages", {
        params: { path: { session_id: sessionId! }, query: { limit: 50 } },
      });
      if (error) throw new ApiError(error);
      return data;
    },
    enabled: Boolean(sessionId),
  });
}

export function useAdminCases(status: CaseStatus | undefined) {
  return useQuery({
    queryKey: ["admin-cases", status ?? null],
    queryFn: async () => {
      const { data, error } = await getApiClient().GET("/v1/admin/cases", {
        params: { query: { status } },
      });
      if (error) throw new ApiError(error);
      return data;
    },
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
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin-cases"] });
    },
  });
}
