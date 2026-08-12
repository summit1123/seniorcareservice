import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
// CSS를 고치면 반드시 v를 함께 올릴 것 — Cloudflare가 .css URL을 4시간 엣지 캐시하므로
// URL이 같으면 방문자에게 옛 스타일이 그대로 나간다(2026-08-04 대조 표 깨짐의 원인).
import "./styles.css?v=refund-birthyear-20260813b";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
