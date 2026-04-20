# Ryu兵衛 バックエンドAPI

FastAPI + PostgreSQL で構築した Ryu兵衛の本番バックエンドです。

## ファイル構成

```
ryubee-backend/
  app/
    main.py          # エントリポイント・CORS
    database.py      # DB接続
    models.py        # テーブル定義 (SQLAlchemy)
    auth.py          # JWT認証ユーティリティ
    routers/
      auth.py        # /v1/auth/*
      settings.py    # /v1/settings
      jobs.py        # /v1/jobs/*
      admin.py       # /v1/admin/*
  requirements.txt
  .env.example
```

---

## ローカル開発環境のセットアップ

```bash
cd ryubee-backend

# 仮想環境作成
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 依存インストール
pip install -r requirements.txt

# 環境変数ファイルを作成（SQLiteでローカル動作）
cp .env.example .env
# .env の SECRET_KEY を適当な乱数に変更（必須）

# サーバー起動
uvicorn app.main:app --reload

# → http://localhost:8000/docs でSwagger UI確認
```

---

## Render.com へのデプロイ手順

### 1. GitHubリポジトリを作成 & プッシュ

```bash
# ryubee-backend ディレクトリをGitリポジトリ化
git init
git add .
git commit -m "initial backend"
# GitHubで新しいリポジトリ「ryubee-backend」を作成してpush
git remote add origin https://github.com/<your-username>/ryubee-backend.git
git push -u origin main
```

### 2. Render.com でPostgreSQLを作成

1. [render.com](https://render.com) にログイン
2. **New → PostgreSQL** を選択
3. 名前: `ryubee-db`、Plan: **Free**
4. 作成後、**Internal Database URL** をコピー（後で使用）

### 3. Render.com でWebサービスを作成

1. **New → Web Service** を選択
2. GitHubの `ryubee-backend` リポジトリを接続
3. 以下を設定:

| 項目 | 値 |
|------|----|
| **Runtime** | Python 3 |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |

4. **Environment Variables** に以下を追加:

| キー | 値 |
|------|----|
| `DATABASE_URL` | PostgreSQLの Internal Database URL |
| `SECRET_KEY` | ランダムな長い文字列（例: `openssl rand -hex 32` で生成） |
| `FRONTEND_ORIGIN` | `https://your-app.vercel.app` |

5. **Deploy** → デプロイ完了後、URL（例: `https://ryubee-api.onrender.com`）が取得できる

### 4. フロントエンドのAPI URLを切り替え

`volume-tool-ryubee/assets/js/api.js` の `BASE_URL` を新しいURLに:

```js
const BASE_URL = 'https://ryubee-backend.onrender.com/v1';
```

---

## 主なAPIエンドポイント

| メソッド | パス | 説明 | 権限 |
|--------|------|------|------|
| POST | `/v1/auth/register` | 業者・初期管理者登録 | 不要 |
| POST | `/v1/auth/login` | ログイン・JWT取得 | 不要 |
| GET | `/v1/auth/me` | 自分の情報 | 全員 |
| POST | `/v1/auth/invite` | スタッフ追加 | admin |
| GET | `/v1/settings` | 料金・会社情報取得 | 全員 |
| PUT | `/v1/settings` | 設定保存 | admin |
| GET | `/v1/jobs` | 案件一覧 | 全員 |
| POST | `/v1/jobs` | 案件作成 | 全員 |
| PUT | `/v1/jobs/{id}` | 案件更新（署名含む） | 全員 |
| DELETE | `/v1/jobs/{id}` | 案件削除 | 全員 |
| GET | `/v1/admin/summary` | 月間KPI | admin |
| GET | `/v1/admin/sales-chart` | 日別売上グラフ | admin |
| GET | `/v1/admin/staff-ranking` | 担当者別売上 | admin |

ローカルで `http://localhost:8000/docs` を開くとSwagger UIで全APIを試せます。
