import type { RouteObject } from "react-router";
import { AppLayout } from "./layouts/AppLayout";
import { AdminHomePage, ParentHomePage, SitterHomePage } from "./pages/AreaPages";
import { NotFoundPage, RouteErrorPage } from "./pages/ErrorPages";
import { HomePage } from "./pages/HomePage";

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
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
