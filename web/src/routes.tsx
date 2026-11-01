import type { RouteObject } from "react-router";
import { config } from "./config";
import { AppLayout } from "./layouts/AppLayout";
import { AdminHomePage, ParentHomePage, SitterHomePage } from "./pages/AreaPages";
import { ComponentsPage } from "./pages/ComponentsPage";
import { NotFoundPage, RouteErrorPage } from "./pages/ErrorPages";
import { HomePage } from "./pages/HomePage";
import { AuthCallbackPage, SignInPage } from "./pages/SignInPage";

// One app, three role areas (CLAUDE.md section 3). Role gating is added in phase 2.
export const routes: RouteObject[] = [
  {
    element: <AppLayout />,
    errorElement: <RouteErrorPage />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "parent", element: <ParentHomePage /> },
      { path: "sitter", element: <SitterHomePage /> },
      { path: "admin", element: <AdminHomePage /> },
      { path: "sign-in", element: <SignInPage /> },
      { path: "auth/callback", element: <AuthCallbackPage /> },
      // Component preview for development and staging; never in production.
      ...(config.environment !== "production" ? [{ path: "dev/components", element: <ComponentsPage /> }] : []),
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
