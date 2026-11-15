# Streamlit Cloud デプロイ＆スマホWeb化ガイド

作成した「AI学習パートナー」を **Streamlit Cloud** に無料デプロイし、
スマートフォン（iPhone/Android）のホーム画面からいつでも専用URLで起動できるようにする手順です。

---

## 1. 準備するもの
1. **GitHubアカウント**（無料）
2. **Streamlit Community Cloud アカウント**（[share.streamlit.io](https://share.streamlit.io/)、GitHubで無料サインアップ可能）

---

## 2. デプロイ手順（カンタン3ステップ）

### ステップ①：GitHub にリポジトリを作成してプッシュ
1. ブラウザで [GitHub](https://github.com/) にログインし、**「New repository」** を作成します。
   - Repository name: `ai_study_partner`
   - Public または Private どちらでもOK
2. ターミナルで以下のコマンドを実行してコードをプッシュします：
   ```bash
   git remote add origin https://github.com/あなたのGitHubユーザー名/ai_study_partner.git
   git branch -M main
   git push -u origin main
   ```

### ステップ②：Streamlit Cloud でアプリを立ち上げる
1. [share.streamlit.io](https://share.streamlit.io/) にアクセスし、GitHubアカウントでログインします。
2. **「New app」** をクリックします。
   - **Repository**: `あなたのユーザー名/ai_study_partner`
   - **Branch**: `main`
   - **Main file path**: `app.py`
3. **「Deploy!」** をクリックします（1〜2分でビルドが完了し、世界中からアクセスできる固有の公開URLが発行されます）。

### ステップ③：APIキーや設定を登録する（Secrets設定）
Streamlit Cloud の管理画面で、安全にAPIキーを設定できます：
1. アプリ右下の **「Settings」>「Secrets」** を開きます。
2. 以下の内容を貼り付けて保存します：
   ```toml
   GEMINI_API_KEY = "あなたのGemini-APIキー"
   ```

---

## 3. スマホのホーム画面に追加する（PWA感覚で利用）
発行された Streamlit URL（例: `https://ai-study-partner-xxxx.streamlit.app`）をスマホで開きます：
- **iPhone (Safari)**: 共有ボタン（四角から矢印のアイコン）をタップ ＞ **「ホーム画面に追加」**
- **Android (Chrome)**: メニュー（右上「︙」）をタップ ＞ **「ホーム画面に追加」** または **「アプリをインストール」**

これで、通学電車や自習室、学校の休み時間でも、アプリアイコンをタップするだけでいつでも机の上からスマホカメラで間違えた問題を撮影・復習できるようになります！

