/**
 * ==============================================================================
 * AI学習パートナー - Googleドライブ画像OCR・自動誤答解析システム (GAS)
 * 
 * 【概要】
 * スマホで撮影されたプリント・ノート・答案の画像（Googleドライブの監視フォルダ）を検知し、
 * 最新の Gemini 3.8 Flash / Gemini 4 Argon API を使って画像解析・誤答原因・ヒントを自動抽出。
 * Googleスプレッドシートの「weakness_db」にエビングハウス忘却曲線データとして自動登録します。
 * ==============================================================================
 */

// 設定項目
const CONFIG = {
  // スプレッドシートID
  SPREADSHEET_ID: "1ZFTjAOHDhlk8S3e35gEwxy-LXfupl7x_86s4lqKWFEw",
  SHEET_NAME: "weakness_db",

  // 監視対象のGoogleドライブフォルダ名
  WATCH_FOLDER_NAME: "Study_Uploads",
  PROCESSED_FOLDER_NAME: "Study_Uploads_Processed",

  // 使用するGeminiモデル（Google AI Plusで使える 3.6 Flash を推奨）
  GEMINI_MODEL: "gemini-3.6-flash", // または "gemini-3.5-flash-lite"
  
  // スクリプトプロパティに設定したAPIキー名
  API_KEY_PROPERTY_NAME: "GEMINI_API_KEY"
};

/**
 * 定期実行用メイン関数（時間主導型トリガー: 5分〜15分おきに自動実行）
 */
function processNewStudyImages() {
  const apiKey = PropertiesService.getScriptProperties().getProperty(CONFIG.API_KEY_PROPERTY_NAME);
  if (!apiKey) {
    Logger.log("エラー: スクリプトプロパティに GEMINI_API_KEY が設定されていません。");
    return;
  }

  // 1. 監視フォルダおよび処理済みフォルダの取得
  const watchFolder = getOrCreateFolder(CONFIG.WATCH_FOLDER_NAME);
  const processedFolder = getOrCreateFolder(CONFIG.PROCESSED_FOLDER_NAME);
  
  // 2. フォルダ内の未処理画像ファイルを走査
  const files = watchFolder.getFiles();
  let processedCount = 0;

  while (files.hasNext()) {
    const file = files.next();
    const mimeType = file.getMimeType();

    // 画像ファイル（JPEG/PNG/WEBP/HEIC）のみ対象
    if (mimeType.startsWith("image/") || mimeType === "application/pdf") {
      Logger.log(`解析開始: ${file.getName()} (${mimeType})`);

      try {
        // 3. Gemini API による画像解析
        const analysis = analyzeImageWithGemini(file, apiKey);
        if (analysis) {
          // 4. スプレッドシート weakness_db へ書き込み
          appendWeaknessRecord(analysis);
          Logger.log(`スプレッドシートへ登録完了: ${analysis.topic}`);

          // 5. 処理済みフォルダへ移動
          file.moveTo(processedFolder);
          processedCount++;
        }
      } catch (err) {
        Logger.log(`ファイル処理失敗 [${file.getName()}]: ${err.message}`);
      }
    }
  }

  Logger.log(`全処理完了: ${processedCount} 件の弱点問題を自動登録しました。`);
}

/**
 * Gemini API を呼び出して画像をマルチモーダル解析し、JSONを取得
 */
function analyzeImageWithGemini(file, apiKey) {
  const base64Data = Utilities.base64Encode(file.getBlob().getBytes());
  const mimeType = file.getMimeType();

  const url = `https://generativelanguage.googleapis.com/v1beta/models/${CONFIG.GEMINI_MODEL}:generateContent?key=${apiKey}`;

  const prompt = `
あなたは松江北高校 理数科（高校1年生）の医学部受験指導責任者です。
添付された画像は、生徒が解いて間違えた問題用紙、ノート、または模試の答案です。
画像を精密に読み取り、以下の項目を厳密なJSONフォーマット（Markdownのバッククォートなし、純粋なJSON文字列）で出力してください。

【出力JSONフォーマット】
{
  "subject": "科目名（数学I・A、化学基礎、物理基礎、英語 など）",
  "unit": "単元名（例: 2次関数と不等式、物質量と化学反応式、運動の法則 など）",
  "topic": "具体的な論点・問題テーマ（例: 文字定数を含む2次関数の最大最小）",
  "miss_reason": "生徒が間違えた具体的な原因・計算ミスや思考の盲点（例: 軸が区間外にある場合分けの境界等号を忘れた）",
  "hint": "ソクラテス的に本質を自力で気付かせるための着眼点ヒント（直接の答えは書かず、解法のカギを問う）",
  "interval_days": 3,
  "retention_rate": 50
}
`;

  const payload = {
    contents: [
      {
        parts: [
          { text: prompt },
          {
            inline_data: {
              mime_type: mimeType,
              data: base64Data
            }
          }
        ]
      }
    ],
    generationConfig: {
      temperature: 0.2,
      response_mime_type: "application/json"
    }
  };

  const options = {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  };

  const response = UrlFetchApp.fetch(url, options);
  const responseCode = response.getResponseCode();
  const responseText = response.getContentText();

  if (responseCode !== 200) {
    throw new Error(`Gemini API エラー (${responseCode}): ${responseText}`);
  }

  const jsonResponse = JSON.parse(responseText);
  const contentText = jsonResponse.candidates[0].content.parts[0].text;
  return JSON.parse(contentText);
}

/**
 * スプレッドシート「weakness_db」の末尾に解析結果を追記
 */
function appendWeaknessRecord(data) {
  const ss = SpreadsheetApp.openById(CONFIG.SPREADSHEET_ID);
  let sheet = ss.getSheetByName(CONFIG.SHEET_NAME);

  if (!sheet) {
    sheet = ss.insertSheet(CONFIG.SHEET_NAME);
    sheet.appendRow([
      "id", "subject", "unit", "topic", "miss_reason", 
      "hint", "interval_days", "last_reviewed", "retention_rate", "status"
    ]);
  }

  const lastRow = sheet.getLastRow();
  const newId = `W-${String(lastRow).padStart(3, "0")}`;
  const todayStr = Utilities.formatDate(new Date(), "Asia/Tokyo", "yyyy-MM-dd");

  const rowValues = [
    newId,
    data.subject || "数学I・A",
    data.unit || "未分類単元",
    data.topic || "自動抽出問題",
    data.miss_reason || "誤答原因未解析",
    data.hint || "定義に立ち返って考えよう",
    data.interval_days || 3,
    todayStr,
    data.retention_rate || 50,
    "復習待ち"
  ];

  sheet.appendRow(rowValues);
}

/**
 * フォルダ名からフォルダを取得、無ければ新規作成
 */
function getOrCreateFolder(folderName) {
  const folders = DriveApp.getFoldersByName(folderName);
  if (folders.hasNext()) {
    return folders.next();
  }
  return DriveApp.createFolder(folderName);
}

