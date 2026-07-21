# 牛牛預算 Notion 備份設定

## 1. 在 Notion 建立備份頁面

1. 在 Notion 新增一個空白頁面，例如「牛牛預算雲端備份」。
2. 從瀏覽器網址複製該頁面的 ID。頁面 ID 是網址中最後一段的 32 位英數字。

## 2. 建立 Notion 整合

1. 前往 <https://www.notion.so/profile/integrations> 建立 Internal integration。
2. 啟用讀取、插入與更新內容權限。
3. 複製整合的 Secret。
4. 回到「牛牛預算雲端備份」頁面，從連線／Connections 選單把剛建立的整合加入該頁面。

## 3. 設定本機金鑰

1. 複製 `notion_config.example.json`，重新命名為 `notion_config.local.json`。
2. 將 Notion Secret 填入 `token`。
3. 將備份頁面的 ID 填入 `parent_page_id`。

`notion_config.local.json` 已加入 `.gitignore`，請勿把它傳給別人或放到公開網路。

## 4. 測試備份

1. 雙擊「啟動小金庫.cmd」。
2. 使用開啟的 `http://127.0.0.1:8091/` 網頁，不要直接雙擊 `index.html`。
3. 開啟右上角設定，確認 Notion 狀態顯示「Notion 已設定」。
4. 按「備份到 Notion」。
5. 回到 Notion，應該會看到名稱類似「牛牛預算備份｜2026-07-20 12-30-00」的新子頁面。

## Cloudflare 手機同步版

正式環境由 Cloudflare Worker 提供 HTTPS API，並使用三個加密 Secret：

- `NOTION_API_TOKEN`
- `NOTION_PARENT_PAGE_ID`
- `SYNC_ACCESS_KEY`

部署指令為 `pnpm exec wrangler deploy`。手機第一次開啟時需輸入 `SYNC_ACCESS_KEY`，之後資料變更會自動同步；手動「備份到 Notion」仍會建立一份日期歷史快照。

## 注意

- 「從 Notion 還原」會讀取最新同步資料，覆蓋前先在瀏覽器保存安全備份。
- `notion_config.local.json`、`.dev.vars` 與所有 Secret 均不得提交到 Git。
- 本機 Python 服務仍可用於離線測試；跨裝置使用請開啟 Cloudflare HTTPS 網址。
