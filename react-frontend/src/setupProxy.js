const { createProxyMiddleware } = require("http-proxy-middleware");

/**
 * Dev-only: browser calls same origin `/api/*` → FastAPI on DINEBOT_PROXY_TARGET.
 * Injects X-API-Key from env (never expose the key in client bundle).
 */
module.exports = function (app) {
  const target = process.env.DINEBOT_PROXY_TARGET || "http://127.0.0.1:8000";
  const apiKey = process.env.DINEBOT_PROXY_API_KEY || "";

  app.use(
    "/api",
    createProxyMiddleware({
      target,
      changeOrigin: true,
      pathRewrite: { "^/api": "" },
      onProxyReq(proxyReq) {
        if (apiKey) {
          proxyReq.setHeader("X-API-Key", apiKey);
        }
      },
    })
  );
};
