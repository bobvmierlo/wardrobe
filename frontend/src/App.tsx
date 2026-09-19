import { Suspense, lazy, type ReactElement } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth";
import BottomNav from "./components/BottomNav";
import OfflineBar from "./components/OfflineBar";
import Login from "./pages/Login";
import Wardrobe from "./pages/Wardrobe";

// The kast is where everyone lands, so it ships in the first bundle together
// with the login screen. The rest is fetched when it is first opened — which
// keeps the admin screens (Instellingen, Logboek) off the critical path for
// the people who never open them.
const Invite = lazy(() => import("./pages/Invite"));
const Today = lazy(() => import("./pages/Today"));
const Looks = lazy(() => import("./pages/Looks"));
const Week = lazy(() => import("./pages/Week"));
const Discover = lazy(() => import("./pages/Discover"));
const Insights = lazy(() => import("./pages/Insights"));
const Trips = lazy(() => import("./pages/Trips"));
const StyleDna = lazy(() => import("./pages/StyleDna"));
const StyleGuide = lazy(() => import("./pages/StyleGuide"));
const More = lazy(() => import("./pages/More"));
const AdminLog = lazy(() => import("./pages/AdminLog"));
const AddItem = lazy(() => import("./pages/AddItem"));
const ItemDetail = lazy(() => import("./pages/ItemDetail"));
const Combine = lazy(() => import("./pages/Combine"));
const Outfits = lazy(() => import("./pages/Outfits"));
const Settings = lazy(() => import("./pages/Settings"));

function Protected({ children }: { children: ReactElement }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <div className="spinner" />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return children;
}

function Shell({ children }: { children: ReactElement }) {
  return (
    <div className="app">
      <OfflineBar />
      {children}
      <BottomNav />
    </div>
  );
}

export default function App() {
  const { user, loading } = useAuth();

  return (
    <Suspense fallback={<div className="spinner" />}>
      <Routes>
        <Route
          path="/login"
          element={loading ? <div className="spinner" /> : user ? <Navigate to="/" replace /> : <Login />}
        />
        {/* Reachable without a login: the token in the URL is the credential,
            and a newcomer registers here (registration is closed elsewhere). */}
        <Route path="/invite/:token" element={<Invite />} />
        <Route
          path="/"
          element={
            <Protected>
              <Shell>
                <Wardrobe />
              </Shell>
            </Protected>
          }
        />
        <Route
          path="/add"
          element={
            <Protected>
              <AddItem />
            </Protected>
          }
        />
        <Route
          path="/item/:id"
          element={
            <Protected>
              <ItemDetail />
            </Protected>
          }
        />
        <Route
          path="/combine"
          element={
            <Protected>
              <Shell>
                <Combine />
              </Shell>
            </Protected>
          }
        />
        <Route
          path="/outfits"
          element={
            <Protected>
              <Shell>
                <Outfits />
              </Shell>
            </Protected>
          }
        />
        <Route
          path="/settings"
          element={
            <Protected>
              <Shell>
                <Settings />
              </Shell>
            </Protected>
          }
        />
        <Route
          path="/logboek"
          element={
            <Protected>
              <AdminLog />
            </Protected>
          }
        />
        <Route
          path="/vandaag"
          element={
            <Protected>
              <Shell>
                <Today />
              </Shell>
            </Protected>
          }
        />
        <Route
          path="/looks"
          element={
            <Protected>
              <Shell>
                <Looks />
              </Shell>
            </Protected>
          }
        />
        <Route
          path="/week"
          element={
            <Protected>
              <Shell>
                <Week />
              </Shell>
            </Protected>
          }
        />
        <Route
          path="/discover"
          element={
            <Protected>
              <Shell>
                <Discover />
              </Shell>
            </Protected>
          }
        />
        <Route
          path="/insights"
          element={
            <Protected>
              <Shell>
                <Insights />
              </Shell>
            </Protected>
          }
        />
        <Route
          path="/trips"
          element={
            <Protected>
              <Shell>
                <Trips />
              </Shell>
            </Protected>
          }
        />
        <Route
          path="/stijl-dna"
          element={
            <Protected>
              <Shell>
                <StyleDna />
              </Shell>
            </Protected>
          }
        />
        <Route
          path="/stijlgids"
          element={
            <Protected>
              <Shell>
                <StyleGuide />
              </Shell>
            </Protected>
          }
        />
        <Route
          path="/meer"
          element={
            <Protected>
              <Shell>
                <More />
              </Shell>
            </Protected>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
