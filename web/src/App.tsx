import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { RouterProvider, createBrowserRouter, type DataRouter } from "react-router";
import { createQueryClient } from "./lib/queryClient";
import { routes } from "./routes";
import { ThemeProvider } from "./theme/ThemeProvider";

type AppProps = {
  // Tests pass a memory router and their own query client.
  router?: DataRouter;
  queryClient?: QueryClient;
};

export default function App({ router, queryClient }: AppProps) {
  const [appRouter] = useState(() => router ?? createBrowserRouter(routes));
  const [client] = useState(() => queryClient ?? createQueryClient());

  return (
    <ThemeProvider>
      <QueryClientProvider client={client}>
        <RouterProvider router={appRouter} />
      </QueryClientProvider>
    </ThemeProvider>
  );
}
