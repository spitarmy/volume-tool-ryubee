#!/usr/bin/env python3
"""
商品マスタ44品目を一括インポートするスクリプト。
Ryubeeバックエンドの /v1/templates/bulk-import エンドポイントを呼び出す。

Usage:
  python3 import_items.py [--api-url http://localhost:8000] [--token YOUR_TOKEN]
"""
import requests
import sys

# Excelから抽出した44品目データ
ITEMS = [
    {"name": "一般廃棄物処理費", "unit_price": 0, "unit": "ヶ月"},
    {"name": "塵芥処理費", "unit_price": 0, "unit": "式"},
    {"name": "産業廃棄物処理費", "unit_price": 0, "unit": "kg"},
    {"name": "大型ごみ処理費", "unit_price": 0, "unit": "㎥"},
    {"name": "家電リサイクル立替料（手数料込）", "unit_price": 0, "unit": "台"},
    {"name": "マニフェスト代", "unit_price": 50, "unit": "枚"},
    {"name": "分別収集費", "unit_price": 0, "unit": "式"},
    {"name": "ダンボール処理費", "unit_price": 0, "unit": "式"},
    {"name": "資源ごみ処理費", "unit_price": 0, "unit": "ヶ月"},
    {"name": "感染性ポリ容器", "unit_price": 0, "unit": "ケース"},
    {"name": "感染性廃棄物", "unit_price": 0, "unit": "ℓ"},
    {"name": "非感染性廃棄物", "unit_price": 0, "unit": "ℓ"},
    {"name": "バイオハザードマーク", "unit_price": 0, "unit": "枚"},
    {"name": "人件費", "unit_price": 0, "unit": "人"},
    {"name": "廃油", "unit_price": 0, "unit": "ℓ"},
    {"name": "ダストボックス", "unit_price": 0, "unit": "式"},
    {"name": "ダストボックス処分費", "unit_price": 0, "unit": "式"},
    {"name": "コンテナレンタル料", "unit_price": 0, "unit": "ヶ月"},
    {"name": "収集運搬費", "unit_price": 0, "unit": "回"},
    {"name": "高速代", "unit_price": 0, "unit": "式"},
    {"name": "機密書類処理費", "unit_price": 0, "unit": "kg"},
    {"name": "溶解証明書代", "unit_price": 0, "unit": "枚"},
    {"name": "産業廃棄物処理費　持込分", "unit_price": 0, "unit": "kg"},
    {"name": "収集運搬費　廃プラ", "unit_price": 0, "unit": "回"},
    {"name": "産業廃棄物処理費　（別分）", "unit_price": 0, "unit": "kg"},
    {"name": "産業廃棄物処理費　廃プラ", "unit_price": 0, "unit": "kg"},
    {"name": "産業廃棄物処理費　発泡", "unit_price": 0, "unit": "kg"},
    {"name": "産業廃棄物　動植物性残渣", "unit_price": 0, "unit": "kg"},
    {"name": "産業廃棄物　資源ごみ", "unit_price": 0, "unit": "袋"},
    {"name": "産業廃棄物処理費　蛍光灯", "unit_price": 0, "unit": "kg"},
    {"name": "産業廃棄物処理費　ウエス", "unit_price": 0, "unit": "kg"},
    {"name": "産業廃棄物処理費　廃プラ　シール", "unit_price": 0, "unit": "kg"},
    {"name": "産業廃棄物処理費　廃プラ　クロス", "unit_price": 0, "unit": "kg"},
    {"name": "産業廃棄物処理費　廃プラ（選別）", "unit_price": 0, "unit": "kg"},
    {"name": "産業廃棄物処理費　廃プラ（RPF）", "unit_price": 0, "unit": "kg"},
    {"name": "産業廃棄物処理費　廃プラ　木くず", "unit_price": 0, "unit": "kg"},
    {"name": "産業廃棄物処理費　金属くず", "unit_price": 0, "unit": "kg"},
    {"name": "産業廃棄物処理費　ガラス・陶磁器類", "unit_price": 0, "unit": "kg"},
    {"name": "資源ごみ缶・ビン・ペット・小型金物類", "unit_price": 0, "unit": "kg"},
    {"name": "繰越", "unit_price": 0, "unit": "ヶ月"},
    {"name": "収入印紙代", "unit_price": 200, "unit": "枚"},
    {"name": "祭りのｺﾞﾐ", "unit_price": 650, "unit": "袋"},
    {"name": "事業系産業廃棄物処理費", "unit_price": 0, "unit": "式"},
    {"name": "事業系産業廃棄物収集運搬費", "unit_price": 0, "unit": "式"},
    {"name": "一斗缶回収", "unit_price": 0, "unit": "個"},
    {"name": "段ボール", "unit_price": 0, "unit": "式"},
]

def main():
    api_url = "http://localhost:8000"
    token = None
    
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--api-url" and i < len(sys.argv) - 1:
            api_url = sys.argv[i + 1]
        elif arg == "--token" and i < len(sys.argv) - 1:
            token = sys.argv[i + 1]
    
    if not token:
        print("Usage: python3 import_items.py --token YOUR_JWT_TOKEN [--api-url URL]")
        print("  トークンはブラウザのlocalStorageから取得: localStorage.getItem('token')")
        sys.exit(1)
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    
    payload = {"items": ITEMS}
    
    print(f"📦 {len(ITEMS)} 品目を {api_url}/v1/templates/bulk-import にインポート中...")
    resp = requests.post(f"{api_url}/v1/templates/bulk-import", json=payload, headers=headers)
    
    if resp.status_code == 201:
        result = resp.json()
        print(f"✅ 完了! 新規登録: {result['created']}件, スキップ(既存): {result['skipped']}件")
    else:
        print(f"❌ エラー ({resp.status_code}): {resp.text}")
        sys.exit(1)

if __name__ == "__main__":
    main()
