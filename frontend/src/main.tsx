import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { AuthProvider } from "./auth";
import { ConfirmProvider } from "./confirm";
import { ThemeProvider } from "./theme";
import { WardrobeProvider } from "./wardrobe";
import App from "./App";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        {/* Inside AuthProvider: the palette is the signed-in person's own
            choice, so it cannot be fetched before we know who that is. */}
        <ThemeProvider>
          <WardrobeProvider>
            <ConfirmProvider>
              <App />
            </ConfirmProvider>
          </WardrobeProvider>
        </ThemeProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
);
