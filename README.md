# 防騙提醒

給一般民眾看的防騙說明網站，用大字、短句，手機就能看。不是政府機關。

網站內容在 `site/`。上線網址預計為：

https://scam-alert-tw.github.io/anti-scam/

## 頁面上有什麼

一整頁就好，沒有選單：

- 最上面可以直接打 **165**（反詐騙專線）
- 緊急時打 **110**
- 常見手法：假投資、假網購與解除分期、假警察與假公務員、假交友、假工作、假簡訊與假網址、叫你去操作提款機
- 看到就要停的清單
- 已經被騙時怎麼做
- 最近的官方提醒，每一則連到原文，並標日期

頁面不收集資料，沒有分析工具，也沒有聯絡方式。

## 最新消息怎麼更新

`scripts/update_news.py` 會抓公開資料，寫進 `site/data/news.json`，並更新首頁上的清單。不需要金鑰，也不用付費 API。

1. 先用內政部警政署 **165 全民防騙網** 公開文章：
   - https://165.npa.gov.tw/api/article/list/9 （涉詐資訊公告）
   - https://165.npa.gov.tw/api/article/list/1 （新聞快訊）
   - 原文網址形如 `https://165.npa.gov.tw/article/9/1862`
2. 若 165 抓不到，或最新一則超過 60 天，改用 **中央社** 公開 RSS（社會、地方、生活），只留標題有詐騙相關字的新聞，並連到中央社原文。

在自己的電腦上可以先跑：

```bash
python3 scripts/update_news.py
```

`.github/workflows/update-news.yml` 會在每天台北時間早上 7 點左右自動跑（排程寫的是 UTC 23:00）。有新資料才會提交。同一個工作也會把網站發佈到 GitHub Pages，因為用內建權杖推上去的提交，不會再觸發另一個工作流程。GitHub 有時會把排程稍微延後。

`.github/workflows/deploy-pages.yml` 會在推送到 `main` 時，把 `site/` 發佈到 GitHub Pages。

## 上線前要在 GitHub 點什麼

合併到 `main` 之後：

1. 打開這個儲存庫的 **Settings**。
2. 左側點 **Pages**。
3. 在 **Build and deployment** 的 **Source**，選 **GitHub Actions**。

每日更新要能把新清單推回 `main`，還需要寫入權限：

1. **Settings** → **Actions** → **General**。
2. 拉到 **Workflow permissions**。
3. 選 **Read and write permissions**。
4. 按 **Save**。

如果組織把 Actions 設成只能讀取，需要組織管理員允許這個儲存庫寫入。`main` 若有分支保護、不允許 Actions 直接推送，每日更新的提交會失敗，需要放行 `github-actions[bot]`，或改成由人工合併。

## 本機預覽

```bash
python3 scripts/update_news.py
cd site
python3 -m http.server 8000
```

瀏覽器打開 http://127.0.0.1:8000/

## 免責

內容只供防騙參考。遇到事情請打 165 或 110，並以 165 全民防騙網與警察機關的說法為準。
