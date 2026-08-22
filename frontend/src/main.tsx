import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { AuthProvider } from "./auth";
import { WardrobeProvider } from "./wardrobe";
import App from "./App";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <WardrobeProvider>
          <App />
        </WardrobeProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
);
