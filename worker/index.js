const NOTION_VERSION = "2026-03-11";
const CURRENT_TITLE = "牛牛預算同步｜current";

function json(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}

function authorized(request, env) {
  const supplied = request.headers.get("x-sync-key") || "";
  return supplied && supplied === env.SYNC_ACCESS_KEY;
}

async function notion(env, method, path, payload) {
  const response = await fetch(`https://api.notion.com/v1${path}`, {
    method,
    headers: {
      authorization: `Bearer ${env.NOTION_API_TOKEN}`,
      "notion-version": NOTION_VERSION,
      "content-type": "application/json",
    },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.message || `Notion API ${response.status}`);
  return result;
}

async function children(env, blockId) {
  const output = [];
  let cursor = "";
  do {
    const query = new URLSearchParams({ page_size: "100" });
    if (cursor) query.set("start_cursor", cursor);
    const result = await notion(env, "GET", `/blocks/${blockId}/children?${query}`);
    output.push(...result.results);
    cursor = result.has_more ? result.next_cursor : "";
  } while (cursor);
  return output;
}

async function findCurrentPage(env) {
  const blocks = await children(env, env.NOTION_PARENT_PAGE_ID);
  return blocks.find((block) => block.type === "child_page" && block.child_page?.title === CURRENT_TITLE);
}

function richText(text) {
  const parts = [];
  for (let index = 0; index < text.length; index += 1800) {
    parts.push({ type: "text", text: { content: text.slice(index, index + 1800) } });
  }
  if (parts.length > 100) throw new Error("同步資料超過 Notion 單頁容量，請先匯出備份並整理舊資料");
  return parts;
}

async function readCurrent(env) {
  const page = await findCurrentPage(env);
  if (!page) {
    const parentBlocks = await children(env, env.NOTION_PARENT_PAGE_ID);
    const backups = parentBlocks.filter((block) => block.type === "child_page" && block.child_page?.title?.startsWith("牛牛預算備份｜"));
    if (!backups.length) return null;
    const latest = backups.sort((a, b) => b.child_page.title.localeCompare(a.child_page.title))[0];
    const backupBlocks = await children(env, latest.id);
    const backupText = backupBlocks.filter((block) => block.type === "code").flatMap((block) => block.code?.rich_text || []).map((item) => item.plain_text || "").join("");
    const backup = backupText ? JSON.parse(backupText) : null;
    if (!backup?.data) return null;
    const migrated = { version: crypto.randomUUID(), updated_at: backup.saved_at || new Date().toISOString(), device_id: "notion-backup", data: backup.data };
    await writeCurrent(env, migrated);
    return migrated;
  }
  const blocks = await children(env, page.id);
  const code = blocks.find((block) => block.type === "code");
  if (!code) return null;
  const text = (code.code?.rich_text || []).map((item) => item.plain_text || "").join("");
  return text ? JSON.parse(text) : null;
}

async function writeCurrent(env, envelope) {
  let page = await findCurrentPage(env);
  if (!page) {
    page = await notion(env, "POST", "/pages", {
      parent: { type: "page_id", page_id: env.NOTION_PARENT_PAGE_ID },
      properties: { title: { type: "title", title: [{ type: "text", text: { content: CURRENT_TITLE } }] } },
    });
  }
  const blocks = await children(env, page.id);
  const code = blocks.find((block) => block.type === "code");
  const value = { language: "json", rich_text: richText(JSON.stringify(envelope)) };
  if (code) await notion(env, "PATCH", `/blocks/${code.id}`, { code: value });
  else await notion(env, "PATCH", `/blocks/${page.id}/children`, { children: [{ object: "block", type: "code", code: value }] });
}

async function createBackup(env, data) {
  const now = new Date();
  const timestamp = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Taipei", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).format(now).replace(" ", " ").replaceAll(":", "-");
  const envelope = { version: 1, saved_at: now.toISOString(), data };
  const page = await notion(env, "POST", "/pages", {
    parent: { type: "page_id", page_id: env.NOTION_PARENT_PAGE_ID },
    properties: { title: { type: "title", title: [{ type: "text", text: { content: `牛牛預算備份｜${timestamp}` } }] } },
    children: [{ object: "block", type: "code", code: { language: "json", rich_text: richText(JSON.stringify(envelope)) } }],
  });
  return { page_id: page.id, saved_at: timestamp };
}

async function syncApi(request, env) {
  if (!authorized(request, env)) return json({ error: "請輸入正確的手機同步存取碼" }, 401);
  if (request.method === "GET") return json({ ok: true, current: await readCurrent(env) });
  if (request.method !== "PUT") return json({ error: "不支援的方法" }, 405);
  const body = await request.json();
  if (!body.data || typeof body.data !== "object") return json({ error: "同步資料格式不正確" }, 400);
  const current = await readCurrent(env);
  if (current?.version && body.base_version && current.version !== body.base_version) {
    return json({ error: "其他裝置已有較新的資料", conflict: true, current }, 409);
  }
  const envelope = {
    version: crypto.randomUUID(),
    updated_at: new Date().toISOString(),
    device_id: String(body.device_id || "unknown").slice(0, 80),
    data: body.data,
  };
  await writeCurrent(env, envelope);
  return json({ ok: true, current: envelope });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    try {
      if (url.pathname === "/api/notion/status") {
        if (!authorized(request, env)) return json({ error: "需要存取碼" }, 401);
        return json({ configured: true, storage: "Notion Cloud" });
      }
      if (url.pathname === "/api/notion/backup" && request.method === "POST") {
        if (!authorized(request, env)) return json({ error: "請輸入正確的手機同步存取碼" }, 401);
        const body = await request.json();
        if (!body.data || typeof body.data !== "object") return json({ error: "備份資料格式不正確" }, 400);
        return json({ ok: true, ...(await createBackup(env, body.data)) });
      }
      if (url.pathname === "/api/sync/current") return await syncApi(request, env);
      return env.ASSETS.fetch(request);
    } catch (error) {
      return json({ error: error.message || "雲端同步失敗" }, 502);
    }
  },
};
