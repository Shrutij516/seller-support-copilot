// Static export has no server, so the CSP is a <meta> tag baked into each HTML file at build
// time (see src/app/csp.ts). Next itself emits a couple of inline <script> tags per page (the
// self.__next_f.push(...) RSC hydration payload) that a plain `script-src 'self'` blocks,
// which breaks hydration entirely. Since these files are static (same bytes for every visitor,
// not per-request), we can hash their exact, already-final content here and let the CSP allow
// only those specific hashes, instead of the much weaker 'unsafe-inline'.
import { createHash } from "node:crypto";
import { readdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const OUT_DIR = path.resolve(import.meta.dirname, "..", "out");

async function findHtmlFiles(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await findHtmlFiles(full)));
    } else if (entry.name.endsWith(".html")) {
      files.push(full);
    }
  }
  return files;
}

function sha256Base64(text) {
  return createHash("sha256").update(text, "utf8").digest("base64");
}

function inlineScriptHashes(html) {
  const hashes = new Set();
  const scriptRe = /<script([^>]*)>([\s\S]*?)<\/script>/g;
  let match;
  while ((match = scriptRe.exec(html))) {
    const [, attrs, content] = match;
    if (/\bsrc=/.test(attrs)) continue; // external script, governed by script-src 'self'
    if (!content) continue;
    hashes.add(`'sha256-${sha256Base64(content)}'`);
  }
  return hashes;
}

async function patchFile(file) {
  const html = await readFile(file, "utf8");
  const hashes = inlineScriptHashes(html);
  if (hashes.size === 0) return false;

  const cspMetaRe = /(<meta http-equiv="Content-Security-Policy" content=")([^"]*)("\/?>)/;
  const metaMatch = html.match(cspMetaRe);
  if (!metaMatch) return false;

  const scriptSrcRe = /(script-src &#x27;self&#x27;)/;
  if (!scriptSrcRe.test(metaMatch[2])) {
    throw new Error(`${file}: CSP meta tag has no "script-src 'self'" to extend`);
  }

  const addition = [...hashes].map((h) => ` &#x27;${h.slice(1, -1)}&#x27;`).join("");
  const patchedContent = metaMatch[2].replace(scriptSrcRe, `$1${addition}`);
  const patchedHtml =
    html.slice(0, metaMatch.index) +
    metaMatch[1] +
    patchedContent +
    metaMatch[3] +
    html.slice(metaMatch.index + metaMatch[0].length);

  await writeFile(file, patchedHtml, "utf8");
  return true;
}

const files = await findHtmlFiles(OUT_DIR);
let patched = 0;
for (const file of files) {
  if (await patchFile(file)) patched += 1;
}
console.log(`Injected inline-script CSP hashes into ${patched}/${files.length} HTML files.`);
