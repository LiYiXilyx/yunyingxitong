import { readFileSync } from "node:fs";
export const base = process.env.NOCOBASE_TEST_URL || "http://127.0.0.1:13000";
export async function login(email?: string, password?: string) {
  const env = Object.fromEntries(
    readFileSync(
      new URL("../../.local/secrets/deploy.env", import.meta.url),
      "utf8",
    )
      .split("\n")
      .filter((l) => l && !l.startsWith("#"))
      .map((l) => {
        const i = l.indexOf("=");
        return [l.slice(0, i), l.slice(i + 1)];
      }),
  );
  const r = await api("auth:signIn", undefined, {
    email: email || env.INIT_ROOT_EMAIL,
    password: password || env.INIT_ROOT_PASSWORD,
  });
  if (r.status !== 200) throw Error("test login failed");
  return (await r.json()).data.token;
}
export function api(path: string, token?: string, body?: unknown) {
  return fetch(`${base}/api/${path}`, {
    method: body ? "POST" : "GET",
    headers: {
      "content-type": "application/json",
      ...(token ? { authorization: `Bearer ${token}` } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
}
export function accounts() {
  return JSON.parse(
    readFileSync(
      new URL("../../.local/secrets/t03-accounts.json", import.meta.url),
      "utf8",
    ),
  );
}
export async function roleToken(role: string) {
  const account = accounts()[role];
  return login(account.email, account.password);
}
