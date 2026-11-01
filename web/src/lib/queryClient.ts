import { QueryClient } from "@tanstack/react-query";
import { ApiError } from "./api";

export function shouldRetry(failureCount: number, error: unknown): boolean {
  // 4xx answers won't change on retry (bad input, no permission); network and server errors might.
  if (error instanceof ApiError && error.isClientError) return false;
  return failureCount < 2;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: shouldRetry, staleTime: 30_000 },
      mutations: { retry: false },
    },
  });
}
