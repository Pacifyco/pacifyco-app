import type { RouteObject } from "react-router";
import { RequireRole } from "./auth/RequireRole";
import { config } from "./config";
import { AppLayout } from "./layouts/AppLayout";
import { AdminHomePage, ParentHomePage, SitterHomePage } from "./pages/AreaPages";
import { ComponentsPage } from "./pages/ComponentsPage";
import { ConsentPage } from "./pages/ConsentPage";
import { NotFoundPage, RouteErrorPage } from "./pages/ErrorPages";
import { HomePage } from "./pages/HomePage";
import { JoinPage } from "./pages/JoinPage";
import { ParentTermsPage, PrivacyPolicyPage, SitterTermsPage } from "./pages/LegalPages";
import { AuthCallbackPage, SignInPage } from "./pages/SignInPage";

// One app, three role areas (CLAUDE.md section 3), each open only to its own role.
export const routes: RouteObject[] = [
  {
    element: <AppLayout />,
    errorElement: <RouteErrorPage />,
    children: [
      { index: true, element: <HomePage /> },
      {
        path: "parent",
        element: (
          <RequireRole role="parent">
            <ParentHomePage />
          </RequireRole>
        ),
      },
      {
        path: "parent/consent",
        element: (
          <RequireRole role="parent">
            <ConsentPage />
          </RequireRole>
        ),
      },
      {
        path: "sitter",
        element: (
          <RequireRole role="sitter">
            <SitterHomePage />
          </RequireRole>
        ),
      },
      {
        path: "admin",
        element: (
          <RequireRole role="admin">
            <AdminHomePage />
          </RequireRole>
        ),
      },
      { path: "sign-in", element: <SignInPage /> },
      { path: "auth/callback", element: <AuthCallbackPage /> },
      { path: "join", element: <JoinPage /> },
      { path: "terms/parent", element: <ParentTermsPage /> },
      { path: "terms/sitter", element: <SitterTermsPage /> },
      { path: "privacy", element: <PrivacyPolicyPage /> },
      // Component preview for development and staging; never in production.
      ...(config.environment !== "production" ? [{ path: "dev/components", element: <ComponentsPage /> }] : []),
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
