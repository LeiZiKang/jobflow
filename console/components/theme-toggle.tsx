"use client";

import { useEffect, useState } from "react";

type Theme = "light" | "dark";
const KEY = "jobflow-theme";

function effectiveTheme(): Theme {
  const chosen = document.documentElement.dataset.theme;
  if (chosen === "light" || chosen === "dark") return chosen;
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

/** 一键切换深色 / 浅色。选择存在 localStorage，下次打开沿用。 */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme | null>(null);

  useEffect(() => setTheme(effectiveTheme()), []);

  const flip = () => {
    const next: Theme = effectiveTheme() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    // cookie 给报告页用（报告页禁脚本，由服务端读 cookie 决定主题）。
    document.cookie = `${KEY}=${next}; path=/; max-age=31536000; samesite=lax`;
    try {
      localStorage.setItem(KEY, next);
    } catch {
      // 存不了就只对本次生效。
    }
    setTheme(next);
  };

  const label = theme === "dark" ? "切换到浅色" : "切换到深色";
  return (
    <button type="button" className="icon-btn" onClick={flip} aria-label={label} title={label}>
      <span aria-hidden="true">{theme === "dark" ? "☀" : "☾"}</span>
    </button>
  );
}
