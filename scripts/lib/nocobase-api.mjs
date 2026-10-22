import { readFileSync } from "node:fs";
export const base = "http://127.0.0.1:13000";
export function localAdmin() {
  const file = new URL("../../.local/secrets/deploy.env", import.meta.url);
  const env = Object.fromEntries(
    readFileSync(file, "utf8")
      .split("\n")
      .filter((l) => l && !l.startsWith("#"))
      .map((l) => {
        const i = l.indexOf("=");
        return [l.slice(0, i), l.slice(i + 1)];
      }),
  );
  return { email: env.INIT_ROOT_EMAIL, password: env.INIT_ROOT_PASSWORD };
}
export async function client(credentials = localAdmin()) {
  const login = await fetch(`${base}/api/auth:signIn`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      email: credentials.email,
      password: credentials.password,
    }),
    signal: AbortSignal.timeout(10000),
  });
  if (!login.ok) throw new Error(`Local login failed: ${login.status}`);
  const token = (await login.json()).data.token;
  return async function request(
    resource,
    action,
    { values, params = {}, method } = {},
  ) {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (Array.isArray(value)) {
        for (const item of value) query.append(key + "[]", String(item));
      } else
        query.set(
          key,
          typeof value === "object" ? JSON.stringify(value) : String(value),
        );
    }
    const response = await fetch(`${base}/api/${resource}:${action}?${query}`, {
      method: method || (values === undefined ? "GET" : "POST"),
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${token}`,
      },
      body: values === undefined ? undefined : JSON.stringify(values),
      signal: AbortSignal.timeout(15000),
    });
    const data = await response.json();
    if (!response.ok)
      throw new Error(
        `${resource}:${action} HTTP ${response.status} ${JSON.stringify(data.errors || []).slice(0, 350)}`,
      );
    return data;
  };
}
