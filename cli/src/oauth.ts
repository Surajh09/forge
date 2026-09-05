import { createHash, randomBytes } from "node:crypto";
import { createServer } from "node:http";
import { AddressInfo } from "node:net";

import { save, type StoredCredential } from "./credentials.js";

/**
 * OAuth 2.1 authorization-code + PKCE against Forge, the same flow a coding
 * agent performs. The package registers itself dynamically (RFC 7591), opens
 * the browser to Forge's consent page, and catches the redirect on a loopback
 * server.
 *
 * The package never sees a Clerk secret or the service-role key — only the
 * opaque grant-bound token the user consented to.
 */

const SCOPES = ["context.read", "context.write", "context.supersede", "session.write"];

function pkce(): { verifier: string; challenge: string } {
  const verifier = randomBytes(48).toString("base64url");
  const challenge = createHash("sha256").update(verifier).digest("base64url");
  return { verifier, challenge };
}

/** Loopback server that resolves once the browser is redirected back. */
function awaitRedirect(): Promise<{ port: number; code: Promise<string> }> {
  return new Promise((resolveServer, rejectServer) => {
    let settle: (code: string) => void;
    let fail: (err: Error) => void;
    const code = new Promise<string>((res, rej) => {
      settle = res;
      fail = rej;
    });

    const server = createServer((req, res) => {
      const url = new URL(req.url ?? "/", "http://localhost");
      const err = url.searchParams.get("error");
      const got = url.searchParams.get("code");
      res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
      if (err) {
        res.end(`<h1>Authorization declined</h1><p>${err}. You can close this tab.</p>`);
        fail(new Error(`Authorization declined: ${err}`));
      } else if (got) {
        res.end("<h1>Forge connected</h1><p>You can close this tab and return to the terminal.</p>");
        settle(got);
      } else {
        res.end("<h1>Unexpected response</h1><p>No code was returned.</p>");
        fail(new Error("Authorization server returned no code."));
      }
      setTimeout(() => server.close(), 250);
    });

    server.on("error", rejectServer);
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address() as AddressInfo;
      resolveServer({ port, code });
    });
  });
}

async function openBrowser(url: string): Promise<void> {
  const { spawn } = await import("node:child_process");
  const cmd =
    process.platform === "win32" ? "cmd" : process.platform === "darwin" ? "open" : "xdg-open";
  const args = process.platform === "win32" ? ["/c", "start", "", url] : [url];
  try {
    spawn(cmd, args, { detached: true, stdio: "ignore" }).unref();
  } catch {
    // Headless or locked down: the caller prints the URL as a fallback.
  }
}

export async function login(apiUrl: string): Promise<StoredCredential> {
  const base = apiUrl.replace(/\/$/, "");
  const { port, code } = await awaitRedirect();
  const redirectUri = `http://localhost:${port}/callback`;

  const registration = await fetch(`${base}/register`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      client_name: "Forge CLI",
      redirect_uris: [redirectUri],
      grant_types: ["authorization_code", "refresh_token"],
      response_types: ["code"],
      token_endpoint_auth_method: "none",
      scope: SCOPES.join(" "),
    }),
  });
  if (!registration.ok) {
    throw new Error(`Could not register with Forge at ${base} (${registration.status}). Is the server running?`);
  }
  const client = (await registration.json()) as { client_id: string };

  const { verifier, challenge } = pkce();
  const state = randomBytes(16).toString("base64url");
  const authorizeUrl = new URL(`${base}/authorize`);
  authorizeUrl.search = new URLSearchParams({
    response_type: "code",
    client_id: client.client_id,
    redirect_uri: redirectUri,
    code_challenge: challenge,
    code_challenge_method: "S256",
    scope: SCOPES.join(" "),
    state,
    resource: `${base}/mcp`,
  }).toString();

  process.stderr.write(`Opening your browser to approve Forge access…\n${authorizeUrl}\n\n`);
  await openBrowser(authorizeUrl.toString());

  const authorizationCode = await code;
  const tokenRes = await fetch(`${base}/token`, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      code: authorizationCode,
      redirect_uri: redirectUri,
      client_id: client.client_id,
      code_verifier: verifier,
    }),
  });
  if (!tokenRes.ok) {
    throw new Error(`Token exchange failed (${tokenRes.status}): ${await tokenRes.text()}`);
  }
  const token = (await tokenRes.json()) as {
    access_token: string;
    refresh_token?: string;
    expires_in?: number;
    scope?: string;
  };

  const cred: StoredCredential = {
    client_id: client.client_id,
    access_token: token.access_token,
    refresh_token: token.refresh_token,
    expires_at: token.expires_in ? Math.floor(Date.now() / 1000) + token.expires_in : undefined,
    scopes: token.scope ? token.scope.split(" ") : SCOPES,
  };
  save(base, cred);
  return cred;
}
