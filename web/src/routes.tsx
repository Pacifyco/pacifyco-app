import { Navigate, type RouteObject } from "react-router";
import { RequireRole } from "./auth/RequireRole";
import { FamilyReviewPage } from "./pages/admin/FamilyReviewPage";
import { SitterReviewPage } from "./pages/admin/SitterReviewPage";
import { VerificationQueuePage } from "./pages/admin/VerificationQueuePage";
import { config } from "./config";
import { AppLayout } from "./layouts/AppLayout";
import { AdminHomePage, SitterHomePage } from "./pages/AreaPages";
import { AvailabilityPage } from "./pages/AvailabilityPage";
import { ComponentsPage } from "./pages/ComponentsPage";
import { ConsentPage } from "./pages/ConsentPage";
import { DetailsPage } from "./pages/DetailsPage";
import { NotFoundPage, RouteErrorPage } from "./pages/ErrorPages";
import { FamilyPage } from "./pages/FamilyPage";
import { FindSittersPage } from "./pages/FindSittersPage";
import { HomePage } from "./pages/HomePage";
import { JoinPage } from "./pages/JoinPage";
import { ParentTermsPage, PrivacyPolicyPage, SitterTermsPage } from "./pages/LegalPages";
import { ProfilePage } from "./pages/ProfilePage";
import { PsychTestPage } from "./pages/PsychTestPage";
import { AuthCallbackPage, SIGN_IN_PATH } from "./pages/SignInPage";
import { SitterApplicationPage } from "./pages/SitterApplicationPage";
import { SitterConsentPage } from "./pages/SitterConsentPage";
import { SitterProfilePage } from "./pages/SitterProfilePage";

// One app, three role areas (CLAUDE.md section 3), each open only to its own role.
export const routes: RouteObject[] = [
  {
    element: <AppLayout />,
    errorElement: <RouteErrorPage />,
    children: [
      { index: true, element: <HomePage /> },
      // Parents have no separate home: they go straight to Find a sitter.
      {
        path: "parent",
        element: (
          <RequireRole role="parent">
            <Navigate to="/parent/sitters" replace />
          </RequireRole>
        ),
      },
      // "Your profile": the finish-your-profile checklist, opened from the header's profile button.
      ...(["parent", "sitter"] as const).map((role) => ({
        path: `${role}/profile`,
        element: (
          <RequireRole role={role}>
            <ProfilePage role={role} />
          </RequireRole>
        ),
      })),
      // "Your details" (name, mobile, pin code, address): asked for after sign-up (CLAUDE.md 6.13).
      ...(["parent", "sitter"] as const).map((role) => ({
        path: `${role}/details`,
        element: (
          <RequireRole role={role}>
            <DetailsPage />
          </RequireRole>
        ),
      })),
      // The marketplace (phase 5): parents find sitters; sitters set their free times.
      ...(
        [
          ["parent/sitters", "parent", <FindSittersPage />],
          ["parent/sitters/:sitterId", "parent", <SitterProfilePage />],
          ["sitter/availability", "sitter", <AvailabilityPage />],
        ] as const
      ).map(([path, role, page]) => ({ path, element: <RequireRole role={role}>{page}</RequireRole> })),
      {
        path: "parent/consent",
        element: (
          <RequireRole role="parent">
            <ConsentPage />
          </RequireRole>
        ),
      },
      {
        path: "parent/family",
        element: (
          <RequireRole role="parent">
            <FamilyPage />
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
        path: "sitter/application",
        element: (
          <RequireRole role="sitter">
            <SitterApplicationPage />
          </RequireRole>
        ),
      },
      {
        path: "sitter/consent",
        element: (
          <RequireRole role="sitter">
            <SitterConsentPage />
          </RequireRole>
        ),
      },
      {
        path: "sitter/psych-test",
        element: (
          <RequireRole role="sitter">
            <PsychTestPage />
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
      ...(
        [
          ["admin/verifications", <VerificationQueuePage />],
          ["admin/sitters/:sitterId", <SitterReviewPage />],
          ["admin/parents/:parentId", <FamilyReviewPage />],
        ] as const
      ).map(([path, page]) => ({ path, element: <RequireRole role="admin">{page}</RequireRole> })),
      // Signing in is a box on the home page; old /sign-in links land there with it open.
      { path: "sign-in", element: <Navigate to={SIGN_IN_PATH} replace /> },
      { path: "auth/callback", element: <AuthCallbackPage /> },
      { path: "join", element: <JoinPage /> },
      { path: "terms/parent", element: <ParentTermsPage /> },
      { path: "terms/sitter", element: <SitterTermsPage /> },
      { path: "privacy", element: <PrivacyPolicyPage /> },
      // Component preview for local development and staging only, not linked from anywhere.
      ...(["local", "staging"].includes(config.environment)
        ? [{ path: "dev/components", element: <ComponentsPage /> }]
        : []),
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
