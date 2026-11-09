// Stand-ins for the outside services the app uses, for end-to-end tests only (never deployed):
// - Supabase Auth: the public signing keys (JWKS) the API checks tokens against, plus a test-only
//   endpoint that signs a token for any user, so tests can sign in without email codes.
// - Supabase Storage: the few endpoints app/services/storage.py and the browser upload use, in memory.
// - OpenStreetMap Nominatim: every address is in Koramangala.
//
// Run: node e2e/fake-services.mjs   (port 54321, or E2E_FAKE_PORT)

import { createSign, generateKeyPairSync, randomUUID } from "node:crypto";
import { createServer } from "node:http";

const PORT = Number(process.env.E2E_FAKE_PORT || 54321);
const BASE = `http://localhost:${PORT}`;
const KID = "e2e-key";

const { privateKey, publicKey } = generateKeyPairSync("ec", { namedCurve: "P-256" });
const jwk = { ...publicKey.export({ format: "jwk" }), kid: KID, alg: "ES256", use: "sig" };

const base64url = (data) => Buffer.from(data).toString("base64url");

function signToken({ sub, email }) {
  const now = Math.floor(Date.now() / 1000);
  const header = { alg: "ES256", typ: "JWT", kid: KID };
  const claims = {
    sub,
    email,
    aud: "authenticated",
    role: "authenticated",
    iss: `${BASE}/auth/v1`,
    iat: now,
    exp: now + 24 * 60 * 60,
  };
  const input = `${base64url(JSON.stringify(header))}.${base64url(JSON.stringify(claims))}`;
  const signature = createSign("SHA256").update(input).sign({ key: privateKey, dsaEncoding: "ieee-p1363" });
  return `${input}.${base64url(signature)}`;
}

const files = new Map(); // storage path -> { body, type }

function contentType(body) {
  if (body.subarray(0, 4).toString("latin1") === "%PDF") return "application/pdf";
  if (body[0] === 0xff && body[1] === 0xd8) return "image/jpeg";
  if (body[0] === 0x89 && body.subarray(1, 4).toString("latin1") === "PNG") return "image/png";
  return "application/octet-stream";
}

function send(res, status, body, type = "application/json") {
  res.writeHead(status, {
    "Content-Type": type,
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
  });
  res.end(type === "application/json" ? JSON.stringify(body) : body);
}

async function readBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  return Buffer.concat(chunks);
}

createServer(async (req, res) => {
  const url = new URL(req.url, BASE);
  const path = decodeURIComponent(url.pathname);
  if (req.method === "OPTIONS") return send(res, 204, "", "text/plain");

  // ---- auth ----
  if (path === "/auth/v1/.well-known/jwks.json") return send(res, 200, { keys: [jwk] });
  if (path === "/e2e/token") {
    return send(res, 200, { token: signToken({ sub: url.searchParams.get("sub"), email: url.searchParams.get("email") }) });
  }
  if (path.startsWith("/auth/v1/logout")) return send(res, 204, "", "text/plain");

  // ---- storage (bucket "documents") ----
  const uploadSign = path.match(/^\/storage\/v1\/object\/upload\/sign\/documents\/(.+)$/);
  if (uploadSign && req.method === "POST") return send(res, 200, { token: randomUUID() });
  if (uploadSign && req.method === "PUT") {
    const body = await readBody(req);
    files.set(uploadSign[1], { body, type: contentType(body) });
    return send(res, 200, { Key: uploadSign[1] });
  }
  const viewSign = path.match(/^\/storage\/v1\/object\/sign\/documents\/(.+)$/);
  if (viewSign && req.method === "POST") {
    return send(res, 200, { signedURL: `/object/sign/documents/${viewSign[1]}?token=${randomUUID()}` });
  }
  if (viewSign && req.method === "GET") {
    const file = files.get(viewSign[1]);
    return file ? send(res, 200, file.body, file.type) : send(res, 404, { error: "not_found" });
  }
  const object = path.match(/^\/storage\/v1\/object\/documents\/(.+)$/);
  if (object && req.method === "GET") {
    const file = files.get(object[1]);
    return file ? send(res, 200, file.body, file.type) : send(res, 404, { error: "not_found" });
  }
  if (path === "/storage/v1/object/documents" && req.method === "DELETE") {
    const { prefixes = [] } = JSON.parse((await readBody(req)).toString() || "{}");
    for (const prefix of prefixes) files.delete(prefix);
    return send(res, 200, []);
  }

  // ---- geocoding ----
  if (path === "/nominatim/search") return send(res, 200, [{ lat: "12.935200", lon: "77.624500" }]);

  return send(res, 404, { error: `no fake for ${req.method} ${path}` });
}).listen(PORT, () => console.log(`fake services on ${BASE}`));
