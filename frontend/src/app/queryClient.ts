import { QueryClient } from "@tanstack/react-query";

/**
 * Server state defaults.
 *
 * Department-scoped data is never cached longer than it is useful, and failures are
 * retried only once so a permission error is not hammered. Query keys must include the
 * department/scope (see docs/architecture/FRONTEND_ARCHITECTURE.md).
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 0,
    },
  },
});
