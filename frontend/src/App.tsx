import type { ReactElement } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth";
import BottomNav from "./components/BottomNav";
import Login from "./pages/Login";
import Invite from "./pages/Invite";
import AdminLog from "./pages/AdminLog";
import Wardrobe from "./pages/Wardrobe";
import AddItem from "./pages/AddItem";
import ItemDetail from "./pages/ItemDetail";
import Combine from "./pages/Combine";
import Outfits from "./pages/Outfits";
import Settings from "./pages/Settings";

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
      {children}
      <BottomNav />
    </div>
  );
}

export default function App() {
  const { user, loading } = useAuth();

  return (
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
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
