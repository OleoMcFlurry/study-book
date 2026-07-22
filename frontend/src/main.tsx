import "./styles.css";

import { ThemeProvider, type ThemeSwitchProps } from "@lobehub/ui";
import React, { useState } from "react";
import ReactDOM from "react-dom/client";

import App from "./App";

function Root() {
  const [themeMode, setThemeMode] =
    useState<ThemeSwitchProps["themeMode"]>("auto");

  return (
    <ThemeProvider appearance={themeMode} enableGlobalStyle>
      <App onThemeSwitch={setThemeMode} themeMode={themeMode} />
    </ThemeProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>
);
